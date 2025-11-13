"""API request/response schemas."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class DecisionStatus(str, Enum):
    """Status of a criterion evaluation."""
    MET = "met"
    MISSING = "missing"
    UNCERTAIN = "uncertain"


class RetrievalMethod(str, Enum):
    """Method used for retrieval."""
    PAGEINDEX_LLM = "pageindex-llm"
    PAGEINDEX_HYBRID = "pageindex-hybrid"
    BM25_RERANKER = "bm25+reranker"


class ConfidenceBreakdown(BaseModel):
    """Confidence components for a decision."""

    c_tree: float = Field(ge=0.0, le=1.0, description="Retrieval confidence")
    c_span: float = Field(ge=0.0, le=1.0, description="Span alignment confidence")
    c_final: float = Field(ge=0.0, le=1.0, description="Decision confidence")
    c_joint: float = Field(ge=0.0, le=1.0, description="Joint confidence score")


class ReasoningStep(BaseModel):
    """Single ReAct reasoning step."""

    step: int = Field(ge=1, description="Step number")
    action: str = Field(description="Action name (think/retrieve/read/link_evidence/decide)")
    observation: str = Field(description="Resulting observation for the action")


class VLMField(BaseModel):
    """A single field extracted by VLM with provenance."""
    
    field_name: str = Field(description="Name of the extracted field")
    value: Any = Field(description="Extracted value")
    confidence: float = Field(ge=0.0, le=1.0, description="VLM confidence score")
    doc_id: str = Field(description="Source document identifier")
    page: int = Field(ge=1, description="Page number (1-indexed)")
    bbox: list[float] = Field(description="Bounding box [x0, y0, x1, y1]")
    field_class: Optional[str] = Field(default=None, description="Classification of field type")
    
    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, v: list[float]) -> list[float]:
        """Ensure bbox has 4 coordinates."""
        if len(v) != 4:
            raise ValueError("bbox must have exactly 4 coordinates [x0, y0, x1, y1]")
        return v


class CaseBundle(BaseModel):
    """Complete case data with VLM extractions."""
    
    case_id: str = Field(description="Unique case identifier")
    fields: list[VLMField] = Field(description="Extracted fields with provenance")
    policy_id: str = Field(description="Applicable policy identifier")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional case metadata")


class CitationInfo(BaseModel):
    """Policy citation with section and page references."""
    
    doc: str = Field(description="Policy document ID (e.g., LCD-33822)")
    version: str = Field(description="Policy version (e.g., 2025-Q1)")
    section: str = Field(description="Section path (e.g., 3.b)")
    pages: list[int] = Field(description="Referenced page numbers")


class EvidenceInfo(BaseModel):
    """Evidence from source documents."""
    
    doc_id: str = Field(description="Source document identifier")
    page: int = Field(ge=1, description="Page number")
    bbox: Optional[list[float]] = Field(default=None, description="Bounding box [x0, y0, x1, y1]")
    text_excerpt: Optional[str] = Field(default=None, description="Relevant text excerpt")


class CriterionResult(BaseModel):
    """Result of evaluating a single criterion."""
    
    criterion_id: str = Field(description="Criterion identifier (e.g., LCD-33822:Sec3.b)")
    status: DecisionStatus = Field(description="Decision status: met, missing, or uncertain")
    evidence: Optional[EvidenceInfo] = Field(default=None, description="Supporting evidence from source docs")
    citation: CitationInfo = Field(description="Policy citation with section and pages")
    rationale: str = Field(description="Human-readable explanation of the decision")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    confidence_breakdown: Optional[ConfidenceBreakdown] = Field(
        default=None,
        description="Optional multi-factor confidence breakdown"
    )
    search_trajectory: list[str] = Field(
        default_factory=list,
        description="Node path taken during tree search (e.g., ['1', '1.1', '1.1.a'])"
    )
    retrieval_method: RetrievalMethod = Field(description="Method used for retrieval")
    reason_code: Optional[str] = Field(
        default=None,
        description="Code explaining uncertainty or errors"
    )
    reasoning_trace: list[ReasoningStep] = Field(
        default_factory=list,
        description="ReAct reasoning trace for the decision"
    )


class AuthReviewRequest(BaseModel):
    """Request for authorization review."""
    
    case_bundle: CaseBundle = Field(description="Case data with VLM extractions")
    self_consistency: bool = Field(
        default=False,
        description="Enable self-consistency sampling for high-impact decisions"
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional options for the review"
    )


class AuthReviewResponse(BaseModel):
    """Response from authorization review."""
    
    case_id: str = Field(description="Case identifier")
    results: list[CriterionResult] = Field(description="Results for each criterion")
    policy_version_used: str = Field(description="Policy version used for evaluation")
    controller_version: str = Field(description="ReAct controller version")
    prompt_id: str = Field(description="Prompt version identifier")
    processing_time_ms: int = Field(description="Total processing time in milliseconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class QAIssue(BaseModel):
    """A quality assurance issue found in the case."""
    
    issue_type: str = Field(description="Type of issue (e.g., contradiction, missing_attachment)")
    description: str = Field(description="Human-readable description")
    severity: str = Field(description="Severity level: high, medium, low")
    affected_fields: list[str] = Field(default_factory=list, description="Fields involved in the issue")
    evidence: list[EvidenceInfo] = Field(default_factory=list, description="Supporting evidence")


class QARequest(BaseModel):
    """Request for document-level quality assurance."""
    
    case_bundle: CaseBundle = Field(description="Case data to check")


class QAResponse(BaseModel):
    """Response from quality assurance check."""
    
    case_id: str = Field(description="Case identifier")
    issues: list[QAIssue] = Field(description="Detected quality issues")
    clean: bool = Field(description="True if no issues found")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
