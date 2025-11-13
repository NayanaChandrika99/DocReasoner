"""Unit tests for safety service."""

import numpy as np
import pytest

from reasoning_service.services.safety import SafetyService
from reasoning_service.models.schema import CriterionResult, DecisionStatus, CitationInfo, RetrievalMethod


class TestSafetyService:
    """Tests for SafetyService."""
    
    def test_temperature_scaling(self):
        """Test temperature scaling application."""
        service = SafetyService()
        logits = np.array([2.0, 1.0, 0.5])
        
        probs = service.apply_temperature_scaling(logits, temperature=1.0)
        
        assert probs.shape == logits.shape
        assert np.isclose(probs.sum(), 1.0)
    
    def test_joint_confidence(self):
        """Test joint confidence calculation."""
        service = SafetyService()
        
        joint = service.calculate_joint_confidence(
            c_tree=0.9,
            c_span=0.95,
            c_final=0.85
        )
        
        expected = 0.9 * 0.95 * 0.85
        assert np.isclose(joint, expected)
    
    def test_should_route_uncertain(self):
        """Test routing of uncertain results."""
        service = SafetyService()
        
        result = CriterionResult(
            criterion_id="test-1",
            status=DecisionStatus.UNCERTAIN,
            citation=CitationInfo(doc="LCD-1", version="v1", section="1", pages=[1]),
            rationale="Uncertain",
            confidence=0.5,
            search_trajectory=[],
            retrieval_method=RetrievalMethod.PAGEINDEX_LLM
        )
        
        assert service.should_route_to_human(result) is True
