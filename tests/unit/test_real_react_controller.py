"""Tests for real ReAct controller with LLM-driven reasoning."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from reasoning_service.models.schema import CaseBundle, VLMField, DecisionStatus
from reasoning_service.services.react_controller import ReActController
from reasoning_service.services.llm_client import LLMClient
from reasoning_service.services.tool_handlers import ToolExecutor, ToolTimeoutError
from retrieval.service import RetrievalResult, NodeReference, Span


@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    client = AsyncMock(spec=LLMClient)
    return client


@pytest.fixture
def mock_retrieval_service():
    """Mock retrieval service."""
    service = AsyncMock()
    return service


@pytest.fixture
def sample_case():
    """Sample case bundle."""
    return CaseBundle(
        case_id="test-123",
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
        metadata={"criteria": ["lumbar-mri-pt"], "policy_document_id": "pi-test-doc-123"},
    )


@pytest.fixture
def sample_retrieval_result():
    """Sample retrieval result."""
    return RetrievalResult(
        node_refs=[
            NodeReference(
                node_id="1.2.3",
                pages=[5, 6],
                title="Section 2.3: Lumbar MRI Indications",
                summary="Requirements for lumbar MRI authorization",
            )
        ],
        spans=[
            Span(
                node_id="1.2.3",
                page_index=5,
                text="Requires age ≥18, conservative treatment ≥6 weeks, approved ICD-10 code",
            )
        ],
        search_trajectory=["1", "1.2", "1.2.3"],
        retrieval_method="pageindex-llm",
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_react_loop_successful_met(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
    sample_retrieval_result,
):
    """Test successful evaluation returning MET status."""
    # Mock LLM responses
    mock_llm_client.call_with_tools.side_effect = [
        # First call: Agent searches policy
        {
            "role": "assistant",
            "content": "I need to search for PT requirements",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "pi_search",
                        "arguments": json.dumps({"query": "physical therapy duration requirements"}),
                    },
                }
            ],
            "finish_reason": "tool_calls",
        },
        # Second call: Agent gets patient age
        {
            "role": "assistant",
            "content": "Now let me check patient age",
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "facts_get",
                        "arguments": json.dumps({"field_name": "patient_age"}),
                    },
                }
            ],
            "finish_reason": "tool_calls",
        },
        # Third call: Agent finishes
        {
            "role": "assistant",
            "content": "Case meets all requirements",
            "tool_calls": [
                {
                    "id": "call_3",
                    "type": "function",
                    "function": {
                        "name": "finish",
                        "arguments": json.dumps({
                            "status": "met",
                            "rationale": "Patient completed 8 weeks PT, exceeds 6 week minimum",
                            "confidence": 0.9,
                            "policy_section": "Section 2.3",
                            "policy_pages": [5, 6],
                            "evidence_doc_id": "doc1",
                            "evidence_page": 2,
                        }),
                    },
                }
            ],
            "finish_reason": "tool_calls",
        },
    ]

    # Mock retrieval service
    mock_retrieval_service.retrieve.return_value = sample_retrieval_result

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=5,
    )

    results = await controller.evaluate_case(
        case_bundle=sample_case,
        policy_document_id="pi-test-doc-123",
    )

    assert len(results) == 1
    assert results[0].status == DecisionStatus.MET
    assert results[0].confidence >= 0.8
    assert "8 weeks" in results[0].rationale.lower() or "pt" in results[0].rationale.lower()
    assert len(results[0].reasoning_trace) == 3  # Three tool calls
    assert results[0].reasoning_trace[0].action == "pi_search"
    assert results[0].reasoning_trace[1].action == "facts_get"
    assert results[0].reasoning_trace[2].action == "finish"


@pytest.mark.asyncio
async def test_react_loop_uncertain_low_confidence(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
):
    """Test agent returns UNCERTAIN when confidence is low."""
    mock_llm_client.call_with_tools.return_value = {
        "role": "assistant",
        "content": "Uncertain due to ambiguous policy language",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "finish",
                    "arguments": json.dumps({
                        "status": "uncertain",
                        "rationale": "Policy language is ambiguous regarding PT requirements",
                        "confidence": 0.5,
                        "policy_section": "Section 2.3",
                        "policy_pages": [5],
                    }),
                },
            }
        ],
        "finish_reason": "tool_calls",
    }

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=5,
    )

    results = await controller.evaluate_case(
        case_bundle=sample_case,
        policy_document_id="pi-test-doc-123",
    )

    assert len(results) == 1
    assert results[0].status == DecisionStatus.UNCERTAIN
    assert results[0].confidence < 0.65
    assert results[0].reason_code == "agent_uncertain"


@pytest.mark.asyncio
async def test_react_loop_max_iterations(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
    sample_retrieval_result,
):
    """Test max iterations limit."""
    # LLM keeps calling tools but never finishes
    mock_llm_client.call_with_tools.return_value = {
        "role": "assistant",
        "content": "Still thinking...",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "pi_search",
                    "arguments": json.dumps({"query": "requirements"}),
                },
            }
        ],
        "finish_reason": "tool_calls",
    }

    mock_retrieval_service.retrieve.return_value = sample_retrieval_result

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=3,  # Low limit for testing
    )

    results = await controller.evaluate_case(
        case_bundle=sample_case,
        policy_document_id="pi-test-doc-123",
    )

    assert len(results) == 1
    assert results[0].status == DecisionStatus.UNCERTAIN
    assert "max iterations" in results[0].rationale.lower() or "max_iterations" in results[0].reason_code
    assert len(results[0].reasoning_trace) == 3  # Three iterations


@pytest.mark.asyncio
async def test_react_loop_llm_error(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
):
    """Test handling of LLM API errors."""
    from reasoning_service.services.llm_client import LLMClientError

    mock_llm_client.call_with_tools.side_effect = LLMClientError("API rate limit exceeded")

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=5,
    )

    results = await controller.evaluate_case(
        case_bundle=sample_case,
        policy_document_id="pi-test-doc-123",
    )

    assert len(results) == 1
    assert results[0].status == DecisionStatus.UNCERTAIN
    assert "LLM call failed" in results[0].rationale
    assert results[0].reason_code == "agent_error"


@pytest.mark.asyncio
async def test_react_loop_tool_execution_error(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
):
    """Test handling of tool execution errors."""
    # LLM calls a tool that fails
    mock_llm_client.call_with_tools.return_value = {
        "role": "assistant",
        "content": "Let me search",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "pi_search",
                    "arguments": json.dumps({"query": "requirements"}),
                },
            }
        ],
        "finish_reason": "tool_calls",
    }

    # Retrieval service raises an error
    mock_retrieval_service.retrieve.side_effect = Exception("Retrieval service unavailable")

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=5,
    )

    results = await controller.evaluate_case(
        case_bundle=sample_case,
        policy_document_id="pi-test-doc-123",
    )

    # Should handle gracefully and continue or return uncertain
    assert len(results) == 1
    # The error should be recorded in reasoning trace
    assert len(results[0].reasoning_trace) > 0


@pytest.mark.asyncio
async def test_reasoning_trace_format(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
    sample_retrieval_result,
):
    """Test reasoning trace format matches ReasoningStep schema."""
    mock_llm_client.call_with_tools.return_value = {
        "role": "assistant",
        "content": "Decision made",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "finish",
                    "arguments": json.dumps({
                        "status": "met",
                        "rationale": "Test rationale",
                        "confidence": 0.9,
                        "policy_section": "Section 2.3",
                        "policy_pages": [5],
                    }),
                },
            }
        ],
        "finish_reason": "tool_calls",
    }

    mock_retrieval_service.retrieve.return_value = sample_retrieval_result

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=5,
    )

    results = await controller.evaluate_case(
        case_bundle=sample_case,
        policy_document_id="pi-test-doc-123",
    )

    assert len(results) == 1
    trace = results[0].reasoning_trace

    # Verify trace format
    assert len(trace) > 0
    for step in trace:
        assert hasattr(step, "step")
        assert hasattr(step, "action")
        assert hasattr(step, "observation")
        assert isinstance(step.step, int)
        assert isinstance(step.action, str)
        assert isinstance(step.observation, str)
        assert step.step >= 1


@pytest.mark.asyncio
async def test_observation_truncation(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
    sample_retrieval_result,
):
    """Test that long observations are truncated."""
    # Create a very long tool result
    long_result = "x" * 1000
    mock_retrieval_service.retrieve.return_value = sample_retrieval_result

    # Mock tool executor to return long result
    with patch.object(ToolExecutor, "execute", new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = json.dumps({"success": True, "data": long_result})

        mock_llm_client.call_with_tools.side_effect = [
            {
                "role": "assistant",
                "content": "Searching",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "pi_search",
                            "arguments": json.dumps({"query": "test"}),
                        },
                    }
                ],
                "finish_reason": "tool_calls",
            },
            {
                "role": "assistant",
                "content": "Done",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": json.dumps({
                                "status": "met",
                                "rationale": "Test",
                                "confidence": 0.9,
                                "policy_section": "Section 2.3",
                                "policy_pages": [5],
                            }),
                        },
                    }
                ],
                "finish_reason": "tool_calls",
            },
        ]

        controller = ReActController(
            llm_client=mock_llm_client,
            retrieval_service=mock_retrieval_service,
            max_iterations=5,
        )

        results = await controller.evaluate_case(
            case_bundle=sample_case,
            policy_document_id="pi-test-doc-123",
        )

        # Check that observation is truncated
        assert len(results) == 1
        trace = results[0].reasoning_trace
        for step in trace:
            assert len(step.observation) <= 200  # Should be truncated


@pytest.mark.asyncio
async def test_identify_criteria(
    mock_llm_client,
    mock_retrieval_service,
):
    """Test criterion identification logic."""
    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
    )

    # Test with explicit criteria
    case1 = CaseBundle(
        case_id="test-1",
        policy_id="LCD-L34220",
        fields=[],
        metadata={"criteria": ["criterion-1", "criterion-2"]},
    )
    criteria = await controller._identify_criteria(case1)
    assert criteria == ["criterion-1", "criterion-2"]

    # Test with criterion_id fallback
    case2 = CaseBundle(
        case_id="test-2",
        policy_id="LCD-L34220",
        fields=[],
        metadata={"criterion_id": "single-criterion"},
    )
    criteria = await controller._identify_criteria(case2)
    assert criteria == ["single-criterion"]

    # Test with default fallback
    case3 = CaseBundle(
        case_id="test-3",
        policy_id="LCD-L34220",
        fields=[],
        metadata={},
    )
    criteria = await controller._identify_criteria(case3)
    assert criteria == ["LCD-L34220:default"]


@pytest.mark.asyncio
async def test_reasoning_trace_schema_validation(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
    sample_retrieval_result,
):
    """Test that reasoning trace matches ReasoningStep schema exactly."""
    from reasoning_service.models.schema import ReasoningStep
    from pydantic import ValidationError

    mock_llm_client.call_with_tools.return_value = {
        "role": "assistant",
        "content": "Decision made",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "finish",
                    "arguments": json.dumps({
                        "status": "met",
                        "rationale": "Test rationale",
                        "confidence": 0.9,
                        "policy_section": "Section 2.3",
                        "policy_pages": [5],
                    }),
                },
            }
        ],
        "finish_reason": "tool_calls",
    }

    mock_retrieval_service.retrieve.return_value = sample_retrieval_result

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=5,
    )

    results = await controller.evaluate_case(
        case_bundle=sample_case,
        policy_document_id="pi-test-doc-123",
    )

    assert len(results) == 1
    trace = results[0].reasoning_trace

    # Validate each step can be serialized/deserialized as ReasoningStep
    for step in trace:
        # Should be a ReasoningStep instance
        assert isinstance(step, ReasoningStep)
        
        # Validate required fields exist and have correct types
        assert isinstance(step.step, int)
        assert step.step >= 1
        assert isinstance(step.action, str)
        assert len(step.action) > 0
        assert isinstance(step.observation, str)
        
        # Test serialization to dict (as Pydantic model)
        step_dict = step.model_dump()
        assert "step" in step_dict
        assert "action" in step_dict
        assert "observation" in step_dict
        
        # Test deserialization from dict
        reconstructed = ReasoningStep(**step_dict)
        assert reconstructed.step == step.step
        assert reconstructed.action == step.action
        assert reconstructed.observation == step.observation
        
        # Test JSON serialization
        step_json = step.model_dump_json()
        assert isinstance(step_json, str)
        
        # Test JSON deserialization
        import json as json_lib
        step_from_json = ReasoningStep(**json_lib.loads(step_json))
        assert step_from_json.step == step.step


@pytest.mark.asyncio
async def test_reasoning_trace_action_values(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
    sample_retrieval_result,
):
    """Test that action values match expected tool names."""
    mock_llm_client.call_with_tools.side_effect = [
        {
            "role": "assistant",
            "content": "Searching",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "pi_search",
                        "arguments": json.dumps({"query": "test"}),
                    },
                }
            ],
            "finish_reason": "tool_calls",
        },
        {
            "role": "assistant",
            "content": "Getting facts",
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "facts_get",
                        "arguments": json.dumps({"field_name": "patient_age"}),
                    },
                }
            ],
            "finish_reason": "tool_calls",
        },
        {
            "role": "assistant",
            "content": "Finishing",
            "tool_calls": [
                {
                    "id": "call_3",
                    "type": "function",
                    "function": {
                        "name": "finish",
                        "arguments": json.dumps({
                            "status": "met",
                            "rationale": "Test",
                            "confidence": 0.9,
                            "policy_section": "Section 2.3",
                            "policy_pages": [5],
                        }),
                    },
                }
            ],
            "finish_reason": "tool_calls",
        },
    ]

    mock_retrieval_service.retrieve.return_value = sample_retrieval_result

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=5,
    )

    results = await controller.evaluate_case(
        case_bundle=sample_case,
        policy_document_id="pi-test-doc-123",
    )

    assert len(results) == 1
    trace = results[0].reasoning_trace

    # Verify action values match tool names
    expected_actions = ["pi_search", "facts_get", "finish"]
    actual_actions = [step.action for step in trace]
    
    assert len(actual_actions) == len(expected_actions)
    for i, expected_action in enumerate(expected_actions):
        assert actual_actions[i] == expected_action


@pytest.mark.asyncio
async def test_controller_retries_tool_after_timeout(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
):
    """Controller should retry once when a tool times out."""
    mock_llm_client.call_with_tools.side_effect = [
        {
            "role": "assistant",
            "content": "Searching PT requirements",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "pi_search",
                        "arguments": json.dumps({"query": "pt requirements"}),
                    },
                }
            ],
            "finish_reason": "tool_calls",
        },
        {
            "role": "assistant",
            "content": "Finishing",
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "finish",
                        "arguments": json.dumps({
                            "status": "met",
                            "rationale": "All requirements satisfied",
                            "confidence": 0.85,
                            "policy_section": "Section 2.3",
                            "policy_pages": [5],
                        }),
                    },
                }
            ],
            "finish_reason": "tool_calls",
        },
    ]

    attempt_counter = {"pi_search": 0}

    async def fake_execute(self, tool_name, arguments, timeout=None):
        if tool_name == "pi_search":
            attempt_counter["pi_search"] += 1
            if attempt_counter["pi_search"] == 1:
                raise ToolTimeoutError(tool_name, timeout or 0)
            return json.dumps({"success": True, "node_refs": []})
        if tool_name == "finish":
            return json.dumps({"success": True})
        return json.dumps({"success": True})

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=3,
    )
    controller.tool_retry_limit = 1

    with patch.object(ToolExecutor, "execute", new=fake_execute):
        results = await controller.evaluate_case(
            case_bundle=sample_case,
            policy_document_id="pi-test-doc-123",
        )

    assert attempt_counter["pi_search"] == 2
    assert results[0].status == DecisionStatus.MET


@pytest.mark.asyncio
async def test_controller_abstains_after_repeated_timeouts(
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
):
    """Controller should return UNCERTAIN when tool keeps timing out."""
    mock_llm_client.call_with_tools.return_value = {
        "role": "assistant",
        "content": "Searching",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "pi_search",
                    "arguments": json.dumps({"query": "pt requirements"}),
                },
            }
        ],
        "finish_reason": "tool_calls",
    }

    async def always_timeout(self, tool_name, arguments, timeout=None):
        raise ToolTimeoutError(tool_name, timeout or 0)

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=3,
    )
    controller.tool_retry_limit = 1

    with patch.object(ToolExecutor, "execute", new=always_timeout):
        results = await controller.evaluate_case(
            case_bundle=sample_case,
            policy_document_id="pi-test-doc-123",
        )

    assert results[0].status == DecisionStatus.UNCERTAIN
    assert results[0].reason_code == "tool_timeout"


@patch("reasoning_service.services.react_controller.record_confidence_score")
@pytest.mark.asyncio
async def test_controller_logs_tool_sequence_and_confidence_metric(
    mock_conf_metric,
    mock_llm_client,
    mock_retrieval_service,
    sample_case,
):
    """Controller emits structured log with tool sequence and records gauge."""
    mock_llm_client.call_with_tools.side_effect = [
        {
            "role": "assistant",
            "content": "Searching PT requirements",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "pi_search",
                        "arguments": json.dumps({"query": "pt requirements"}),
                    },
                }
            ],
            "finish_reason": "tool_calls",
        },
        {
            "role": "assistant",
            "content": "Finishing",
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "finish",
                        "arguments": json.dumps({
                            "status": "met",
                            "rationale": "All requirements satisfied",
                            "confidence": 0.9,
                            "policy_section": "Section 2.3",
                            "policy_pages": [5],
                        }),
                    },
                }
            ],
            "finish_reason": "tool_calls",
        },
    ]

    async def fake_execute(self, tool_name, arguments, timeout=None):
        if tool_name == "pi_search":
            return json.dumps({"success": True, "node_refs": []})
        if tool_name == "finish":
            return json.dumps({"success": True})
        return json.dumps({"success": True})

    controller = ReActController(
        llm_client=mock_llm_client,
        retrieval_service=mock_retrieval_service,
        max_iterations=3,
    )
    controller.logger = MagicMock()

    with patch.object(ToolExecutor, "execute", new=fake_execute):
        await controller.evaluate_case(
            case_bundle=sample_case,
            policy_document_id="pi-test-doc-123",
        )

    controller.logger.info.assert_called()
    _, kwargs = controller.logger.info.call_args
    assert "tool_sequence" in kwargs["extra"]
    assert kwargs["extra"]["tool_sequence"][0]["action"] == "pi_search"
    mock_conf_metric.assert_called_with(0.9)
