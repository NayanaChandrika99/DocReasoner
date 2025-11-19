"""Calibration service for conformal prediction.

Provides historical confidence score data for conformal prediction,
enabling uncertainty quantification with statistical guarantees.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import numpy as np

from reasoning_service.models.policy import ReasoningOutput

logger = logging.getLogger(__name__)


class CalibrationService:
    """Service for retrieving and processing historical calibration data."""

    def __init__(self, session_maker: async_sessionmaker):
        """Initialize calibration service.

        Args:
            session_maker: Async database session maker
        """
        self.session_maker = session_maker

    async def get_calibration_set(
        self,
        criterion_id: Optional[str] = None,
        policy_id: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, any]]:
        """Get historical calibration scores for conformal prediction.

        Args:
            criterion_id: Filter by specific criterion (None for all)
            policy_id: Filter by specific policy (None for all)
            limit: Maximum number of records to retrieve

        Returns:
            List of calibration records with confidence scores
        """
        async with self.session_maker() as session:
            stmt = select(ReasoningOutput).order_by(ReasoningOutput.created_at.desc())

            if criterion_id:
                stmt = stmt.where(ReasoningOutput.criterion_id == criterion_id)
            if policy_id:
                stmt = stmt.where(ReasoningOutput.policy_id == policy_id)

            stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            records = result.scalars().all()

            calibration_data = []
            for record in records:
                calibration_data.append({
                    "case_id": record.case_id,
                    "criterion_id": record.criterion_id,
                    "policy_id": record.policy_id,
                    "status": record.status,
                    "c_tree": record.c_tree,
                    "c_span": record.c_span,
                    "c_final": record.c_final,
                    "c_joint": record.c_joint,
                    "created_at": record.created_at,
                })

            logger.info(
                f"Retrieved {len(calibration_data)} calibration records "
                f"(criterion={criterion_id}, policy={policy_id})"
            )
            return calibration_data

    async def get_confidence_quantiles(
        self,
        criterion_id: Optional[str] = None,
        policy_id: Optional[str] = None,
        quantiles: List[float] = [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99],
    ) -> Dict[str, List[float]]:
        """Compute confidence quantiles for calibration.

        Args:
            criterion_id: Filter by criterion
            policy_id: Filter by policy
            quantiles: Quantile levels to compute

        Returns:
            Dict mapping confidence type to quantile values
        """
        calibration_data = await self.get_calibration_set(
            criterion_id=criterion_id,
            policy_id=policy_id,
        )

        if not calibration_data:
            logger.warning("No calibration data available")
            return {
                "c_tree": [0.0] * len(quantiles),
                "c_span": [0.0] * len(quantiles),
                "c_final": [0.0] * len(quantiles),
                "c_joint": [0.0] * len(quantiles),
            }

        # Extract confidence scores
        c_tree_scores = [d["c_tree"] for d in calibration_data]
        c_span_scores = [d["c_span"] for d in calibration_data]
        c_final_scores = [d["c_final"] for d in calibration_data]
        c_joint_scores = [d["c_joint"] for d in calibration_data]

        # Compute quantiles
        result = {
            "c_tree": np.quantile(c_tree_scores, quantiles).tolist(),
            "c_span": np.quantile(c_span_scores, quantiles).tolist(),
            "c_final": np.quantile(c_final_scores, quantiles).tolist(),
            "c_joint": np.quantile(c_joint_scores, quantiles).tolist(),
        }

        logger.info(f"Computed quantiles from {len(calibration_data)} samples")
        return result

    async def get_status_distribution(
        self,
        criterion_id: Optional[str] = None,
        policy_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Get distribution of decision statuses.

        Args:
            criterion_id: Filter by criterion
            policy_id: Filter by policy

        Returns:
            Dict mapping status to count
        """
        calibration_data = await self.get_calibration_set(
            criterion_id=criterion_id,
            policy_id=policy_id,
        )

        distribution = defaultdict(int)
        for record in calibration_data:
            distribution[record["status"]] += 1

        return dict(distribution)

    async def compute_conformal_threshold(
        self,
        alpha: float = 0.1,
        criterion_id: Optional[str] = None,
        policy_id: Optional[str] = None,
        confidence_type: str = "c_joint",
    ) -> float:
        """Compute conformal prediction threshold.

        Uses historical calibration data to compute a threshold such that
        at least (1-alpha) fraction of predictions exceed this threshold.

        Args:
            alpha: Significance level (e.g., 0.1 for 90% coverage)
            criterion_id: Filter by criterion
            policy_id: Filter by policy
            confidence_type: Which confidence score to use

        Returns:
            Threshold value for conformal prediction
        """
        calibration_data = await self.get_calibration_set(
            criterion_id=criterion_id,
            policy_id=policy_id,
        )

        if not calibration_data:
            logger.warning("No calibration data, returning default threshold")
            return 0.5

        scores = [d[confidence_type] for d in calibration_data]
        n = len(scores)

        # Conformal prediction: quantile at level ceil((n+1)(1-alpha))/n
        # This ensures valid coverage even for finite samples
        k = int(np.ceil((n + 1) * (1 - alpha)))
        threshold = np.quantile(scores, k / n)

        logger.info(
            f"Computed conformal threshold {threshold:.4f} "
            f"for alpha={alpha} from {n} samples"
        )
        return float(threshold)

    async def get_calibration_curve(
        self,
        criterion_id: Optional[str] = None,
        policy_id: Optional[str] = None,
        bins: int = 10,
        confidence_type: str = "c_joint",
    ) -> Tuple[List[float], List[float]]:
        """Compute reliability (calibration) curve.

        Args:
            criterion_id: Filter by criterion
            policy_id: Filter by policy
            bins: Number of bins for grouping
            confidence_type: Which confidence score to use

        Returns:
            Tuple of (bin_centers, accuracies)
        """
        calibration_data = await self.get_calibration_set(
            criterion_id=criterion_id,
            policy_id=policy_id,
        )

        if not calibration_data:
            return [], []

        # Extract confidence scores and convert status to binary
        confidences = []
        correct = []

        for record in calibration_data:
            confidences.append(record[confidence_type])
            # Assume "ready" is correct decision for simplicity
            # In practice, you'd need ground truth labels
            correct.append(1.0 if record["status"] == "ready" else 0.0)

        confidences = np.array(confidences)
        correct = np.array(correct)

        # Bin by confidence
        bin_edges = np.linspace(0, 1, bins + 1)
        bin_centers = []
        bin_accuracies = []

        for i in range(bins):
            mask = (confidences >= bin_edges[i]) & (confidences < bin_edges[i + 1])
            if mask.sum() > 0:
                bin_centers.append((bin_edges[i] + bin_edges[i + 1]) / 2)
                bin_accuracies.append(correct[mask].mean())

        logger.info(f"Computed calibration curve with {bins} bins")
        return bin_centers, bin_accuracies

    async def get_statistics_summary(
        self,
        criterion_id: Optional[str] = None,
        policy_id: Optional[str] = None,
    ) -> Dict[str, any]:
        """Get comprehensive statistics summary.

        Args:
            criterion_id: Filter by criterion
            policy_id: Filter by policy

        Returns:
            Dict with various statistics
        """
        calibration_data = await self.get_calibration_set(
            criterion_id=criterion_id,
            policy_id=policy_id,
        )

        if not calibration_data:
            return {
                "total_samples": 0,
                "status_distribution": {},
                "confidence_stats": {},
            }

        # Status distribution
        status_dist = await self.get_status_distribution(
            criterion_id=criterion_id,
            policy_id=policy_id,
        )

        # Confidence statistics
        c_joint_scores = [d["c_joint"] for d in calibration_data]
        confidence_stats = {
            "mean": float(np.mean(c_joint_scores)),
            "median": float(np.median(c_joint_scores)),
            "std": float(np.std(c_joint_scores)),
            "min": float(np.min(c_joint_scores)),
            "max": float(np.max(c_joint_scores)),
        }

        summary = {
            "total_samples": len(calibration_data),
            "status_distribution": status_dist,
            "confidence_stats": confidence_stats,
            "criterion_id": criterion_id,
            "policy_id": policy_id,
        }

        return summary
