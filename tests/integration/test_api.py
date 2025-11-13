"""Integration tests for API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch

from reasoning_service.api.routes import reason
from reasoning_service.models.schema import (
    CaseBundle,
    CitationInfo,
    ConfidenceBreakdown,
    CriterionResult,
    DecisionStatus,
    EvidenceInfo,
    ReasoningStep,
    RetrievalMethod,
)


class _DummyController:
    """Fake controller for API integration testing."""

    async def evaluate_case(self, case_bundle: CaseBundle, policy_document_id: str):
        return [
            CriterionResult(
                criterion_id="lumbar-mri-pt",
                status=DecisionStatus.MET,
                evidence=EvidenceInfo(
                    doc_id="doc1", page=5, bbox=[0, 0, 100, 200], text_excerpt="6 weeks of PT"
                ),
                citation=CitationInfo(
                    doc=case_bundle.policy_id, version="v1", section="Section A", pages=[1]
                ),
                rationale="Evidence aligns with policy requirement.",
                confidence=0.77,
                confidence_breakdown=ConfidenceBreakdown(
                    c_tree=0.9, c_span=0.9, c_final=0.95, c_joint=0.77
                ),
                search_trajectory=["root", "1"],
                retrieval_method=RetrievalMethod.PAGEINDEX_LLM,
                reason_code=None,
                reasoning_trace=[
                    ReasoningStep(step=1, action="think", observation="plan retrieval")
                ],
            )
        ]


class _DummySafety:
    async def apply_self_consistency(self, criterion_result, evaluate_fn):
        return criterion_result

    def apply_conformal_prediction(self, criterion_result, calibration_scores):
        return criterion_result


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check(self, client):
        """Test basic health check."""
        response = client.get("/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_readiness_check(self, client):
        """Test readiness check."""
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    def test_liveness_check(self, client):
        """Test liveness check."""
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"


class TestReasoningEndpoints:
    """Tests for reasoning endpoints."""

    @patch("reasoning_service.api.routes.reason.load_calibration_scores", new_callable=AsyncMock)
    @patch("reasoning_service.api.routes.reason.get_policy_document_id", new_callable=AsyncMock)
    def test_auth_review(
        self, mock_get_policy, mock_load_calibration, app, client, sample_case_bundle
    ):
        """Test authorization review endpoint with mocked database functions."""

        # Mock the database functions that are called inside auth_review
        mock_get_policy.return_value = ("pi-test-doc-123", "2025-Q1")
        mock_load_calibration.return_value = []

        # Override controller and safety service dependencies
        app.dependency_overrides[reason.get_controller] = lambda: _DummyController()
        app.dependency_overrides[reason.get_safety_service] = lambda: _DummySafety()

        payload = {
            "case_bundle": sample_case_bundle,
            "self_consistency": False,
        }
        response = client.post(
            "/reason/auth-review",
            json=payload,
        )
        app.dependency_overrides.clear()

        # Debug: print error if not 200
        if response.status_code != 200:
            print(f"Error response: {response.json()}")

        assert response.status_code == 200
        data = response.json()
        assert data["case_id"] == sample_case_bundle["case_id"]
        assert (
            data["results"][0]["confidence_breakdown"]["c_joint"]
            == data["results"][0]["confidence"]
        )
        assert data["results"][0]["reasoning_trace"][0]["action"] == "think"
