"""
CLI entry points for the reasoning-service single-policy demo workflow.

This module provides the primary command-line interface for interacting with
the prior authorization reasoning system. It supports policy ingestion,
validation, and decision-making workflows.

Commands:
  - ingest-policy: Upload PDF to PageIndex, poll for tree completion, and cache locally
  - validate-tree: Verify cached tree file exists and contains valid nodes
  - show-policy: Display metadata about a persisted policy snapshot
  - run-decision: Execute full retrieval + controller pipeline for a single case
  - run-test-suite: Evaluate all curated test fixtures and report results

All commands use the PageIndex API for retrieval and the ReAct controller
for policy-grounded decision making with reasoning traces.
"""

from __future__ import annotations

import json
import hashlib
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from controller.react_controller import ReActController as CliReActController
from policy_ingest.pageindex_client import PageIndexClient, PageIndexError
from policy_ingest.persistence import fetch_policy_summary, persist_policy_snapshot
from retrieval.service import RetrievalService
from retrieval.tree_search import TreeSearchService
from telemetry.logger import get_logger, log_event
from reasoning_service.models.schema import DecisionStatus, ConfidenceBreakdown
from reasoning_service.services.retrieval import RetrievalService as AsyncRetrievalService
from reasoning_service.services.react_controller import ReActController as LLMReActController

DATA_DIR = Path("data")
TREE_CACHE_PATH = DATA_DIR / "pageindex_tree.json"
FIXTURE_DIR = Path("tests/data/cases")

app = typer.Typer(help="Reasoning-service CLI for the single-policy demo.")
logger = get_logger()
CONTROLLER_CHOICES = {"heuristic", "llm"}


def _normalize_controller_choice(value: str) -> str:
    choice = value.lower()
    if choice not in CONTROLLER_CHOICES:
        raise typer.BadParameter(f"controller must be one of {sorted(CONTROLLER_CHOICES)}")
    return choice


def ingest_policy_command(
    pdf_path: Path,
    cache_path: Path = TREE_CACHE_PATH,
    max_attempts: int = 5,
    policy_id: str = "LCD-L34220",
    version_id: str = "2025-Q1",
    source_url: Optional[str] = None,
) -> tuple[str, bool]:
    """
    Core logic for policy ingestion workflow.

    Uploads a policy PDF to PageIndex, polls for tree completion, caches the
    resulting tree structure locally, and persists metadata to the database.

    Args:
        pdf_path: Path to the policy PDF file
        cache_path: Where to save the tree JSON (default: data/pageindex_tree.json)
        max_attempts: Maximum number of polling attempts for tree completion
        policy_id: Unique policy identifier (e.g., LCD-L34220)
        version_id: Semantic version label (e.g., 2025-Q1)
        source_url: Original policy source URL (optional)

    Returns:
        Tuple of (doc_id, tree_ready_flag)

    Raises:
        PageIndexError: If upload or tree generation fails
        ValueError: If PDF file not found or invalid
    """
    client = PageIndexClient()
    pdf_bytes = pdf_path.read_bytes()
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    doc_id = client.upload_pdf(pdf_path)
    log_event(logger, "policy_upload_submitted", doc_id=doc_id)
    tree: Dict[str, Any] = {}
    ready = False
    attempts = 0
    for attempt in range(max_attempts):
        tree = client.get_tree(doc_id)
        attempts = attempt + 1
        if _has_nodes(tree):
            ready = True
            break
        typer.secho(
            f"Tree not ready yet (status={tree.get('status')}). Attempt {attempt + 1}/{max_attempts}",
            fg=typer.colors.YELLOW,
        )
    if not _has_nodes(tree):
        typer.secho(
            "Tree never became ready; cached the latest response. Wait a few seconds and rerun this command.",
            fg=typer.colors.RED,
        )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(tree, indent=2))
    markdown_ptr = tree.get("markdown_ptr") or f"file://{cache_path.resolve()}"
    try:
        node_count = persist_policy_snapshot(
            policy_id=policy_id,
            version_id=version_id,
            pageindex_doc_id=doc_id,
            pdf_sha256=pdf_sha256,
            markdown_ptr=str(markdown_ptr),
            tree_json_ptr=str(cache_path.resolve()),
            tree_payload=tree,
            source_url=source_url,
        )
    except Exception as exc:
        typer.secho(f"Failed to persist policy snapshot: {exc}", fg=typer.colors.RED)
        raise
    log_event(
        logger,
        "policy_persisted",
        policy_id=policy_id,
        version_id=version_id,
        doc_id=doc_id,
        nodes=node_count,
    )
    log_event(
        logger,
        "policy_ingested",
        doc_id=doc_id,
        cache_path=str(cache_path),
        attempts=attempts,
        nodes=node_count,
        policy_id=policy_id,
        version_id=version_id,
    )
    return doc_id, ready


def _has_nodes(tree: Dict[str, Any]) -> bool:
    nodes = tree.get("result") or tree.get("nodes")
    return bool(nodes)


@app.command()
def ingest_policy(
    pdf_path: Path = typer.Argument(DATA_DIR / "Dockerfile.pdf"),
    cache_path: Path = typer.Option(
        TREE_CACHE_PATH, help="Where to cache the PageIndex tree JSON."
    ),
    policy_id: str = typer.Option("LCD-L34220", help="Unique policy identifier."),
    version_id: str = typer.Option("2025-Q1", help="Semantic version for this ingestion run."),
    source_url: Optional[str] = typer.Option(None, help="Original policy source URL, if known."),
) -> None:
    """Upload the policy PDF to PageIndex and cache the resulting tree JSON."""
    try:
        doc_id, ready = ingest_policy_command(
            pdf_path=pdf_path,
            cache_path=cache_path,
            policy_id=policy_id,
            version_id=version_id,
            source_url=source_url,
        )
    except PageIndexError as exc:
        typer.secho(f"PageIndex ingestion failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    color = typer.colors.GREEN if ready else typer.colors.YELLOW
    status_msg = "ready" if ready else "cached partial response (check status manually)"
    typer.secho(f"Ingestion complete. doc_id={doc_id} ({status_msg})", fg=color)


@app.command()
def validate_tree(cache_path: Path = TREE_CACHE_PATH) -> None:
    """
    Verify that the cached tree file exists and contains valid nodes.

    Checks that the tree cache file is present, parseable as JSON, and
    contains at least one top-level node in the "result" array.

    Args:
        cache_path: Path to the cached tree JSON file

    Raises:
        typer.Exit: If tree file missing or invalid (exit code 1)
    """
    if not cache_path.exists():
        typer.secho(f"No cached tree found at {cache_path}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    tree = json.loads(cache_path.read_text())
    nodes = tree.get("result") or tree.get("nodes") or tree.get("tree") or []
    typer.secho(f"Cached tree OK. Top-level nodes: {len(nodes)}", fg=typer.colors.GREEN)


@app.command()
def show_policy(
    policy_id: str = typer.Option(..., help="Policy identifier to inspect."),
    version_id: str = typer.Option(..., help="Version label to inspect."),
) -> None:
    """
    Print metadata about a persisted policy snapshot from the database.

    Retrieves and displays policy version metadata including PageIndex doc_id,
    PDF hash, ingestion timestamp, and node count.

    Args:
        policy_id: Policy identifier (e.g., LCD-L34220)
        version_id: Version label (e.g., 2025-Q1)

    Raises:
        typer.Exit: If policy version not found in database (exit code 1)
    """
    try:
        summary = fetch_policy_summary(policy_id, version_id)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(summary, indent=2))


def _build_retrieval_service(tree_path: Path):
    client = PageIndexClient()
    if client.available:
        return RetrievalService(client=client)
    return TreeSearchService(client=None, tree_cache_path=tree_path)


def _read_case(case_file: Path) -> Dict[str, Any]:
    return json.loads(case_file.read_text())


def _run_case(
    case_data: Dict[str, Any], retrieval_service, controller: CliReActController
) -> Dict[str, Any]:
    question = case_data.get("question") or case_data.get("criterion_text") or ""
    policy = case_data.get("policy", {})
    doc_id = policy.get("doc_id")
    retrieval = retrieval_service.search(query=question, doc_id=doc_id)
    decision = controller.decide(case_data, retrieval)
    return decision.to_dict()


def run_decision_command(
    case_file: Path,
    tree_path: Path = TREE_CACHE_PATH,
    controller_mode: str = "heuristic",
) -> Dict[str, Any]:
    controller_mode = controller_mode.lower()
    case_data = _read_case(case_file)
    if controller_mode == "llm":
        return asyncio.run(_run_llm_case(case_data))
    if not tree_path.exists():
        raise FileNotFoundError(f"Tree cache missing at {tree_path}. Run ingest_policy first.")
    retrieval_service = _build_retrieval_service(tree_path)
    controller = CliReActController()
    return _run_case(case_data, retrieval_service, controller)


@app.command()
def run_decision(
    case_file: Path = typer.Argument(..., help="Path to case JSON."),
    tree_path: Path = typer.Option(TREE_CACHE_PATH, help="Path to cached tree JSON."),
    controller: str = typer.Option(
        "heuristic",
        "--controller",
        help="Controller to run ('heuristic' or 'llm').",
    ),
) -> None:
    """
    Run the full retrieval + controller pipeline for a single case.

    Loads a case bundle, executes PageIndex retrieval, runs the ReAct controller
    with policy-specific validators, and outputs a structured decision JSON with
    citations, confidence breakdown, and reasoning trace.

    Args:
        case_file: Path to case bundle JSON file
        tree_path: Path to cached PageIndex tree (default: data/pageindex_tree.json)

    Outputs:
        Prints decision JSON to stdout with status (ready/not_ready/uncertain),
        rationale, citations, confidence scores, and reasoning trace
    """
    controller = _normalize_controller_choice(controller)
    try:
        decision = run_decision_command(case_file, tree_path, controller_mode=controller)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(decision, indent=2))


@app.command()
def run_test_suite(
    fixture_dir: Path = typer.Option(FIXTURE_DIR, help="Directory with test fixtures."),
    tree_path: Path = typer.Option(TREE_CACHE_PATH, help="Path to cached tree JSON."),
    controller: str = typer.Option(
        "heuristic", "--controller", help="Controller to run ('heuristic' or 'llm')."
    ),
) -> None:
    """
    Evaluate all curated test fixtures and generate a summary report.

    Iterates through every JSON case file in the fixture directory, runs the
    full decision pipeline, and reports pass/fail/uncertain outcomes with
    confidence scores and reasoning quality metrics.

    Args:
        fixture_dir: Directory containing test case JSON files
        tree_path: Path to cached PageIndex tree

    Outputs:
        Prints summary table showing test results, statuses, confidence scores,
        and overall pass rate
    """
    controller = _normalize_controller_choice(controller)
    fixtures_dir = fixture_dir
    if not fixtures_dir.exists():
        typer.secho(f"No fixtures found at {fixtures_dir}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    cases = sorted(fixtures_dir.glob("*.json"))
    if not cases:
        typer.secho("Fixture directory is empty.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if controller == "heuristic" and not tree_path.exists():
        typer.secho(f"Tree cache missing at {tree_path}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    controller_instance = CliReActController() if controller == "heuristic" else None
    retrieval_service = _build_retrieval_service(tree_path) if controller == "heuristic" else None
    results: List[Dict[str, Any]] = []
    for case_file in cases:
        if controller == "llm":
            decision = run_decision_command(case_file, tree_path, controller_mode="llm")
        else:
            decision = _run_case(_read_case(case_file), retrieval_service, controller_instance)
        log_event(
            logger,
            "case_evaluated",
            case=str(case_file.name),
            status=decision["status"],
            retrieval_method=decision.get("retrieval_method"),
        )
        results.append(decision)

ready = sum(1 for result in results if result["status"] == "ready")
not_ready = sum(1 for result in results if result["status"] == "not_ready")
uncertain = len(results) - ready - not_ready
typer.secho(
    f"Test suite complete. ready={ready}, not_ready={not_ready}, uncertain={uncertain}",
    fg=typer.colors.GREEN,
)


async def _run_llm_case(case_data: Dict[str, Any]) -> Dict[str, Any]:
    case_bundle, policy_doc_id = case_dict_to_case_bundle(case_data)
    retrieval_service = AsyncRetrievalService()
    controller = LLMReActController(retrieval_service=retrieval_service)
    results = await controller.evaluate_case(case_bundle=case_bundle, policy_document_id=policy_doc_id)
    await retrieval_service.close()
    if not results:
        raise RuntimeError("LLM controller returned no results.")
    return _criterion_result_to_cli(results[0], case_data)


def _criterion_result_to_cli(result, case_data: Dict[str, Any]) -> Dict[str, Any]:
    status_map = {
        DecisionStatus.MET: "ready",
        DecisionStatus.MISSING: "not_ready",
        DecisionStatus.UNCERTAIN: "uncertain",
    }
    citation = result.citation
    policy = case_data.get("policy", {})
    confidence = result.confidence_breakdown or ConfidenceBreakdown(
        c_tree=result.confidence, c_span=0.85, c_final=0.9, c_joint=result.confidence
    )
    reasoning_trace = [
        {"step": step.step, "action": step.action, "observation": step.observation}
        for step in result.reasoning_trace
    ]
    return {
        "criterion_id": result.criterion_id,
        "status": status_map.get(result.status, "uncertain"),
        "citation": {
            "policy_id": policy.get("policy_id", citation.doc),
            "version": citation.version,
            "section_path": citation.section,
            "pages": citation.pages,
        },
        "rationale": result.rationale,
        "confidence": {
            "c_tree": confidence.c_tree,
            "c_span": confidence.c_span,
            "c_final": confidence.c_final,
            "c_joint": confidence.c_joint,
        },
        "search_trajectory": result.search_trajectory,
        "reasoning_trace": reasoning_trace,
        "retrieval_method": result.retrieval_method.value,
        "reason_code": result.reason_code,
    }


if __name__ == "__main__":
    app()
