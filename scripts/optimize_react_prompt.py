#!/usr/bin/env python3
"""
Utility script for running GEPA prompt optimization.

Example usage (dry run):
    uv run python scripts/optimize_react_prompt.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from reasoning_service.config import settings
from reasoning_service.models.schema import (
    CaseBundle,
    CitationInfo,
    ConfidenceBreakdown,
    CriterionResult,
    DecisionStatus,
    ReasoningStep,
    RetrievalMethod,
)
from reasoning_service.prompts.react_system_prompt import REACT_SYSTEM_PROMPT
from reasoning_service.services.react_controller import ReActController as LLMReActController
from reasoning_service.services.retrieval import RetrievalService as AsyncRetrievalService
from reasoning_service.services.prompt_evaluator import MetricWeights, PolicyEvaluator
from reasoning_service.services.prompt_optimizer import (
    OptimizationConfig,
    PromptOptimizer,
    ReActControllerAdapter,
)
from reasoning_service.services.prompt_registry import PromptRegistry
from reasoning_service.utils.case_conversion import case_dict_to_case_bundle


@dataclass
class EvaluationCase:
    case_bundle: CaseBundle
    policy_document_id: str
    source: str


async def _simulate_evaluation(candidate: Dict[str, Any], minibatch: List[EvaluationCase]):
    """Fake evaluation used for dry runs."""
    return [_synthetic_result(entry.case_bundle) for entry in minibatch]


async def _evaluate_with_controller(candidate: Dict[str, Any], minibatch: List[EvaluationCase]):
    """Real evaluation that calls the LLM controller."""
    retrieval_service = AsyncRetrievalService()
    controller = LLMReActController(
        retrieval_service=retrieval_service,
        system_prompt=candidate["system_prompt"],
    )
    results: List[CriterionResult] = []
    try:
        for entry in minibatch:
            result_batch = await controller.evaluate_case(
                case_bundle=entry.case_bundle,
                policy_document_id=entry.policy_document_id,
            )
            results.extend(result_batch)
    finally:
        await retrieval_service.close()
    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize the ReAct system prompt.")
    parser.add_argument(
        "--cases-path",
        type=Path,
        default=Path(settings.gepa_dataset_path),
        help="Directory or file containing sample cases (JSON). Defaults to tests/data/cases.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip live LLM calls.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("optimization_results/latest.json"),
        help="Where to store the final evaluation result.",
    )
    parser.add_argument(
        "--auto-mode",
        type=str,
        default=settings.gepa_auto_mode,
        choices=["light", "medium", "heavy"],
        help="Optimization intensity preset.",
    )
    args = parser.parse_args()

    registry = PromptRegistry()
    registry.load()

    config = OptimizationConfig(auto_mode=args.auto_mode)
    evaluator = PolicyEvaluator(
        weights=MetricWeights(
            citation_accuracy=config.citation_accuracy_weight,
            reasoning_coherence=config.reasoning_coherence_weight,
            confidence_calibration=config.confidence_calibration_weight,
            status_correctness=config.status_correctness_weight,
        )
    )

    dataset = _load_dataset(args.cases_path)

    if args.dry_run:
        evaluate_fn = _simulate_evaluation
        print("Dry run mode: using simulated evaluation results.")
    else:
        evaluate_fn = _evaluate_with_controller
        print("Running live evaluation; ensure LLM and PageIndex credentials are configured.")

    adapter = ReActControllerAdapter(
        evaluate_fn=evaluate_fn,
        evaluator=evaluator,
    )
    optimizer = PromptOptimizer(adapter=adapter, registry=registry, config=config)

    result = await optimizer.optimize(
        base_prompt=registry.latest().prompt_text if registry.latest() else REACT_SYSTEM_PROMPT,
        test_cases=dataset,
        generations=1,
    )

    if result:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "candidate_id": result.candidate_id,
                    "aggregate_score": result.metrics.aggregate_score,
                    "feedback": result.feedback,
                },
                indent=2,
            )
        )
        print(f"Optimization complete. Aggregate score={result.metrics.aggregate_score:.3f}")
    else:
        print("Optimization aborted: no result produced.")


def _load_dataset(path: Path) -> List[EvaluationCase]:
    """Load case fixtures and convert them to CaseBundle objects."""
    entries: List[EvaluationCase] = []

    def _add_entry(data: Dict[str, Any], source: str) -> None:
        case_bundle, policy_doc_id = case_dict_to_case_bundle(data)
        entries.append(EvaluationCase(case_bundle=case_bundle, policy_document_id=policy_doc_id, source=source))

    if path.is_dir():
        for file in sorted(path.glob("*.json")):
            _add_entry(json.loads(file.read_text()), str(file))
    elif path.is_file():
        payload = json.loads(path.read_text())
        if isinstance(payload, list):
            for idx, case in enumerate(payload):
                _add_entry(case, f"{path}:{idx}")
        elif "cases" in payload:
            for idx, case in enumerate(payload["cases"]):
                _add_entry(case, f"{path}:{idx}")
        else:
            _add_entry(payload, str(path))
    else:
        raise SystemExit(f"No dataset found at {path}")

    return entries


def _synthetic_result(case_bundle: CaseBundle) -> CriterionResult:
    """Generate a fake CriterionResult for dry-run evaluation."""
    status = DecisionStatus.MET if len(case_bundle.fields) >= 2 else DecisionStatus.UNCERTAIN
    citation = CitationInfo(
        doc=case_bundle.policy_id,
        version=case_bundle.metadata.get("policy_version", "v1"),
        section=case_bundle.metadata.get("criterion_id", "N/A"),
        pages=[1],
    )
    confidence = 0.85 if status is DecisionStatus.MET else 0.6
    breakdown = ConfidenceBreakdown(c_tree=0.9, c_span=0.9, c_final=0.95, c_joint=confidence)
    trace = [
        ReasoningStep(step=1, action="think", observation="Dry-run reasoning placeholder."),
        ReasoningStep(step=2, action="decide", observation=f"Status={status.value}."),
    ]
    return CriterionResult(
        criterion_id=case_bundle.metadata.get("criteria", ["unknown"])[0],
        status=status,
        citation=citation,
        rationale="Dry-run evaluation.",
        confidence=confidence,
        confidence_breakdown=breakdown,
        search_trajectory=["root", "node-1"],
        retrieval_method=RetrievalMethod.PAGEINDEX_LLM,
        reasoning_trace=trace,
    )


if __name__ == "__main__":
    asyncio.run(main())
