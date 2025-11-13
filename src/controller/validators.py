"""
Policy-specific validators for Lumbar MRI prior authorization criteria.

This module provides structured validation logic for the LCD-L34220 policy,
replacing naive keyword matching with proper business rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


# Approved ICD-10-CM codes for Lumbar MRI (from LCD-L34220 policy)
APPROVED_ICD10_CODES = {
    "M48.06",  # Spinal stenosis, lumbar region
    "M48.07",  # Spinal stenosis, lumbosacral region
    "M51.16",  # Intervertebral disc disorders with radiculopathy, lumbar
    "M51.36",  # Other intervertebral disc degeneration, lumbar
    "M51.37",  # Other intervertebral disc degeneration, lumbosacral
    "M54.5",  # Low back pain
    "M99.99",  # Other biomechanical lesions (placeholder for testing)
}

# Red flag conditions that bypass conservative treatment requirement
RED_FLAG_CONDITIONS = {
    "progressive neurological deficit",
    "cauda equina syndrome",
    "suspected tumor",
    "suspected infection",
    "suspected fracture",
    "bowel or bladder dysfunction",
}


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    confidence: float
    reason: str
    supporting_facts: List[Dict[str, Any]]


@dataclass
class CriterionValidation:
    """Complete validation result for a criterion."""

    criterion_id: str
    status: str  # "ready" | "not_ready" | "uncertain"
    validations: Dict[str, ValidationResult]
    overall_confidence: float
    rationale: str
    reason_code: Optional[str] = None


class LumbarMRIValidator:
    """Validator for Lumbar MRI prior authorization criteria."""

    def __init__(
        self,
        min_age: int = 18,
        min_treatment_weeks: int = 6,
        min_confidence_threshold: float = 0.75,
    ):
        self.min_age = min_age
        self.min_treatment_weeks = min_treatment_weeks
        self.min_confidence_threshold = min_confidence_threshold

    def validate_criterion(
        self, criterion_id: str, case_facts: List[Dict[str, Any]]
    ) -> CriterionValidation:
        """
        Validate all requirements for a specific criterion.

        Args:
            criterion_id: The criterion being evaluated
            case_facts: List of extracted facts from case documents

        Returns:
            CriterionValidation with detailed validation results
        """
        validations: Dict[str, ValidationResult] = {}

        # Extract facts by field
        facts_by_field = self._group_facts_by_field(case_facts)

        # Validate age requirement
        age_validation = self._validate_age(facts_by_field.get("age", []))
        validations["age"] = age_validation

        # Validate diagnosis requirement
        diagnosis_validation = self._validate_diagnosis(
            facts_by_field.get("primary_diagnosis", [])
            + facts_by_field.get("secondary_diagnosis", [])
        )
        validations["diagnosis"] = diagnosis_validation

        # Check for red flags
        red_flag_validation = self._validate_red_flags(facts_by_field)
        validations["red_flags"] = red_flag_validation

        # Validate treatment requirement (can be bypassed by red flags)
        treatment_validation = self._validate_treatment_duration(
            facts_by_field.get("conservative_treatment_weeks", []),
            bypass=red_flag_validation.is_valid,
        )
        validations["treatment"] = treatment_validation

        # Determine overall status
        return self._compute_overall_status(criterion_id, validations)

    def _group_facts_by_field(self, facts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group facts by field name."""
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for fact in facts:
            field = fact.get("field")
            if field:
                grouped.setdefault(field, []).append(fact)
        return grouped

    def _validate_age(self, age_facts: List[Dict[str, Any]]) -> ValidationResult:
        """Validate patient age >= minimum requirement."""
        if not age_facts:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                reason="Age information missing",
                supporting_facts=[],
            )

        # Take the fact with highest confidence
        age_fact = max(age_facts, key=lambda f: f.get("confidence", 0.0))
        age_value = age_fact.get("value")
        confidence = age_fact.get("confidence", 0.0)

        if confidence < self.min_confidence_threshold:
            return ValidationResult(
                is_valid=False,
                confidence=confidence,
                reason=f"Age documentation has low confidence ({confidence:.2f})",
                supporting_facts=[age_fact],
            )

        if not isinstance(age_value, (int, float)):
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                reason=f"Age value is not numeric: {age_value}",
                supporting_facts=[age_fact],
            )

        if age_value >= self.min_age:
            return ValidationResult(
                is_valid=True,
                confidence=confidence,
                reason=f"Patient age {age_value} meets minimum requirement of {self.min_age}",
                supporting_facts=[age_fact],
            )
        else:
            return ValidationResult(
                is_valid=False,
                confidence=confidence,
                reason=f"Patient age {age_value} is below minimum of {self.min_age}",
                supporting_facts=[age_fact],
            )

    def _validate_diagnosis(self, diagnosis_facts: List[Dict[str, Any]]) -> ValidationResult:
        """Validate diagnosis code is in approved list."""
        if not diagnosis_facts:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                reason="Diagnosis code missing",
                supporting_facts=[],
            )

        # Check all diagnosis codes
        approved_diagnoses = []
        unapproved_diagnoses = []

        for fact in diagnosis_facts:
            code = str(fact.get("value", "")).strip()
            confidence = fact.get("confidence", 0.0)

            if confidence < self.min_confidence_threshold:
                return ValidationResult(
                    is_valid=False,
                    confidence=confidence,
                    reason=f"Diagnosis code {code} has low confidence ({confidence:.2f})",
                    supporting_facts=[fact],
                )

            if code in APPROVED_ICD10_CODES:
                approved_diagnoses.append((code, fact))
            else:
                unapproved_diagnoses.append((code, fact))

        if approved_diagnoses:
            best_diagnosis = max(approved_diagnoses, key=lambda x: x[1].get("confidence", 0.0))
            code, fact = best_diagnosis
            return ValidationResult(
                is_valid=True,
                confidence=fact.get("confidence", 0.0),
                reason=f"Diagnosis {code} is in approved ICD-10-CM list",
                supporting_facts=[fact],
            )
        elif unapproved_diagnoses:
            code, fact = unapproved_diagnoses[0]
            return ValidationResult(
                is_valid=False,
                confidence=fact.get("confidence", 0.0),
                reason=f"Diagnosis {code} is not in approved ICD-10-CM list for lumbar MRI",
                supporting_facts=[fact],
            )
        else:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                reason="No valid diagnosis codes found",
                supporting_facts=diagnosis_facts,
            )

    def _validate_red_flags(
        self, facts_by_field: Dict[str, List[Dict[str, Any]]]
    ) -> ValidationResult:
        """Check for red flag conditions that bypass treatment requirements."""
        red_flag_present = facts_by_field.get("red_flag_present", [])
        red_flag_confirmed = facts_by_field.get("red_flag_confirmed", [])
        red_flag_type = facts_by_field.get("red_flag_type", [])

        # Check if red flags are explicitly confirmed
        if red_flag_confirmed:
            fact = red_flag_confirmed[0]
            if (
                fact.get("value") is True
                and fact.get("confidence", 0.0) >= self.min_confidence_threshold
            ):
                # Get the type of red flag
                if red_flag_type:
                    flag_type = str(red_flag_type[0].get("value", "")).lower()
                    if any(known_flag in flag_type for known_flag in RED_FLAG_CONDITIONS):
                        return ValidationResult(
                            is_valid=True,
                            confidence=fact.get("confidence", 0.0),
                            reason=f"Red flag present: {flag_type}",
                            supporting_facts=[fact] + red_flag_type,
                        )

        # Check if red flags are present but not confirmed (conflicting info)
        if red_flag_present:
            fact = red_flag_present[0]
            if (
                fact.get("value") is True
                and fact.get("confidence", 0.0) < self.min_confidence_threshold
            ):
                return ValidationResult(
                    is_valid=False,
                    confidence=fact.get("confidence", 0.0),
                    reason="Red flag reported but confidence too low",
                    supporting_facts=[fact],
                )

        # No red flags present
        return ValidationResult(
            is_valid=False,
            confidence=1.0,
            reason="No red flags present",
            supporting_facts=[],
        )

    def _validate_treatment_duration(
        self, treatment_facts: List[Dict[str, Any]], bypass: bool = False
    ) -> ValidationResult:
        """Validate conservative treatment duration meets minimum."""
        if bypass:
            return ValidationResult(
                is_valid=True,
                confidence=1.0,
                reason="Conservative treatment requirement bypassed due to red flags",
                supporting_facts=[],
            )

        if not treatment_facts:
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                reason="Conservative treatment duration not documented",
                supporting_facts=[],
            )

        # Take the fact with highest confidence
        treatment_fact = max(treatment_facts, key=lambda f: f.get("confidence", 0.0))
        weeks = treatment_fact.get("value")
        confidence = treatment_fact.get("confidence", 0.0)

        if confidence < self.min_confidence_threshold:
            return ValidationResult(
                is_valid=False,
                confidence=confidence,
                reason=f"Treatment duration has low confidence ({confidence:.2f})",
                supporting_facts=[treatment_fact],
            )

        if not isinstance(weeks, (int, float)):
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                reason=f"Treatment duration is not numeric: {weeks}",
                supporting_facts=[treatment_fact],
            )

        if weeks >= self.min_treatment_weeks:
            return ValidationResult(
                is_valid=True,
                confidence=confidence,
                reason=f"Conservative treatment {weeks} weeks meets minimum of {self.min_treatment_weeks}",
                supporting_facts=[treatment_fact],
            )
        else:
            return ValidationResult(
                is_valid=False,
                confidence=confidence,
                reason=f"Conservative treatment {weeks} weeks is below minimum of {self.min_treatment_weeks}",
                supporting_facts=[treatment_fact],
            )

    def _compute_overall_status(
        self, criterion_id: str, validations: Dict[str, ValidationResult]
    ) -> CriterionValidation:
        """Compute overall criterion status from individual validations."""
        # Check if any critical validation has low confidence
        critical_fields = ["age", "diagnosis", "treatment"]
        low_confidence_fields = []
        failed_fields = []

        for field in critical_fields:
            if field in validations:
                validation = validations[field]
                if validation.confidence < self.min_confidence_threshold:
                    low_confidence_fields.append(field)
                elif not validation.is_valid and field != "treatment":
                    # Treatment can be bypassed by red flags
                    failed_fields.append(field)

        # Treatment special case: check if bypassed by red flags
        if "treatment" in validations and not validations["treatment"].is_valid:
            # Check if red flags validation says it's bypassed
            if "red_flags" not in validations or not validations["red_flags"].is_valid:
                failed_fields.append("treatment")

        # Compute overall confidence (minimum of all critical validations)
        confidences = [v.confidence for k, v in validations.items() if k in critical_fields]
        overall_confidence = min(confidences) if confidences else 0.0

        # Determine status
        if low_confidence_fields:
            status = "uncertain"
            reason_code = "insufficient_documentation"
            rationale = (
                f"Unable to determine: {', '.join(low_confidence_fields)} have insufficient documentation. "
                f"Requires additional documentation or clarification."
            )
        elif failed_fields:
            status = "not_ready"
            reason_code = "criteria_not_met"
            failures = [validations[f].reason for f in failed_fields if f in validations]
            rationale = f"Policy requirements not met: {' '.join(failures)}"
        else:
            status = "ready"
            reason_code = None
            successes = [
                v.reason for k, v in validations.items() if v.is_valid and k in critical_fields
            ]
            rationale = f"Patient meets all criteria: {' '.join(successes)}"

        return CriterionValidation(
            criterion_id=criterion_id,
            status=status,
            validations=validations,
            overall_confidence=overall_confidence,
            rationale=rationale,
            reason_code=reason_code,
        )
