# Test Cases - Lumbar MRI Prior Authorization Policy

**Policy:** LCD - Lumbar MRI (L34220) & doc_id `pi-cmhppdets02r308pjqnaukvnt`
**Effective Date:** Refer to policy document

## Test Case 1: Straightforward - All Criteria Met ✅

**Case ID:** `TC-001-STRAIGHTFORWARD`

**Question:** Is this referral ready to file for prior authorization?

**Case Bundle:**
```json
{
  "case_id": "TC-001",
  "patient_key": "pt-001",
  "facts": [
    {
      "field": "age",
      "value": 45,
      "confidence": 1.0,
      "doc_id": "visit-note-001",
      "page": 1,
      "bbox": [100, 200, 300, 220],
      "class": "age_field"
    },
    {
      "field": "primary_diagnosis",
      "value": "M54.5",
      "confidence": 0.95,
      "doc_id": "visit-note-001",
      "page": 1,
      "bbox": [100, 250, 300, 270],
      "class": "icd10_code"
    },
    {
      "field": "conservative_treatment_weeks",
      "value": 8,
      "confidence": 0.90,
      "doc_id": "pt-record-001",
      "page": 3,
      "bbox": [100, 300, 400, 320],
      "class": "treatment_duration"
    },
    {
      "field": "physical_therapy_sessions",
      "value": 12,
      "confidence": 0.90,
      "doc_id": "pt-record-001",
      "page": 4,
      "bbox": [100, 350, 450, 370],
      "class": "pt_sessions"
    },
    {
      "field": "prior_authorization_required",
      "value": true,
      "confidence": 1.0,
      "doc_id": "policy-001",
      "page": 1,
      "bbox": [100, 100, 500, 120],
      "class": "policy_requirement"
    }
  ]
}
```

**Expected Output:**
```json
{
  "status": "ready",
  "confidence": {
    "c_tree": 0.90,
    "c_span": 0.88,
    "c_final": 0.89,
    "c_joint": 0.88
  },
  "citation": {
    "section_path": "1.0 Prior Authorization Policy",
    "pages": [1]
  },
  "rationale": "Patient meets all criteria: age 45 (>18), diagnosis M54.5 (low back pain) is in approved list, completed 8 weeks conservative treatment including 12 PT sessions (exceeds 6-week minimum)."
}
```

---

## Test Case 2: Age Boundary - Exactly 18 Years ✅

**Case ID:** `TC-002-AGE-BOUNDARY`

**Question:** Is this referral ready to file for prior authorization?

**Case Bundle:**
```json
{
  "case_id": "TC-002",
  "patient_key": "pt-002",
  "facts": [
    {
      "field": "age",
      "value": 18,
      "confidence": 1.0,
      "doc_id": "visit-note-002",
      "page": 1,
      "bbox": [100, 200, 300, 220],
      "class": "age_field"
    },
    {
      "field": "primary_diagnosis",
      "value": "M48.06",
      "confidence": 0.95,
      "doc_id": "visit-note-002",
      "page": 1,
      "bbox": [100, 250, 300, 270],
      "class": "icd10_code"
    },
    {
      "field": "conservative_treatment_weeks",
      "value": 6,
      "confidence": 0.90,
      "doc_id": "pt-record-002",
      "page": 2,
      "bbox": [100, 300, 400, 320],
      "class": "treatment_duration"
    }
  ]
}
```

**Expected Output:**
```json
{
  "status": "ready",
  "confidence": {
    "c_tree": 0.88,
    "c_span": 0.85,
    "c_final": 0.86,
    "c_joint": 0.85
  },
  "citation": {
    "section_path": "1.0 Prior Authorization Policy",
    "pages": [1]
  },
  "rationale": "Patient meets criteria: age 18 meets minimum requirement, diagnosis M48.06 (spinal stenosis) is approved, completed exactly 6 weeks conservative treatment (meets minimum threshold)."
}
```

---

## Test Case 3: Failed - Age Under 18 ❌

**Case ID:** `TC-003-AGE-FAIL`

**Question:** Is this referral ready to file for prior authorization?

**Case Bundle:**
```json
{
  "case_id": "TC-003",
  "patient_key": "pt-003",
  "facts": [
    {
      "field": "age",
      "value": 16,
      "confidence": 1.0,
      "doc_id": "visit-note-003",
      "page": 1,
      "bbox": [100, 200, 300, 220],
      "class": "age_field"
    },
    {
      "field": "primary_diagnosis",
      "value": "M54.5",
      "confidence": 0.95,
      "doc_id": "visit-note-003",
      "page": 1,
      "bbox": [100, 250, 300, 270],
      "class": "icd10_code"
    },
    {
      "field": "conservative_treatment_weeks",
      "value": 8,
      "confidence": 0.90,
      "doc_id": "pt-record-003",
      "page": 3,
      "bbox": [100, 300, 400, 320],
      "class": "treatment_duration"
    }
  ]
}
```

**Expected Output:**
```json
{
  "status": "not_ready",
  "confidence": {
    "c_tree": 0.95,
    "c_span": 0.92,
    "c_final": 0.93,
    "c_joint": 0.92
  },
  "citation": {
    "section_path": "1.0 Prior Authorization Policy",
    "pages": [1]
  },
  "rationale": "Patient does not meet age requirement: age 16 is below minimum of 18 years. Despite meeting diagnosis and conservative treatment criteria, policy requires patients to be 18 or older."
}
```

---

## Test Case 4: Red Flags Exception - Bypass Conservative Treatment ✅

**Case ID:** `TC-004-RED-FLAGS`

**Question:** Is this referral ready to file for prior authorization?

**Case Bundle:**
```json
{
  "case_id": "TC-004",
  "patient_key": "pt-004",
  "facts": [
    {
      "field": "age",
      "value": 35,
      "confidence": 1.0,
      "doc_id": "visit-note-004",
      "page": 1,
      "bbox": [100, 200, 300, 220],
      "class": "age_field"
    },
    {
      "field": "primary_diagnosis",
      "value": "M51.36",
      "confidence": 0.95,
      "doc_id": "visit-note-004",
      "page": 1,
      "bbox": [100, 250, 300, 270],
      "class": "icd10_code"
    },
    {
      "field": "conservative_treatment_weeks",
      "value": 0,
      "confidence": 1.0,
      "doc_id": "visit-note-004",
      "page": 2,
      "bbox": [100, 300, 400, 320],
      "class": "treatment_duration"
    },
    {
      "field": "red_flag_present",
      "value": true,
      "confidence": 0.95,
      "doc_id": "visit-note-004",
      "page": 2,
      "bbox": [100, 350, 400, 370],
      "class": "red_flag"
    },
    {
      "field": "red_flag_type",
      "value": "progressive neurological deficit",
      "confidence": 0.95,
      "doc_id": "visit-note-004",
      "page": 2,
      "bbox": [100, 400, 450, 420],
      "class": "red_flag_type"
    }
  ]
}
```

**Expected Output:**
```json
{
  "status": "ready",
  "confidence": {
    "c_tree": 0.87,
    "c_span": 0.84,
    "c_final": 0.85,
    "c_joint": 0.84
  },
  "citation": {
    "section_path": "1.0 Prior Authorization Policy",
    "pages": [1]
  },
  "rationale": "Red flags exception applies: patient has progressive neurological deficit (a documented red flag). Conservative treatment requirement is bypassed per policy when red flags are present. Patient meets age (35>18) and has approved diagnosis M51.36."
}
```

---

## Test Case 5: Failed - Insufficient Conservative Treatment ❌

**Case ID:** `TC-005-INSUFFICIENT-TREATMENT`

**Question:** Is this referral ready to file for prior authorization?

**Case Bundle:**
```json
{
  "case_id": "TC-005",
  "patient_key": "pt-005",
  "facts": [
    {
      "field": "age",
      "value": 42,
      "confidence": 1.0,
      "doc_id": "visit-note-005",
      "page": 1,
      "bbox": [100, 200, 300, 220],
      "class": "age_field"
    },
    {
      "field": "primary_diagnosis",
      "value": "M54.5",
      "confidence": 0.95,
      "doc_id": "visit-note-005",
      "page": 1,
      "bbox": [100, 250, 300, 270],
      "class": "icd10_code"
    },
    {
      "field": "conservative_treatment_weeks",
      "value": 4,
      "confidence": 0.90,
      "doc_id": "pt-record-005",
      "page": 2,
      "bbox": [100, 300, 400, 320],
      "class": "treatment_duration"
    }
  ]
}
```

**Expected Output:**
```json
{
  "status": "not_ready",
  "confidence": {
    "c_tree": 0.92,
    "c_span": 0.90,
    "c_final": 0.91,
    "c_joint": 0.90
  },
  "citation": {
    "section_path": "1.0 Prior Authorization Policy",
    "pages": [1]
  },
  "rationale": "Conservative treatment requirement not met: patient completed only 4 weeks of conservative treatment, but policy requires minimum 6 weeks. No red flags documented. Cannot proceed without meeting treatment threshold."
}
```

---

## Test Case 6: Uncertain - Missing Diagnosis Code ⚠️

**Case ID:** `TC-006-MISSING-DIAGNOSIS`

**Question:** Is this referral ready to file for prior authorization?

**Case Bundle:**
```json
{
  "case_id": "TC-006",
  "patient_key": "pt-006",
  "facts": [
    {
      "field": "age",
      "value": 55,
      "confidence": 1.0,
      "doc_id": "visit-note-006",
      "page": 1,
      "bbox": [100, 200, 300, 220],
      "class": "age_field"
    },
    {
      "field": "conservative_treatment_weeks",
      "value": 8,
      "confidence": 0.90,
      "doc_id": "pt-record-006",
      "page": 3,
      "bbox": [100, 300, 400, 320],
      "class": "treatment_duration"
    },
    {
      "field": "primary_diagnosis",
      "value": "M99.99",
      "confidence": 0.50,
      "doc_id": "visit-note-006",
      "page": 1,
      "bbox": [100, 250, 300, 270],
      "class": "icd10_code"
    }
  ]
}
```

**Expected Output:**
```json
{
  "status": "uncertain",
  "confidence": {
    "c_tree": 0.58,
    "c_span": 0.55,
    "c_final": 0.56,
    "c_joint": 0.55
  },
  "citation": {
    "section_path": "1.0 Prior Authorization Policy",
    "pages": [1]
  },
  "rationale": "Unable to determine: diagnosis code M99.99 has low confidence (0.50) and may not be in approved list. Patient meets age (55>18) and treatment (8 weeks), but diagnosis verification is incomplete. Requires additional documentation or clarification before proceeding."
}
```

---

## Test Case 7: Failed - Non-Approved Diagnosis ❌

**Case ID:** `TC-007-NON-APPROVED-DIAGNOSIS`

**Question:** Is this referral ready to file for prior authorization?

**Case Bundle:**
```json
{
  "case_id": "TC-007",
  "patient_key": "pt-007",
  "facts": [
    {
      "field": "age",
      "value": 50,
      "confidence": 1.0,
      "doc_id": "visit-note-007",
      "page": 1,
      "bbox": [100, 200, 300, 220],
      "class": "age_field"
    },
    {
      "field": "primary_diagnosis",
      "value": "M79.3",
      "confidence": 0.95,
      "doc_id": "visit-note-007",
      "page": 1,
      "bbox": [100, 250, 300, 270],
      "class": "icd10_code"
    },
    {
      "field": "conservative_treatment_weeks",
      "value": 10,
      "confidence": 0.90,
      "doc_id": "pt-record-007",
      "page": 3,
      "bbox": [100, 300, 400, 320],
      "class": "treatment_duration"
    }
  ]
}
```

**Expected Output:**
```json
{
  "status": "not_ready",
  "confidence": {
    "c_tree": 0.94,
    "c_span": 0.91,
    "c_final": 0.92,
    "c_joint": 0.91
  },
  "citation": {
    "section_path": "1.0 Prior Authorization Policy",
    "pages": [1]
  },
  "rationale": "Primary diagnosis M79.3 (panniculitis) is not in the list of approved ICD-10-CM codes for lumbar MRI. Patient meets age (50>18) and conservative treatment (10 weeks), but non-approved diagnosis prevents prior authorization approval."
}
```

---

## Test Case 8: Uncertain - Conflicting Information ⚠️

**Case ID:** `TC-008-CONFLICTING`

**Question:** Is this referral ready to file for prior authorization?

**Case Bundle:**
```json
{
  "case_id": "TC-008",
  "patient_key": "pt-008",
  "facts": [
    {
      "field": "age",
      "value": 29,
      "confidence": 1.0,
      "doc_id": "visit-note-008",
      "page": 1,
      "bbox": [100, 200, 300, 220],
      "class": "age_field"
    },
    {
      "field": "primary_diagnosis",
      "value": "M51.16",
      "confidence": 0.90,
      "doc_id": "visit-note-008",
      "page": 1,
      "bbox": [100, 250, 300, 270],
      "class": "icd10_code"
    },
    {
      "field": "conservative_treatment_weeks",
      "value": 6,
      "confidence": 0.90,
      "doc_id": "pt-record-008",
      "page": 2,
      "bbox": [100, 300, 400, 320],
      "class": "treatment_duration"
    },
    {
      "field": "red_flag_reported",
      "value": true,
      "confidence": 0.60,
      "doc_id": "patient-statement",
      "page": 1,
      "bbox": [100, 400, 400, 420],
      "class": "patient_report"
    },
    {
      "field": "red_flag_confirmed",
      "value": false,
      "confidence": 0.90,
      "doc_id": "physician-note",
      "page": 2,
      "bbox": [100, 450, 450, 470],
      "class": "physician_assessment"
    }
  ]
}
```

**Expected Output:**
```json
{
  "status": "uncertain",
  "confidence": {
    "c_tree": 0.62,
    "c_span": 0.58,
    "c_final": 0.60,
    "c_joint": 0.58
  },
  "citation": {
    "section_path": "1.0 Prior Authorization Policy",
    "pages": [1]
  },
  "rationale": "Conflicting information detected: patient reports red flag symptoms, but physician assessment indicates no red flags present. Patient meets basic criteria (age 29>18, M51.16 approved diagnosis, 6 weeks treatment), but red flag discrepancy requires clarification before proceeding. Confidence too low to proceed without resolution."
}
```

---

## Test Case 9: Uncertain - Multiple Missing Criteria ⚠️

**Case ID:** `TC-009-MULTIPLE-MISSING`

**Question:** Is this referral ready to file for prior authorization?

**Case Bundle:**
```json
{
  "case_id": "TC-009",
  "patient_key": "pt-009",
  "facts": [
    {
      "field": "age",
      "value": 38,
      "confidence": 0.70,
      "doc_id": "patient-intake",
      "page": 1,
      "bbox": [100, 200, 300, 220],
      "class": "age_field"
    },
    {
      "field": "conservative_treatment_weeks",
      "value": 3,
      "confidence": 0.60,
      "doc_id": "partial-record",
      "page": 1,
      "bbox": [100, 300, 400, 320],
      "class": "treatment_duration"
    }
  ]
}
```

**Expected Output:**
```json
{
  "status": "uncertain",
  "confidence": {
    "c_tree": 0.35,
    "c_span": 0.30,
    "c_final": 0.32,
    "c_joint": 0.30
  },
  "citation": {
    "section_path": "1.0 Prior Authorization Policy",
    "pages": [1]
  },
  "rationale": "Multiple critical gaps in documentation: primary diagnosis missing, conservative treatment duration uncertain (3 weeks with low confidence), and age documentation insufficient. Cannot verify any major policy criteria. Complete clinical documentation required before assessment possible."
}
```

---

## Test Case 10: Edge Case - Multiple Approved Diagnoses ✅

**Case ID:** `TC-010-MULTIPLE-DIAGNOSES`

**Question:** Is this referral ready to file for prior authorization?

**Case Bundle:**
```json
{
  "case_id": "TC-010",
  "patient_key": "pt-010",
  "facts": [
    {
      "field": "age",
      "value": 63,
      "confidence": 1.0,
      "doc_id": "visit-note-010",
      "page": 1,
      "bbox": [100, 200, 300, 220],
      "class": "age_field"
    },
    {
      "field": "primary_diagnosis",
      "value": "M48.07",
      "confidence": 0.95,
      "doc_id": "visit-note-010",
      "page": 1,
      "bbox": [100, 250, 350, 270],
      "class": "icd10_code"
    },
    {
      "field": "secondary_diagnosis",
      "value": "M51.37",
      "confidence": 0.90,
      "doc_id": "visit-note-010",
      "page": 1,
      "bbox": [100, 280, 350, 300],
      "class": "icd10_code"
    },
    {
      "field": "conservative_treatment_weeks",
      "value": 12,
      "confidence": 0.90,
      "doc_id": "pt-record-010",
      "page": 5,
      "bbox": [100, 300, 400, 320],
      "class": "treatment_duration"
    },
    {
      "field": "physical_therapy_sessions",
      "value": 16,
      "confidence": 0.90,
      "doc_id": "pt-record-010",
      "page": 6,
      "bbox": [100, 350, 450, 370],
      "class": "pt_sessions"
    },
    {
      "field": "medication_trials",
      "value": ["NSAIDs", "muscle relaxants", "neuropathic agents"],
      "confidence": 0.90,
      "doc_id": "medication-log",
      "page": 2,
      "bbox": [100, 400, 500, 420],
      "class": "medication_history"
    }
  ]
}
```

**Expected Output:**
```json
{
  "status": "ready",
  "confidence": {
    "c_tree": 0.93,
    "c_span": 0.90,
    "c_final": 0.91,
    "c_joint": 0.90
  },
  "citation": {
    "section_path": "1.0 Prior Authorization Policy",
    "pages": [1]
  },
  "rationale": "Patient exceeds all requirements: age 63 (>18), multiple approved diagnoses (M48.07 spinal stenosis, M51.37 disc displacement), completed 12 weeks conservative treatment including 16 PT sessions and 3 medication classes (exceeds 6-week minimum). Strong documentation supports approval."
}
```

---

## Test Case Summary

| ID | Scenario | Status | Key Test |
|----|----------|--------|----------|
| TC-001 | Straightforward | ready | All criteria clearly met |
| TC-002 | Age boundary | ready | Exactly 18 years old |
| TC-003 | Failed age | not_ready | Under 18 years |
| TC-004 | Red flags | ready | Bypasses conservative treatment |
| TC-005 | Insufficient treatment | not_ready | Only 4 weeks (< 6 required) |
| TC-006 | Missing diagnosis | uncertain | Low confidence diagnosis |
| TC-007 | Non-approved diagnosis | not_ready | M79.3 not in approved list |
| TC-008 | Conflicting info | uncertain | Patient vs physician disagreement |
| TC-009 | Multiple missing | uncertain | Critical gaps in documentation |
| TC-010 | Multiple diagnoses | ready | Complex case with strong documentation |

## Test Execution Notes

1. **Validation Focus:** Each test case should validate specific policy criteria
2. **Edge Cases:** Boundary conditions (age=18, treatment=6 weeks)
3. **Error Handling:** Missing/conflicting/ambiguous information
4. **Confidence Scoring:** Test abstention threshold (0.65)
5. **Citation Quality:** Ensure returned citations point to correct policy sections
