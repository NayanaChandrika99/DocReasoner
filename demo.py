#!/usr/bin/env python3
"""
Demo script showing the validator-based controller in action.
Bypasses retrieval to focus on the policy-specific validation logic.
"""

import sys
import json

sys.path.insert(0, "src")

from controller.validators import LumbarMRIValidator

print("=" * 80)
print("🏥 LUMBAR MRI PRIOR AUTHORIZATION - DEMO")
print("=" * 80)

validator = LumbarMRIValidator()

# Load all test cases
test_cases = [
    ("tests/data/cases/case_straightforward.json", "All criteria met"),
    ("tests/data/cases/tc_002_age_boundary.json", "Age boundary (exactly 18)"),
    ("tests/data/cases/tc_003_age_fail.json", "Age requirement failed"),
    ("tests/data/cases/tc_004_red_flags.json", "Red flags bypass treatment"),
    ("tests/data/cases/tc_005_insufficient_treatment.json", "Insufficient treatment"),
    ("tests/data/cases/tc_006_missing_diagnosis.json", "Low confidence diagnosis"),
    ("tests/data/cases/tc_007_non_approved_diagnosis.json", "Non-approved diagnosis"),
    ("tests/data/cases/tc_010_multiple_diagnoses.json", "Multiple diagnoses"),
]

for filepath, description in test_cases:
    print(f"\n{'─' * 80}")
    print(f"📋 {description}")
    print(f"   File: {filepath}")
    print(f"{'─' * 80}")

    with open(filepath) as f:
        test_case = json.load(f)

    facts = test_case["case_bundle"]["facts"]
    criterion_id = test_case["criterion_id"]
    result = validator.validate_criterion(criterion_id, facts)

    # Status emoji
    status_icon = {"ready": "✅ READY", "not_ready": "❌ NOT READY", "uncertain": "⚠️  UNCERTAIN"}[
        result.status
    ]

    print(f"\nStatus: {status_icon}")
    print(f"Confidence: {result.overall_confidence:.1%}")
    print(f"Rationale: {result.rationale[:120]}...")

    # Show key validations
    print(f"\nValidations:")
    for key in ["age", "diagnosis", "treatment"]:
        if key in result.validations:
            val = result.validations[key]
            icon = "✓" if val.is_valid else "✗"
            print(f"  {icon} {key}: {val.reason[:60]}...")

print(f"\n{'=' * 80}")
print("Demo complete!")
print(f"{'=' * 80}\n")
