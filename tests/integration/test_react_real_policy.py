"""Integration tests with real PageIndex calls (requires API key)."""

import os
import pytest

from reasoning_service.models.schema import CaseBundle, VLMField, DecisionStatus
from reasoning_service.services.react_controller import ReActController
from reasoning_service.services.llm_client import LLMClient
from reasoning_service.services.retrieval import RetrievalService


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"),
    reason="Requires OPENAI_API_KEY or ANTHROPIC_API_KEY",
)
@pytest.mark.skipif(
    not os.getenv("PAGEINDEX_API_KEY"),
    reason="Requires PAGEINDEX_API_KEY",
)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_react_with_pageindex():
    """Test real ReAct controller with live PageIndex and LLM."""
    # Determine LLM provider from environment
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # Real LLM client
    llm_client = LLMClient(
        provider=provider,
        model=model,
        temperature=0.1,
    )

    # Real retrieval service
    retrieval_service = RetrievalService()

    # Sample case
    case = CaseBundle(
        case_id="integration-test-001",
        policy_id="LCD-L34220",
        fields=[
            VLMField(
                field_name="patient_age",
                value="45",
                confidence=0.95,
                doc_id="doc1",
                page=1,
                bbox=[0, 0, 100, 100],
                field_class="age",
            ),
            VLMField(
                field_name="physical_therapy_duration",
                value="8 weeks",
                confidence=0.92,
                doc_id="doc1",
                page=2,
                bbox=[0, 0, 100, 100],
                field_class="duration",
            ),
        ],
        metadata={
            "criteria": ["lumbar-mri-pt"],
            "policy_document_id": "pi-cmhppdets02r308pjqnaukvnt",  # Lumbar MRI policy
        },
    )

    controller = ReActController(
        llm_client=llm_client,
        retrieval_service=retrieval_service,
        max_iterations=10,
        verbose=True,  # Print trace for debugging
    )

    results = await controller.evaluate_case(
        case_bundle=case,
        policy_document_id="pi-cmhppdets02r308pjqnaukvnt",
    )

    assert len(results) == 1
    result = results[0]

    # Should successfully evaluate
    assert result.status in [DecisionStatus.MET, DecisionStatus.MISSING, DecisionStatus.UNCERTAIN]
    assert result.confidence > 0.0
    assert len(result.reasoning_trace) > 0
    assert result.citation.pages

    # Print for manual inspection
    print(f"\nStatus: {result.status.value}")
    print(f"Confidence: {result.confidence}")
    print(f"Rationale: {result.rationale}")
    print(f"Citation: Section {result.citation.section}, Pages {result.citation.pages}")
    print(f"\nReasoning Trace ({len(result.reasoning_trace)} steps):")
    for step in result.reasoning_trace:
        print(f"  {step.step}. {step.action}: {step.observation[:100]}...")


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"),
    reason="Requires OPENAI_API_KEY or ANTHROPIC_API_KEY",
)
@pytest.mark.skipif(
    not os.getenv("PAGEINDEX_API_KEY"),
    reason="Requires PAGEINDEX_API_KEY",
)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_react_uncertain_case():
    """Test real ReAct controller with insufficient information."""
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    llm_client = LLMClient(provider=provider, model=model, temperature=0.1)
    retrieval_service = RetrievalService()

    # Case with missing critical information
    case = CaseBundle(
        case_id="integration-test-002",
        policy_id="LCD-L34220",
        fields=[
            VLMField(
                field_name="patient_age",
                value="45",
                confidence=0.95,
                doc_id="doc1",
                page=1,
                bbox=[0, 0, 100, 100],
                field_class="age",
            ),
            # Missing PT duration - should lead to uncertain
        ],
        metadata={
            "criteria": ["lumbar-mri-pt"],
            "policy_document_id": "pi-cmhppdets02r308pjqnaukvnt",
        },
    )

    controller = ReActController(
        llm_client=llm_client,
        retrieval_service=retrieval_service,
        max_iterations=10,
        verbose=True,
    )

    results = await controller.evaluate_case(
        case_bundle=case,
        policy_document_id="pi-cmhppdets02r308pjqnaukvnt",
    )

    assert len(results) == 1
    result = results[0]

    # Should return uncertain due to missing information
    assert result.status == DecisionStatus.UNCERTAIN
    assert result.confidence < 0.65
    assert "uncertain" in result.rationale.lower() or result.reason_code == "agent_uncertain"

