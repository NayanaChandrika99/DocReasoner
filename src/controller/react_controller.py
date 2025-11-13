"""
Lightweight ReAct-style controller that consumes retrieval outputs and emits
strict JSON decisions with reasoning traces. Uses policy-specific validators
for structured business rule evaluation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from controller.validators import LumbarMRIValidator
from retrieval.service import RetrievalResult


@dataclass
class Citation:
    policy_id: str
    version: str
    section_path: str
    pages: Sequence[int]


@dataclass
class ConfidenceBreakdown:
    c_tree: float
    c_span: float
    c_final: float

    @property
    def c_joint(self) -> float:
        return self.c_tree * self.c_span * self.c_final


@dataclass
class ReasoningStep:
    step: int
    action: str
    observation: str


@dataclass
class Decision:
    criterion_id: str
    status: str
    citation: Optional[Citation]
    rationale: str
    confidence: ConfidenceBreakdown
    search_trajectory: List[str]
    reasoning_trace: List[ReasoningStep]
    retrieval_method: str
    reason_code: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "criterion_id": self.criterion_id,
            "status": self.status,
            "citation": asdict(self.citation) if self.citation else None,
            "rationale": self.rationale,
            "confidence": {
                "c_tree": self.confidence.c_tree,
                "c_span": self.confidence.c_span,
                "c_final": self.confidence.c_final,
                "c_joint": self.confidence.c_joint,
            },
            "search_trajectory": self.search_trajectory,
            "reasoning_trace": [asdict(step) for step in self.reasoning_trace],
            "retrieval_method": self.retrieval_method,
        }
        if self.reason_code:
            payload["reason_code"] = self.reason_code
        if self.error:
            payload["error"] = self.error
        return payload


class ReActController:
    def __init__(
        self, model_name: str = "react-controller", abstain_threshold: float = 0.65
    ) -> None:
        self.model_name = model_name
        self.abstain_threshold = abstain_threshold
        self.validator = LumbarMRIValidator(min_confidence_threshold=abstain_threshold)

    def decide(self, case_bundle: Dict[str, Any], retrieval: RetrievalResult) -> Decision:
        criterion_id = case_bundle.get("criterion_id", "unspecified-criterion")
        reasoning_trace: List[ReasoningStep] = []
        status = "uncertain"
        reason_code = retrieval.reason_code
        rationale = "Insufficient evidence."

        if retrieval.error:
            reasoning_trace.append(
                ReasoningStep(
                    step=1,
                    action="retrieval",
                    observation=f"Retrieval error: {retrieval.error}",
                )
            )
            confidence = ConfidenceBreakdown(0.0, 0.0, 0.0)
            return Decision(
                criterion_id=criterion_id,
                status="uncertain",
                citation=None,
                rationale="Retrieval failed; routing to human review.",
                confidence=confidence,
                search_trajectory=retrieval.search_trajectory,
                reasoning_trace=reasoning_trace,
                retrieval_method=retrieval.retrieval_method,
                reason_code=reason_code or "retrieval_error",
                error=retrieval.error,
            )

        reasoning_trace.append(
            ReasoningStep(
                step=1, action="search", observation=f"Evaluated nodes: {len(retrieval.node_refs)}"
            )
        )

        # Use policy-specific validator
        facts = case_bundle.get("case_bundle", {}).get("facts", [])
        validation_result = self.validator.validate_criterion(criterion_id, facts)

        reasoning_trace.append(
            ReasoningStep(
                step=2,
                action="validate",
                observation=f"Validated {len(validation_result.validations)} criteria: {validation_result.status}",
            )
        )

        status = validation_result.status
        rationale = validation_result.rationale
        reason_code = validation_result.reason_code or reason_code

        # Build confidence from validation result
        confidence = self._build_confidence_from_validation(retrieval.confidence, validation_result)

        citation = self._build_citation(case_bundle, retrieval)
        reasoning_trace.append(
            ReasoningStep(
                step=3,
                action="decide",
                observation=f"Status: {status}, conf={confidence.c_joint:.2f}",
            )
        )

        return Decision(
            criterion_id=criterion_id,
            status=status,
            citation=citation,
            rationale=rationale,
            confidence=confidence,
            search_trajectory=retrieval.search_trajectory,
            reasoning_trace=reasoning_trace,
            retrieval_method=retrieval.retrieval_method,
            reason_code=reason_code,
        )

    def _build_confidence_from_validation(
        self, retrieval_confidence: float, validation_result: Any
    ) -> ConfidenceBreakdown:
        """Build confidence breakdown from validation result."""
        c_tree = retrieval_confidence
        c_span = validation_result.overall_confidence

        # Map status to c_final
        if validation_result.status == "ready":
            c_final = 0.95
        elif validation_result.status == "not_ready":
            c_final = 0.90
        else:  # uncertain
            c_final = 0.60

        return ConfidenceBreakdown(c_tree=c_tree, c_span=c_span, c_final=c_final)

    def _build_citation(
        self, case_bundle: Dict[str, Any], retrieval: RetrievalResult
    ) -> Optional[Citation]:
        policy = case_bundle.get("policy", {})
        section_path = policy.get("section_path") or (
            retrieval.node_refs[0].title if retrieval.node_refs else None
        )
        pages = retrieval.node_refs[0].pages if retrieval.node_refs else []
        if not section_path and not pages:
            return None
        return Citation(
            policy_id=policy.get("policy_id", "unknown-policy"),
            version=policy.get("version_id", "unknown-version"),
            section_path=str(section_path),
            pages=pages,
        )
