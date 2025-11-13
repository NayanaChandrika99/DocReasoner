#!/usr/bin/env python3
"""
Interactive demo of the policy-specific validators.
Shows how the LumbarMRIValidator evaluates different scenarios.
"""

import sys

sys.path.insert(0, "src")

from controller.validators import LumbarMRIValidator

# Initialize validator
validator = LumbarMRIValidator()

print("=" * 80)
print("🏥 LUMBAR MRI PRIOR AUTHORIZATION VALIDATOR DEMO")
print("=" * 80)

# Scenario 1: Perfect case
print("\n📋 SCENARIO 1: All Criteria Met")
print("-" * 80)
facts_pass = [
    {"field": "age", "value": 45, "confidence": 1.0},
    {"field": "primary_diagnosis", "value": "M54.5", "confidence": 0.95},
    {"field": "conservative_treatment_weeks", "value": 8, "confidence": 0.90},
]
result = validator.validate_criterion("lumbar-mri-pt", facts_pass)
print(f"Status: {result.status.upper()}")
print(f"Confidence: {result.overall_confidence:.2%}")
print(f"Rationale: {result.rationale}")

# Scenario 2: Age too young
print("\n\n📋 SCENARIO 2: Patient Under 18")
print("-" * 80)
facts_age_fail = [
    {"field": "age", "value": 16, "confidence": 1.0},
    {"field": "primary_diagnosis", "value": "M54.5", "confidence": 0.95},
    {"field": "conservative_treatment_weeks", "value": 8, "confidence": 0.90},
]
result = validator.validate_criterion("lumbar-mri-pt", facts_age_fail)
print(f"Status: {result.status.upper()}")
print(f"Confidence: {result.overall_confidence:.2%}")
print(f"Rationale: {result.rationale}")
print("\nValidation Breakdown:")
for key, val in result.validations.items():
    icon = "✓" if val.is_valid else "✗"
    print(f"  {icon} {key}: {val.reason}")

# Scenario 3: Red flags present
print("\n\n📋 SCENARIO 3: Red Flags Exception (bypasses treatment)")
print("-" * 80)
facts_red_flag = [
    {"field": "age", "value": 35, "confidence": 1.0},
    {"field": "primary_diagnosis", "value": "M51.36", "confidence": 0.95},
    {"field": "conservative_treatment_weeks", "value": 0, "confidence": 1.0},
    {"field": "red_flag_confirmed", "value": True, "confidence": 0.95},
    {"field": "red_flag_type", "value": "progressive neurological deficit", "confidence": 0.95},
]
result = validator.validate_criterion("lumbar-mri-pt", facts_red_flag)
print(f"Status: {result.status.upper()}")
print(f"Confidence: {result.overall_confidence:.2%}")
print(f"Rationale: {result.rationale}")
print("\nValidation Breakdown:")
for key, val in result.validations.items():
    icon = "✓" if val.is_valid else "✗"
    print(f"  {icon} {key}: {val.reason}")

# Scenario 4: Non-approved diagnosis
print("\n\n📋 SCENARIO 4: Non-Approved Diagnosis Code")
print("-" * 80)
facts_bad_diagnosis = [
    {"field": "age", "value": 50, "confidence": 1.0},
    {"field": "primary_diagnosis", "value": "M79.3", "confidence": 0.95},
    {"field": "conservative_treatment_weeks", "value": 10, "confidence": 0.90},
]
result = validator.validate_criterion("lumbar-mri-pt", facts_bad_diagnosis)
print(f"Status: {result.status.upper()}")
print(f"Confidence: {result.overall_confidence:.2%}")
print(f"Rationale: {result.rationale}")

# Show approved codes
print("\n\n📋 APPROVED ICD-10-CM CODES:")
print("-" * 80)
from controller.validators import APPROVED_ICD10_CODES

for code in sorted(APPROVED_ICD10_CODES):
    print(f"  • {code}")

print("\n" + "=" * 80)
print("Demo complete! ✓")
print("=" * 80)
