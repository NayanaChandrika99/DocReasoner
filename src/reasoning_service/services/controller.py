"""Controller delegation between heuristic and LLM implementations."""

from __future__ import annotations

import random
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from retrieval.service import RetrievalResult

from reasoning_service.config import settings
from reasoning_service.observability.react_metrics import (
    record_ab_assignment,
    record_evaluation,
    record_fallback,
)
from reasoning_service.services.react_controller import ReActController as LLMReActController
from reasoning_service.models.schema import (
    CaseBundle,
    ConfidenceBreakdown,
    CriterionResult,
    DecisionStatus,
    CitationInfo,
    EvidenceInfo,
    RetrievalMethod,
)
from reasoning_service.utils.logging import get_logger


class ActionType(str, Enum):
    """Types of actions the controller can take."""
    THINK = "think"
    RETRIEVE = "retrieve"
    READ = "read"
    LINK_EVIDENCE = "link_evidence"
    DECIDE = "decide"


class ReActStep:
    """A single step in the ReAct loop."""
    
    def __init__(
        self,
        action: ActionType,
        input_data: Any,
        observation: Optional[Any] = None
    ):
        self.action = action
        self.input_data = input_data
        self.observation = observation


class HeuristicReActController:
    """Rule-based controller used for CLI compatibility and fallback."""
    
    def __init__(self, retrieval_service: Any, llm_client: Optional[Any] = None):
        """Initialize ReAct controller.
        
        Args:
            retrieval_service: Service for document retrieval
            llm_client: LLM client for generating reasoning steps
        """
        self.retrieval_service = retrieval_service
        self.llm_client = llm_client  # TODO: Initialize actual LLM client
        self.max_iterations = settings.controller_max_iterations
        self.temperature = settings.controller_temperature
    
    async def evaluate_case(
        self,
        case_bundle: CaseBundle,
        policy_document_id: str
    ) -> list[CriterionResult]:
        """Evaluate a case against policy criteria using ReAct loop.
        
        Args:
            case_bundle: Case data with VLM extractions
            policy_document_id: PageIndex document ID for policy
            
        Returns:
            List of criterion results with citations and evidence
        """
        criteria = await self._identify_criteria(case_bundle, policy_document_id)

        results: List[CriterionResult] = []
        for criterion_id in criteria:
            result = await self._evaluate_criterion(
                criterion_id=criterion_id,
                case_bundle=case_bundle,
                policy_document_id=policy_document_id,
            )
            results.append(result)
        return results
    
    async def _identify_criteria(
        self,
        case_bundle: CaseBundle,
        policy_document_id: str
    ) -> list[str]:
        """Identify relevant criteria from policy.
        
        Args:
            case_bundle: Case data
            policy_document_id: Policy document ID
            
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
    
    async def _evaluate_criterion(
        self,
        criterion_id: str,
        case_bundle: CaseBundle,
        policy_document_id: str
    ) -> CriterionResult:
        """Evaluate a single criterion using ReAct loop.
        
        Args:
            criterion_id: Criterion identifier
            case_bundle: Case data
            policy_document_id: Policy document ID
            
        Returns:
            Criterion result with decision and evidence
        """
        steps: List[ReActStep] = []
        question = f"What evidence is needed for {criterion_id}?"

        thinking = await self._think(question, case_bundle)
        steps.append(
            ReActStep(
                ActionType.THINK,
                {"question": question, "criterion": criterion_id},
                observation=thinking["plan"],
            )
        )

        retrieval_result: RetrievalResult = await self.retrieval_service.retrieve(
            document_id=policy_document_id,
            query=thinking.get("query", question),
            top_k=3,
        )
        node_refs = getattr(retrieval_result, "node_refs", [])
        spans = getattr(retrieval_result, "spans", [])
        steps.append(
            ReActStep(
                ActionType.RETRIEVE,
                {"query": thinking.get("query", question)},
                observation=f"nodes={len(node_refs)}, spans={len(spans)}",
            )
        )

        if retrieval_result.error:
            rationale = f"Retrieval error: {retrieval_result.error}"
            steps.append(
                ReActStep(
                    ActionType.DECIDE,
                    {"status": DecisionStatus.UNCERTAIN.value},
                    observation=rationale,
                )
            )
            confidence_breakdown = self._build_confidence_breakdown(
                retrieval_confidence=retrieval_result.confidence,
                evidence_confidence=0.0,
                status=DecisionStatus.UNCERTAIN,
            )
            return self._build_result(
                criterion_id=criterion_id,
                case_bundle=case_bundle,
                retrieval=retrieval_result,
                decision_status=DecisionStatus.UNCERTAIN,
                rationale=rationale,
                confidence=confidence_breakdown.c_joint,
                confidence_breakdown=confidence_breakdown,
                evidence=None,
                reason_code=retrieval_result.reason_code or "retrieval_error",
                steps=steps,
            )

        span_texts = [span.text for span in spans]
        requirements = await self._read_requirements(span_texts)
        steps.append(
            ReActStep(
                ActionType.READ,
                {"span_count": len(span_texts)},
                observation=f"requirements={len(requirements.get('requirements', []))}",
            )
        )

        evidence = await self._link_evidence(case_bundle, requirements)
        steps.append(
            ReActStep(
                ActionType.LINK_EVIDENCE,
                {"field_count": len(case_bundle.fields)},
                observation="matched" if evidence.get("matched") else "no_match",
            )
        )

        decision_payload = await self._decide(requirements, evidence)
        steps.append(
            ReActStep(
                ActionType.DECIDE,
                {"status": decision_payload["status"].value},
                observation=decision_payload["rationale"],
            )
        )

        confidence_breakdown = self._build_confidence_breakdown(
            retrieval_confidence=retrieval_result.confidence,
            evidence_confidence=evidence.get("confidence", 0.0),
            status=decision_payload["status"],
        )

        return self._build_result(
            criterion_id=criterion_id,
            case_bundle=case_bundle,
            retrieval=retrieval_result,
            decision_status=decision_payload["status"],
            rationale=self._compose_rationale(decision_payload["rationale"], steps),
            confidence=confidence_breakdown.c_joint,
            confidence_breakdown=confidence_breakdown,
            evidence=evidence.get("evidence_info"),
            reason_code=decision_payload.get("reason_code"),
            steps=steps,
        )

    def _map_retrieval_method(self, method: str) -> RetrievalMethod:
        method = (method or "pageindex-llm").lower()
        if method == "pageindex-hybrid":
            return RetrievalMethod.PAGEINDEX_HYBRID
        if method == "bm25-fallback":
            return RetrievalMethod.BM25_RERANKER
        return RetrievalMethod.PAGEINDEX_LLM
    
    async def _think(self, question: str, context: Any) -> dict[str, Any]:
        """Reason about the next retrieval query.

        Currently uses heuristic extraction from the question/case metadata.
        """
        case_metadata = getattr(context, "metadata", {}) or {}
        hint = case_metadata.get("reasoning_hint")
        criterion_focus = question.replace("What evidence is needed for", "").strip(" ?")
        query = hint or criterion_focus
        plan = f"Retrieve policy language describing {criterion_focus}"
        return {"query": query, "plan": plan, "thinking": f"Focus on {criterion_focus}"}
    
    async def _read_requirements(self, spans: list[str]) -> dict[str, Any]:
        """Extract requirement-style statements from the retrieved spans."""
        requirements: List[str] = []
        keywords: List[str] = []
        for span in spans:
            normalized = span.strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if any(token in lowered for token in ("must", "shall", "require")):
                requirements.append(normalized)
            tokens = [tok.strip(",.") for tok in lowered.split()]
            for token in tokens:
                if token in ("must", "shall", "require", "required"):
                    continue
                if len(token) > 3:
                    keywords.append(token)
        return {"requirements": requirements or spans, "keywords": keywords}
    
    async def _link_evidence(
        self,
        case_bundle: CaseBundle,
        requirements: dict[str, Any]
    ) -> dict[str, Any]:
        """Match VLM fields to the derived requirements."""
        requirement_blob = " ".join(requirements.get("requirements", []))
        lowered_blob = requirement_blob.lower()

        for field in case_bundle.fields:
            value = str(field.value) if field.value is not None else ""
            lowered_value = value.lower()
            if lowered_value and lowered_value in lowered_blob:
                return {
                    "evidence_info": EvidenceInfo(
                        doc_id=field.doc_id,
                        page=field.page,
                        bbox=field.bbox,
                        text_excerpt=value,
                    ),
                    "matched": True,
                    "confidence": 0.9,
                }

        return {"matched": False, "confidence": 0.35}
    
    async def _decide(
        self,
        requirements: dict[str, Any],
        evidence: dict[str, Any]
    ) -> dict[str, Any]:
        """Make the final decision based on requirements and evidence."""
        matched = evidence.get("matched", False)
        has_requirements = bool(requirements.get("requirements"))

        if matched and has_requirements:
            return {
                "status": DecisionStatus.MET,
                "rationale": "Case evidence aligns with the retrieved policy requirement.",
                "reason_code": None,
            }
        if has_requirements:
            return {
                "status": DecisionStatus.MISSING,
                "rationale": "Policy requirement not satisfied by provided evidence.",
                "reason_code": "missing_evidence",
            }
        return {
            "status": DecisionStatus.UNCERTAIN,
            "rationale": "Insufficient policy context to reach a determination.",
            "reason_code": "insufficient_policy_context",
        }

    def _compose_rationale(self, decision_rationale: str, steps: List[ReActStep]) -> str:
        step_fragments = []
        for idx, step in enumerate(steps, start=1):
            observation = step.observation
            if isinstance(observation, dict):
                observation_text = ", ".join(f"{k}={v}" for k, v in observation.items())
            else:
                observation_text = str(observation)
            step_fragments.append(f"{idx}.{step.action.value}:{observation_text}")
        trace_summary = " | ".join(step_fragments)
        return f"{decision_rationale} Reasoning trace: {trace_summary}"

    def _build_result(
        self,
        criterion_id: str,
        case_bundle: CaseBundle,
        retrieval: RetrievalResult,
        decision_status: DecisionStatus,
        rationale: str,
        confidence: float,
        confidence_breakdown: ConfidenceBreakdown,
        evidence: Optional[EvidenceInfo],
        reason_code: Optional[str],
        steps: List[ReActStep],
    ) -> CriterionResult:
        citation = self._build_citation(case_bundle, retrieval)
        return CriterionResult(
            criterion_id=criterion_id,
            status=decision_status,
            evidence=evidence,
            citation=citation,
            rationale=rationale,
            confidence=confidence,
            confidence_breakdown=confidence_breakdown,
            search_trajectory=getattr(retrieval, "search_trajectory", []),
            retrieval_method=self._map_retrieval_method(getattr(retrieval, "retrieval_method", "pageindex-llm")),
            reason_code=reason_code,
            reasoning_trace=self._serialize_steps(steps),
        )

    def _build_citation(self, case_bundle: CaseBundle, retrieval: RetrievalResult) -> CitationInfo:
        node_refs = getattr(retrieval, "node_refs", [])
        section = node_refs[0].title if node_refs and node_refs[0].title else "N/A"
        pages = node_refs[0].pages if node_refs else []
        version = case_bundle.metadata.get("policy_version", "v1.0")
        return CitationInfo(
            doc=case_bundle.policy_id,
            version=version,
            section=section,
            pages=pages,
        )

    def _build_confidence_breakdown(
        self,
        retrieval_confidence: float,
        evidence_confidence: float,
        status: DecisionStatus,
    ) -> ConfidenceBreakdown:
        c_tree = max(0.0, min(1.0, retrieval_confidence or 0.0))
        c_final_map = {
            DecisionStatus.MET: 0.95,
            DecisionStatus.MISSING: 0.9,
            DecisionStatus.UNCERTAIN: 0.6,
        }
        c_final = c_final_map[status]

        if evidence_confidence:
            c_span = max(0.3, min(1.0, evidence_confidence))
        else:
            c_span = 0.85 if status != DecisionStatus.UNCERTAIN else 0.6

        c_joint = round(min(1.0, c_tree * c_span * c_final), 3)
        return ConfidenceBreakdown(c_tree=c_tree, c_span=c_span, c_final=c_final, c_joint=c_joint)

    def _serialize_steps(self, steps: List[ReActStep]) -> List[Dict[str, str]]:
        serialized: List[Dict[str, str]] = []
        for idx, step in enumerate(steps, start=1):
            observation = step.observation
            if isinstance(observation, dict):
                observation_text = ", ".join(f"{k}={v}" for k, v in observation.items())
            else:
                observation_text = str(observation)
            serialized.append(
                {
                    "step": idx,
                    "action": step.action.value,
                    "observation": observation_text,
                }
            )
        return serialized


class ReActController:
    """Delegates between the heuristic and LLM controllers."""

    def __init__(
        self,
        retrieval_service: Any,
        llm_client: Optional[Any] = None,
        fts5_service: Optional[Any] = None,
    ):
        self.logger = get_logger(__name__)
        self.retrieval_service = retrieval_service
        self._heuristic = HeuristicReActController(retrieval_service=retrieval_service)
        self._llm_client = llm_client
        self._fts5_service = fts5_service
        self._llm_controller: Optional[LLMReActController] = None
        self._llm_init_error: Optional[str] = None
        self.shadow_mode = settings.react_shadow_mode
        self.use_llm = settings.react_use_llm_controller
        self.fallback_enabled = settings.react_fallback_enabled
        self.ab_ratio = settings.react_ab_test_ratio
        self._rng = random.Random()

        if self._llm_requested():
            self._initialize_llm_controller()

    async def evaluate_case(
        self,
        case_bundle: CaseBundle,
        policy_document_id: str,
    ) -> List[CriterionResult]:
        """Evaluate a case using the configured controller strategy."""
        self._ensure_llm_controller()
        mode = self._determine_mode()

        if mode == "shadow":
            heuristic_results = await self._run_heuristic(
                case_bundle, policy_document_id, mode="shadow"
            )
            llm_results = await self._maybe_run_llm(
                case_bundle, policy_document_id, mode="shadow"
            )
            if llm_results is not None:
                self._log_shadow_diff(heuristic_results, llm_results)
            return heuristic_results

        if mode == "llm":
            try:
                return await self._run_llm(case_bundle, policy_document_id, mode="primary")
            except Exception as exc:
                self.logger.error(
                    "LLM controller failed, evaluating fallback",
                    exc_info=True,
                    extra={"reason": str(exc)},
                )
                record_fallback("llm_error")
                if not self.fallback_enabled:
                    raise
                return await self._run_heuristic(
                    case_bundle, policy_document_id, mode="fallback"
                )

        # Default heuristic path.
        return await self._run_heuristic(case_bundle, policy_document_id, mode="primary")

    def _llm_requested(self) -> bool:
        return bool(
            self.use_llm
            or self.shadow_mode
            or (self.ab_ratio and self.ab_ratio > 0.0)
        )

    def _ensure_llm_controller(self) -> None:
        """Instantiate the LLM controller lazily if needed."""
        if self._llm_controller or not self._llm_requested():
            return
        self._initialize_llm_controller()

    def _initialize_llm_controller(self) -> None:
        """Create the LLM controller instance."""
        try:
            self._llm_controller = LLMReActController(
                llm_client=self._llm_client,
                retrieval_service=self.retrieval_service,
                fts5_service=self._fts5_service,
            )
            self._llm_init_error = None
        except Exception as exc:
            self._llm_init_error = str(exc)
            self._llm_controller = None
            self.logger.error(
                "Failed to initialize LLM controller",
                extra={"error": self._llm_init_error},
            )

    def _determine_mode(self) -> str:
        """Select operating mode for the current request."""
        if self.shadow_mode and self._llm_controller:
            return "shadow"

        if self.use_llm and self._llm_controller:
            return "llm"

        if self.ab_ratio > 0 and self._llm_controller:
            bucket = "llm" if self._rng.random() < self.ab_ratio else "heuristic"
            record_ab_assignment(bucket)
            return "llm" if bucket == "llm" else "heuristic"

        if self._llm_init_error and self.use_llm:
            self.logger.warning(
                "LLM controller requested but unavailable",
                extra={"error": self._llm_init_error},
            )

        return "heuristic"

    async def _run_heuristic(
        self,
        case_bundle: CaseBundle,
        policy_document_id: str,
        mode: str,
    ) -> List[CriterionResult]:
        start = time.time()
        results = await self._heuristic.evaluate_case(case_bundle, policy_document_id)
        self._record_metrics("heuristic", mode, results, start)
        return results

    async def _run_llm(
        self,
        case_bundle: CaseBundle,
        policy_document_id: str,
        mode: str,
    ) -> List[CriterionResult]:
        if not self._llm_controller:
            raise RuntimeError("LLM controller unavailable")
        start = time.time()
        results = await self._llm_controller.evaluate_case(case_bundle, policy_document_id)
        self._record_metrics("llm", mode, results, start)
        return results

    async def _maybe_run_llm(
        self,
        case_bundle: CaseBundle,
        policy_document_id: str,
        mode: str,
    ) -> Optional[List[CriterionResult]]:
        if not self._llm_controller:
            return None
        try:
            return await self._run_llm(case_bundle, policy_document_id, mode=mode)
        except Exception as exc:
            self.logger.error(
                "Shadow mode LLM evaluation failed",
                exc_info=True,
                extra={"reason": str(exc)},
            )
            record_fallback("shadow_llm_error")
            return None

    def _record_metrics(
        self,
        controller_label: str,
        mode: str,
        results: List[CriterionResult],
        start_time: float,
    ) -> None:
        statuses = [result.status.value for result in results]
        latency = time.time() - start_time
        record_evaluation(
            controller=controller_label,
            mode=mode,
            statuses=statuses,
            latency_seconds=latency,
        )

    def _log_shadow_diff(
        self,
        heuristic_results: List[CriterionResult],
        llm_results: List[CriterionResult],
    ) -> None:
        llm_map = {result.criterion_id: result for result in llm_results}
        for heuristic in heuristic_results:
            counterpart = llm_map.get(heuristic.criterion_id)
            if not counterpart:
                self.logger.warning(
                    "Shadow mode missing matching criterion",
                    extra={"criterion_id": heuristic.criterion_id},
                )
                continue

            if (
                heuristic.status != counterpart.status
                or abs(heuristic.confidence - counterpart.confidence) > 0.05
            ):
                self.logger.info(
                    "Shadow comparison mismatch",
                    extra={
                        "criterion_id": heuristic.criterion_id,
                        "heuristic_status": heuristic.status.value,
                        "heuristic_confidence": heuristic.confidence,
                        "llm_status": counterpart.status.value,
                        "llm_confidence": counterpart.confidence,
                    },
                )
