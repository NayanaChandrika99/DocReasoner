"""Integration tests for the /reason/auth-review route using dependency overrides."""

from fastapi.testclient import TestClient
import pytest
from fastapi import HTTPException

from reasoning_service.api.app import create_app
from reasoning_service.api.routes import reason
from reasoning_service.models.schema import (
    CaseBundle,
    CitationInfo,
    ConfidenceBreakdown,
    CriterionResult,
    DecisionStatus,
    ReasoningStep,
    RetrievalMethod,
    VLMField,
)


class StubController:
    async def evaluate_case(self, case_bundle: CaseBundle, policy_document_id: str):
        result = CriterionResult(
            criterion_id="stub-criterion",
            status=DecisionStatus.MET,
            citation=CitationInfo(doc="doc-1", version="v1", section="Sec 1", pages=[1]),
            rationale="stub rationale",
            confidence=0.9,
            confidence_breakdown=ConfidenceBreakdown(c_tree=0.9, c_span=0.9, c_final=0.95, c_joint=0.77),
            search_trajectory=["root", "node-1"],
            retrieval_method=RetrievalMethod.PAGEINDEX_LLM,
            reasoning_trace=[ReasoningStep(step=1, action="think", observation="stub")],
        )
        return [result]


class StubSafety:
    async def apply_self_consistency(self, criterion_result, evaluate_fn=None):
        return criterion_result

    def apply_conformal_prediction(self, criterion_result, calibration_scores):
        return criterion_result


async def _override_controller():
    return StubController()


async def _override_db():
    yield None


async def _override_safety():
    return StubSafety()


def test_auth_review_route_returns_stubbed_result(monkeypatch):
    app = create_app()
    app.dependency_overrides[reason.get_controller] = _override_controller
    app.dependency_overrides[reason.get_db] = _override_db
    app.dependency_overrides[reason.get_safety_service] = _override_safety

    async def fake_get_policy_document_id(*_args, **_kwargs):
        return "doc-123", "v1"

    async def fake_load_calibration_scores(*_args, **_kwargs):
        return []

    monkeypatch.setattr(reason, "get_policy_document_id", fake_get_policy_document_id)
    monkeypatch.setattr(reason, "load_calibration_scores", fake_load_calibration_scores)

    client = TestClient(app)
    payload = {
        "case_bundle": {
            "case_id": "case-1",
            "policy_id": "LCD-L34220",
            "fields": [
                {
                    "field_name": "patient_age",
                    "value": "45",
                    "confidence": 0.9,
                    "doc_id": "doc-1",
                    "page": 1,
                    "bbox": [0, 0, 0, 0],
                }
            ],
            "metadata": {},
        }
    }

    response = client.post("/reason/auth-review", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["status"] == "met"
    assert data["results"][0]["rationale"] == "stub rationale"


def test_auth_review_returns_504_on_timeout(monkeypatch):
    class TimeoutController(StubController):
        async def evaluate_case(self, *args, **kwargs):
            raise TimeoutError("PageIndex timeout")

    app = create_app()
    app.dependency_overrides[reason.get_controller] = lambda: TimeoutController()
    app.dependency_overrides[reason.get_db] = _override_db
    app.dependency_overrides[reason.get_safety_service] = _override_safety

    async def fake_policy(*_args, **_kwargs):
        return "doc-123", "v1"

    monkeypatch.setattr(reason, "get_policy_document_id", fake_policy)

    client = TestClient(app)
    payload = {
        "case_bundle": {
            "case_id": "case-timeout",
            "policy_id": "LCD-L34220",
            "fields": [],
            "metadata": {},
        }
    }
    response = client.post("/reason/auth-review", json=payload)
    app.dependency_overrides.clear()
    assert response.status_code == 504


def test_auth_review_returns_404_when_policy_missing(monkeypatch):
    app = create_app()
    app.dependency_overrides[reason.get_controller] = lambda: _override_controller()
    app.dependency_overrides[reason.get_db] = _override_db
    app.dependency_overrides[reason.get_safety_service] = _override_safety

    async def missing_policy(*_args, **_kwargs):
        raise HTTPException(status_code=404, detail="Policy missing")

    monkeypatch.setattr(reason, "get_policy_document_id", missing_policy)

    client = TestClient(app)
    payload = {
        "case_bundle": {
            "case_id": "case-missing",
            "policy_id": "LCD-UNKNOWN",
            "fields": [],
            "metadata": {},
        }
    }
    response = client.post("/reason/auth-review", json=payload)
    app.dependency_overrides.clear()
    assert response.status_code == 404
