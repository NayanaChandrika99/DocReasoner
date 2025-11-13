"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient

from reasoning_service.api.app import create_app


@pytest.fixture
def app():
    """Create FastAPI app for testing."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_vlm_field():
    """Sample VLM field for testing."""
    return {
        "field_name": "physical_therapy_duration",
        "value": "6 weeks",
        "confidence": 0.95,
        "doc_id": "test-doc-123",
        "page": 2,
        "bbox": [100.0, 200.0, 300.0, 250.0],
        "field_class": "duration"
    }


@pytest.fixture
def sample_case_bundle(sample_vlm_field):
    """Sample case bundle for testing."""
    return {
        "case_id": "case-123",
        "fields": [sample_vlm_field],
        "policy_id": "LCD-33822",
        "metadata": {"submission_date": "2025-01-15"}
    }
