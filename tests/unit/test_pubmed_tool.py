# ABOUTME: Tests for the gated PubMed tool behavior.
# ABOUTME: Validates config gating, caching, and summaries.
"""Tests for PubMed-backed tool behavior."""

import json
from unittest.mock import AsyncMock

import pytest

from reasoning_service.config import settings
from reasoning_service.models.schema import CaseBundle
from reasoning_service.services.pubmed import PubMedCache, PubMedStudy
from reasoning_service.services.tool_handlers import ToolExecutor


def _case_bundle(**overrides):
    payload = {
        "case_id": "case-pubmed-001",
        "policy_id": "LCD-L34220",
        "fields": [],
        "metadata": {
            "criterion_id": "lumbar-mri-pt",
        },
    }
    payload.update(overrides)
    return CaseBundle(**payload)


class DummyPubMedClient:
    def __init__(self):
        self.calls = 0

    def search(self, condition: str, treatment: str, max_results: int = 3):
        self.calls += 1
        return [
            PubMedStudy(
                pmid="12345",
                title="Randomized trial of physical therapy",
                abstract="A randomized controlled trial showing benefit.",
                publication_date="2024-01-15",
                url="https://pubmed.ncbi.nlm.nih.gov/12345/",
                journal="Spine Journal",
                authors=["Smith J"],
                quality_tag="high",
            ),
            PubMedStudy(
                pmid="67890",
                title="Observational study of lumbar MRI",
                abstract="Retrospective cohort study.",
                publication_date="2023-05-20",
                url="https://pubmed.ncbi.nlm.nih.gov/67890/",
                journal="Radiology",
                authors=["Lee A"],
                quality_tag="medium",
            ),
        ]


@pytest.mark.asyncio
async def test_pubmed_disabled_returns_offline_summary(monkeypatch):
    monkeypatch.setattr(settings, "pubmed_enabled", False, raising=False)
    retrieval_service = AsyncMock()
    executor = ToolExecutor(
        retrieval_service=retrieval_service,
        case_bundle=_case_bundle(),
    )

    payload = await executor.execute(
        "pubmed_search", {"condition": "low back pain", "treatment": "lumbar MRI"}
    )
    data = json.loads(payload)
    assert data["success"] is True
    assert "disabled" in data["summary"].lower()
    assert data["studies"] == []


@pytest.mark.asyncio
async def test_pubmed_enabled_uses_cache_and_summaries(monkeypatch):
    monkeypatch.setattr(settings, "pubmed_enabled", True, raising=False)
    retrieval_service = AsyncMock()
    client = DummyPubMedClient()
    cache = PubMedCache(ttl_seconds=60)
    executor = ToolExecutor(
        retrieval_service=retrieval_service,
        case_bundle=_case_bundle(),
        pubmed_client=client,
        pubmed_cache=cache,
    )

    args = {"condition": "low back pain", "treatment": "lumbar MRI"}
    payload1 = await executor.execute("pubmed_search", args)
    payload2 = await executor.execute("pubmed_search", args)
    assert client.calls == 1  # cached second call

    data = json.loads(payload1)
    assert data["success"] is True
    assert len(data["studies"]) == 2
    assert "randomized" in data["summary"].lower()
    assert any(study["quality_tag"] == "high" for study in data["studies"])
