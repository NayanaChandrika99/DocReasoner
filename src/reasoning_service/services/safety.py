"""Safety layer with calibration, self-consistency, and conformal prediction."""

from typing import Any, Optional
import numpy as np
from scipy.special import softmax

from reasoning_service.config import settings
from reasoning_service.models.schema import CriterionResult, DecisionStatus


class SafetyService:
    """Service for safety mechanisms: calibration, self-consistency, conformal."""
    
    def __init__(self):
        """Initialize safety service."""
        self.temperature_tree = 1.0  # Will be learned during calibration
        self.temperature_final = 1.0  # Will be learned during calibration
        self.calibrated = False
    
    def calibrate(
        self,
        validation_logits: list[np.ndarray],
        validation_labels: list[int]
    ) -> None:
        """Calibrate temperature scaling on validation set.
        
        Args:
            validation_logits: List of logit arrays from validation set
            validation_labels: True labels for validation set
        """
        # TODO: Implement temperature scaling calibration
        # Use scipy.optimize to find optimal temperatures
        # See: https://arxiv.org/abs/1706.04599
        
        if not settings.temperature_scaling_enabled:
            return
        
        # Placeholder - should use optimization to find T
        self.temperature_tree = 1.5
        self.temperature_final = 1.2
        self.calibrated = True
    
    def apply_temperature_scaling(
        self,
        logits: np.ndarray,
        temperature: float
    ) -> np.ndarray:
        """Apply temperature scaling to logits.
        
        Args:
            logits: Raw logits from model
            temperature: Temperature parameter
            
        Returns:
            Calibrated probabilities
        """
        scaled_logits = logits / temperature
        return softmax(scaled_logits)
    
    async def apply_self_consistency(
        self,
        criterion_result: CriterionResult,
        evaluate_fn: Any,
        k: Optional[int] = None
    ) -> CriterionResult:
        """Apply self-consistency by sampling multiple reasoning paths.
        
        Args:
            criterion_result: Initial criterion result
            evaluate_fn: Function to re-evaluate criterion
            k: Number of samples (defaults to settings)
            
        Returns:
            Criterion result with aggregated decision
        """
        if not settings.self_consistency_enabled:
            return criterion_result
        
        # Only apply for low-confidence, high-impact cases
        if criterion_result.confidence >= settings.self_consistency_threshold:
            return criterion_result
        
        k = k or settings.self_consistency_k
        
        # Generate k-1 additional samples (we already have 1)
        samples = [criterion_result]
        
        for _ in range(k - 1):
            # TODO: Re-run evaluation with different random seed
            # sample = await evaluate_fn()
            # samples.append(sample)
            pass
        
        # Aggregate via majority vote
        aggregated = self._aggregate_samples(samples)
        return aggregated
    
    def _aggregate_samples(
        self,
        samples: list[CriterionResult]
    ) -> CriterionResult:
        """Aggregate multiple samples via majority voting.
        
        Args:
            samples: List of criterion results from different samples
            
        Returns:
            Aggregated criterion result
        """
        # Count votes for each status
        status_votes: dict[DecisionStatus, int] = {}
        for sample in samples:
            status_votes[sample.status] = status_votes.get(sample.status, 0) + 1
        
        # Majority vote
        majority_status = max(status_votes.items(), key=lambda x: x[1])[0]
        
        # Average confidence among samples with majority status
        matching_confidences = [
            s.confidence for s in samples if s.status == majority_status
        ]
        avg_confidence = np.mean(matching_confidences) if matching_confidences else 0.0
        
        # Return sample with majority status and updated confidence
        result = samples[0]
        result.status = majority_status
        result.confidence = float(avg_confidence)
        
        return result
    
    def apply_conformal_prediction(
        self,
        criterion_result: CriterionResult,
        calibration_scores: list[float]
    ) -> CriterionResult:
        """Apply conformal prediction for uncertainty quantification.
        
        Args:
            criterion_result: Criterion result to check
            calibration_scores: Non-conformity scores from calibration set
            
        Returns:
            Criterion result, potentially marked as UNCERTAIN
        """
        # TODO: Implement full conformal prediction
        # See: https://arxiv.org/abs/2107.07511
        
        # Simplified implementation: check if prediction set is ambiguous
        alpha = settings.conformal_alpha
        
        # Calculate quantile from calibration scores
        if not calibration_scores:
            return criterion_result
        
        quantile = np.quantile(calibration_scores, 1 - alpha)
        
        # If current score exceeds quantile, prediction set is large (uncertain)
        # TODO: Implement proper non-conformity score calculation
        current_score = 1 - criterion_result.confidence
        
        if current_score > quantile:
            criterion_result.status = DecisionStatus.UNCERTAIN
            criterion_result.reason_code = "conformal_ambiguity"
        
        return criterion_result
    
    def calculate_joint_confidence(
        self,
        c_tree: float,
        c_span: float,
        c_final: float
    ) -> float:
        """Calculate joint confidence across retrieval and decision stages.
        
        Args:
            c_tree: Confidence from tree search
            c_span: Confidence from span selection
            c_final: Confidence from final decision
            
        Returns:
            Joint confidence score
        """
        return c_tree * c_span * c_final
    
    def should_route_to_human(self, criterion_result: CriterionResult) -> bool:
        """Determine if result should be routed to human review.
        
        Args:
            criterion_result: Criterion result to check
            
        Returns:
            True if should route to human
        """
        # Route uncertain cases
        if criterion_result.status == DecisionStatus.UNCERTAIN:
            return True
        
        # Route low-confidence high-impact cases
        if criterion_result.confidence < settings.high_impact_confidence_threshold:
            # TODO: Check if criterion is high-impact
            return True
        
        return False
