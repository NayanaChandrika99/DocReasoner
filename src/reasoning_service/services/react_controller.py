"""Real ReAct controller with LLM-driven reasoning."""

from __future__ import annotations

import json
import time
from typing import List, Dict, Any, Optional

from reasoning_service.services.llm_client import LLMClient, LLMClientError
from reasoning_service.services.tools import get_tool_definitions
from reasoning_service.services.tool_handlers import ToolExecutor, ToolTimeoutError
from reasoning_service.services.treestore_client import TreeStoreClient
from reasoning_service.services.pubmed import PubMedClient, PubMedCache
from reasoning_service.observability.react_metrics import record_confidence_score
from reasoning_service.prompts.react_system_prompt import REACT_SYSTEM_PROMPT, PROMPT_VERSION
from reasoning_service.models.schema import (
    CaseBundle,
    CriterionResult,
    DecisionStatus,
    CitationInfo,
    EvidenceInfo,
    ConfidenceBreakdown,
    ReasoningStep,
    RetrievalMethod,
)
from reasoning_service.config import settings
from reasoning_service.utils.logging import get_logger


class ReActController:
    """LLM-powered ReAct agent for policy verification."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        retrieval_service: Any = None,
        fts5_service: Optional[Any] = None,
        max_iterations: Optional[int] = None,
        verbose: bool = False,
        system_prompt: Optional[str] = None,
        treestore_client: Optional[TreeStoreClient] = None,
        pubmed_client: Optional[PubMedClient] = None,
        pubmed_cache: Optional[PubMedCache] = None,
    ):
        """Initialize ReAct controller.

        Args:
            llm_client: LLM client instance (created from config if None)
            retrieval_service: RetrievalService instance
            fts5_service: Optional FTS5Fallback service
            max_iterations: Maximum ReAct loop iterations (default from config)
            verbose: Enable verbose logging
        """
        self.llm = llm_client or LLMClient()
        self.retrieval_service = retrieval_service
        self.fts5_service = fts5_service
        self.treestore_client = treestore_client
        self.pubmed_client = pubmed_client
        self.pubmed_cache = pubmed_cache
        self.max_iterations = max_iterations or settings.controller_max_iterations
        self.verbose = verbose
        self.tools = get_tool_definitions()
        self.system_prompt = system_prompt or REACT_SYSTEM_PROMPT
        self.prompt_version = PROMPT_VERSION
        self.logger = get_logger(__name__)
        self.tool_timeout_seconds = settings.controller_tool_timeout_seconds
        self.tool_timeout_overrides = dict(settings.controller_tool_timeout_overrides or {})
        self.tool_retry_limit = max(0, settings.controller_tool_retry_limit)

        if settings.pubmed_enabled and self.pubmed_client is None:
            self.pubmed_client = PubMedClient(
                api_key=settings.pubmed_api_key or None,
                timeout=settings.pubmed_timeout_seconds,
            )
        if settings.pubmed_enabled and self.pubmed_cache is None:
            self.pubmed_cache = PubMedCache(
                ttl_seconds=settings.pubmed_cache_ttl_seconds
            )

    async def evaluate_case(
        self,
        case_bundle: CaseBundle,
        policy_document_id: str,
    ) -> List[CriterionResult]:
        """Evaluate case using ReAct loop.

        Args:
            case_bundle: Case data with VLM extractions
            policy_document_id: PageIndex document ID for policy

        Returns:
            List of criterion results
        """
        # Set policy document ID in metadata for tool handlers
        case_bundle.metadata["policy_document_id"] = policy_document_id

        criteria = await self._identify_criteria(case_bundle)

        results = []
        for criterion_id in criteria:
            result = await self._evaluate_criterion(
                criterion_id=criterion_id,
                case_bundle=case_bundle,
            )
            results.append(result)

        return results

    async def _evaluate_criterion(
        self,
        criterion_id: str,
        case_bundle: CaseBundle,
    ) -> CriterionResult:
        """Evaluate single criterion with ReAct loop.

        Args:
            criterion_id: Criterion identifier
            case_bundle: Case data

        Returns:
            Criterion result with decision
        """
        # Initialize tool executor
        executor = ToolExecutor(
            retrieval_service=self.retrieval_service,
            case_bundle=case_bundle,
            fts5_service=self.fts5_service,
            treestore_client=self.treestore_client,
            pubmed_client=self.pubmed_client,
            pubmed_cache=self.pubmed_cache,
        )

        # Build messages
        messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {
                "role": "user",
                "content": self._build_user_prompt(criterion_id, case_bundle),
            },
        ]
        tool_history: List[Dict[str, Any]] = []

        # ReAct loop
        reasoning_trace = []
        iteration = 0
        start_time = time.time()

        while iteration < self.max_iterations:
            iteration += 1

            if self.verbose:
                print(f"\n--- Iteration {iteration} ---")

            # Call LLM
            try:
                response = await self.llm.call_with_tools(
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                )
            except LLMClientError as e:
                return self._build_error_result(
                    criterion_id=criterion_id,
                    error=f"LLM call failed: {str(e)}",
                    reasoning_trace=reasoning_trace,
                    case_bundle=case_bundle,
                    latency_ms=int((time.time() - start_time) * 1000),
                    tool_history=tool_history,
                )

            # Add assistant message to history
            assistant_message = {
                "role": "assistant",
                "content": response.get("content"),
            }
            if response.get("tool_calls"):
                assistant_message["tool_calls"] = response["tool_calls"]
            messages.append(assistant_message)

            # Check if LLM called finish()
            if response.get("tool_calls"):
                for tool_call in response["tool_calls"]:
                    if isinstance(tool_call, dict):
                        func_name = tool_call.get("function", {}).get("name")
                        func_args_str = tool_call.get("function", {}).get("arguments", "{}")
                    else:
                        # Handle different tool call formats
                        func_name = getattr(tool_call, "function", {}).get("name", "") if hasattr(tool_call, "function") else ""
                        func_args_str = "{}"

                    if func_name == "finish":
                        try:
                            decision_args = json.loads(func_args_str)
                            # Record finish() call in reasoning trace before returning
                            reasoning_trace.append({
                                "step": iteration,
                                "action": "finish",
                                "input": decision_args,
                                "observation": f"Status: {decision_args.get('status')}, Confidence: {decision_args.get('confidence')}",
                            })
                            tool_history.append(
                                {
                                    "action": "finish",
                                    "success": True,
                                    "latency_ms": 0,
                                    "attempt": 1,
                                    "timeout": False,
                                }
                            )
                            return self._build_result_from_finish(
                                criterion_id=criterion_id,
                                decision_args=decision_args,
                                reasoning_trace=reasoning_trace,
                                messages=messages,
                                latency_ms=int((time.time() - start_time) * 1000),
                                case_bundle=case_bundle,
                                tool_history=tool_history,
                            )
                        except json.JSONDecodeError:
                            return self._build_error_result(
                                criterion_id=criterion_id,
                                error="Failed to parse finish() arguments",
                                reasoning_trace=reasoning_trace,
                                case_bundle=case_bundle,
                                tool_history=tool_history,
                                latency_ms=int((time.time() - start_time) * 1000),
                            )

            # Execute tool calls
            if response.get("tool_calls"):
                tool_results = []
                for tool_call in response["tool_calls"]:
                    # Extract tool call info
                    if isinstance(tool_call, dict):
                        tool_call_id = tool_call.get("id", f"call_{iteration}")
                        func_name = tool_call.get("function", {}).get("name")
                        func_args_str = tool_call.get("function", {}).get("arguments", "{}")
                    else:
                        tool_call_id = f"call_{iteration}"
                        func_name = ""
                        func_args_str = "{}"

                    try:
                        tool_args = json.loads(func_args_str)
                    except json.JSONDecodeError:
                        tool_args = {}

                    if self.verbose:
                        print(f"Tool: {func_name}({tool_args})")

                    # Execute tool with timeout/retry policy
                    timeout_seconds = self._tool_timeout_for(func_name or "")
                    result = await self._execute_tool_call(
                        executor=executor,
                        func_name=func_name or "unknown",
                        tool_args=tool_args,
                        timeout=timeout_seconds,
                        tool_history=tool_history,
                    )

                    if result is None:
                        observation = (
                            f"{func_name or 'tool'} timed out after {timeout_seconds:.2f}s"
                        )
                        reasoning_trace.append(
                            {
                                "step": iteration,
                                "action": func_name or "unknown",
                                "input": tool_args,
                                "observation": observation,
                            }
                        )
                        return self._build_error_result(
                            criterion_id=criterion_id,
                            error=observation,
                            reasoning_trace=reasoning_trace,
                            reason_code="tool_timeout",
                            case_bundle=case_bundle,
                            tool_history=tool_history,
                            latency_ms=int((time.time() - start_time) * 1000),
                        )

                    if self.verbose:
                        result_preview = result[:200] + "..." if len(result) > 200 else result
                        print(f"Result: {result_preview}")

                    # Record in trace
                    reasoning_trace.append({
                        "step": iteration,
                        "action": func_name,
                        "input": tool_args,
                        "observation": result[:500],  # Truncate long results
                    })

                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": func_name,
                        "content": result,
                    })

            # Check if no tool calls and no finish - might be stuck
            if not response.get("tool_calls") and response.get("finish_reason") == "stop":
                # Force finish with uncertain
                return self._build_error_result(
                    criterion_id=criterion_id,
                    error="Agent stopped without calling finish()",
                    reasoning_trace=reasoning_trace,
                    case_bundle=case_bundle,
                    tool_history=tool_history,
                    latency_ms=int((time.time() - start_time) * 1000),
                )

        # Max iterations reached
        return self._build_error_result(
            criterion_id=criterion_id,
            error=f"Max iterations ({self.max_iterations}) reached",
            reasoning_trace=reasoning_trace,
            case_bundle=case_bundle,
            tool_history=tool_history,
            latency_ms=int((time.time() - start_time) * 1000),
        )

    def _build_user_prompt(
        self,
        criterion_id: str,
        case_bundle: CaseBundle,
    ) -> str:
        """Build user prompt for the agent.

        Args:
            criterion_id: Criterion identifier
            case_bundle: Case data

        Returns:
            User prompt string
        """
        # Summarize available case fields
        fields_summary = "\n".join([
            f"- {f.field_name}: {f.value} (confidence: {f.confidence:.2f})"
            for f in case_bundle.fields
        ])

        return f"""
# Task

Evaluate whether this case meets the requirements for criterion: **{criterion_id}**

# Available Case Information

The following fields were extracted from case documents:

{fields_summary if fields_summary else "No fields available."}

# Your Task

1. Use pi_search() to find relevant policy requirements
2. Use facts_get() to retrieve specific case values as needed
3. Compare policy requirements against case facts
4. Call finish() with your determination

Begin your analysis now.
"""

    def _build_result_from_finish(
        self,
        criterion_id: str,
        decision_args: Dict[str, Any],
        reasoning_trace: List[Dict],
        messages: List[Dict],
        latency_ms: int,
        case_bundle: CaseBundle,
        tool_history: List[Dict[str, Any]],
    ) -> CriterionResult:
        """Build CriterionResult from finish() arguments.

        Args:
            criterion_id: Criterion identifier
            decision_args: Arguments from finish() tool call
            reasoning_trace: List of reasoning steps
            messages: Full message history
            latency_ms: Evaluation latency in milliseconds

        Returns:
            CriterionResult object
        """
        # Map status string to enum
        status_map = {
            "met": DecisionStatus.MET,
            "missing": DecisionStatus.MISSING,
            "uncertain": DecisionStatus.UNCERTAIN,
        }
        status = status_map.get(decision_args.get("status", "uncertain"), DecisionStatus.UNCERTAIN)

        # Build confidence breakdown
        confidence = decision_args.get("confidence", 0.0)
        confidence_breakdown = ConfidenceBreakdown(
            c_tree=0.9,  # Could extract from pi_search results if available
            c_span=0.85,
            c_final=confidence,
            c_joint=confidence,
        )

        # Build citation
        policy_version = case_bundle.metadata.get("policy_version_id", "v1.0")
        citation = CitationInfo(
            doc=case_bundle.policy_id,
            version=policy_version,
            section=decision_args.get("policy_section", "Unknown"),
            pages=decision_args.get("policy_pages", []),
        )

        # Build evidence (if provided)
        evidence = None
        if decision_args.get("evidence_doc_id"):
            evidence = EvidenceInfo(
                doc_id=decision_args["evidence_doc_id"],
                page=decision_args.get("evidence_page", 0),
                bbox=[],
                text_excerpt="",
            )

        result = CriterionResult(
            criterion_id=criterion_id,
            status=status,
            evidence=evidence,
            citation=citation,
            rationale=decision_args.get("rationale", "No rationale provided"),
            confidence=confidence,
            confidence_breakdown=confidence_breakdown,
            search_trajectory=[],  # Could extract from tool results
            retrieval_method=RetrievalMethod.PAGEINDEX_LLM,
            reason_code=None if status != DecisionStatus.UNCERTAIN else "agent_uncertain",
            reasoning_trace=[
                ReasoningStep(
                    step=t["step"],
                    action=t["action"],
                    observation=t["observation"][:200] if len(t["observation"]) > 200 else t["observation"],
                )
                for t in reasoning_trace
            ],
        )
        record_confidence_score(confidence)
        self._log_decision_event(
            case_bundle=case_bundle,
            criterion_id=criterion_id,
            status=result.status.value,
            confidence=confidence,
            reason_code=result.reason_code,
            latency_ms=latency_ms,
            tool_history=tool_history,
        )
        return result

    def _build_error_result(
        self,
        criterion_id: str,
        error: str,
        reasoning_trace: List[Dict],
        case_bundle: CaseBundle,
        tool_history: List[Dict[str, Any]],
        reason_code: str = "agent_error",
        latency_ms: Optional[int] = None,
    ) -> CriterionResult:
        """Build error result when agent fails.

        Args:
            criterion_id: Criterion identifier
            error: Error message
            reasoning_trace: Partial reasoning trace

        Returns:
            CriterionResult with UNCERTAIN status
        """
        result = CriterionResult(
            criterion_id=criterion_id,
            status=DecisionStatus.UNCERTAIN,
            evidence=None,
            citation=CitationInfo(doc="N/A", version="N/A", section="N/A", pages=[]),
            rationale=f"Agent error: {error}",
            confidence=0.0,
            confidence_breakdown=ConfidenceBreakdown(
                c_tree=0.0, c_span=0.0, c_final=0.0, c_joint=0.0
            ),
            search_trajectory=[],
            retrieval_method=RetrievalMethod.PAGEINDEX_LLM,
            reason_code=reason_code,
            reasoning_trace=[
                ReasoningStep(
                    step=t["step"],
                    action=t["action"],
                    observation=t["observation"][:200] if len(t["observation"]) > 200 else t["observation"],
                )
                for t in reasoning_trace
            ],
        )
        self._log_decision_event(
            case_bundle=case_bundle,
            criterion_id=criterion_id,
            status=result.status.value,
            confidence=result.confidence,
            reason_code=reason_code,
            latency_ms=latency_ms,
            tool_history=tool_history,
        )
        return result

    async def _identify_criteria(
        self,
        case_bundle: CaseBundle,
    ) -> List[str]:
        """Identify criteria to evaluate.

        Args:
            case_bundle: Case data

        Returns:
            List of criterion identifiers
        """
        explicit_ids = case_bundle.metadata.get("criteria") or []
        if isinstance(explicit_ids, list) and explicit_ids:
            return [str(criterion) for criterion in explicit_ids]

        fallback = case_bundle.metadata.get("criterion_id")
        if isinstance(fallback, str) and fallback:
            return [fallback]

        return [f"{case_bundle.policy_id}:default"]

    def _tool_timeout_for(self, tool_name: str) -> float:
        """Return timeout budget for a tool."""
        return float(self.tool_timeout_overrides.get(tool_name, self.tool_timeout_seconds))

    async def _execute_tool_call(
        self,
        executor: ToolExecutor,
        func_name: str,
        tool_args: Dict[str, Any],
        timeout: float,
        tool_history: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Execute a tool with retry and timeout tracking."""
        attempts = 0
        while attempts <= self.tool_retry_limit:
            attempts += 1
            start = time.perf_counter()
            try:
                payload = await executor.execute(func_name, tool_args, timeout=timeout)
                latency_ms = int((time.perf_counter() - start) * 1000)
                tool_history.append(
                    {
                        "action": func_name,
                        "success": True,
                        "latency_ms": latency_ms,
                        "attempt": attempts,
                        "timeout": False,
                    }
                )
                return payload
            except ToolTimeoutError as exc:
                latency_ms = int((time.perf_counter() - start) * 1000)
                tool_history.append(
                    {
                        "action": func_name,
                        "success": False,
                        "latency_ms": latency_ms,
                        "attempt": attempts,
                        "timeout": True,
                        "error": str(exc),
                    }
                )
                if attempts > self.tool_retry_limit:
                    return None
            except Exception as exc:  # pylint: disable=broad-except
                latency_ms = int((time.perf_counter() - start) * 1000)
                tool_history.append(
                    {
                        "action": func_name,
                        "success": False,
                        "latency_ms": latency_ms,
                        "attempt": attempts,
                        "timeout": False,
                        "error": str(exc),
                    }
                )
                return json.dumps({"success": False, "error": str(exc)})
        return None

    def _log_decision_event(
        self,
        case_bundle: CaseBundle,
        criterion_id: str,
        status: str,
        confidence: float,
        reason_code: Optional[str],
        latency_ms: Optional[int],
        tool_history: List[Dict[str, Any]],
    ) -> None:
        """Emit structured log for downstream observability."""
        extra = {
            "event": "controller_decision",
            "case_id": case_bundle.case_id,
            "policy_id": case_bundle.policy_id,
            "policy_version": case_bundle.metadata.get("policy_version_id"),
            "criterion_id": criterion_id,
            "status": status,
            "confidence": confidence,
            "reason_code": reason_code,
            "latency_ms": latency_ms,
            "tool_sequence": tool_history,
            "prompt_version": self.prompt_version,
        }
        self.logger.info("controller_decision", extra=extra)
