"""Tests for case_conversion utilities."""

import json
from pathlib import Path

from reasoning_service.utils.case_conversion import case_dict_to_case_bundle


def test_case_dict_to_case_bundle_converts_fixture():
    fixture = Path("tests/data/cases/case_straightforward.json")
    case_data = json.loads(fixture.read_text())

    case_bundle, policy_doc_id = case_dict_to_case_bundle(case_data)

    assert policy_doc_id == case_data["policy"]["doc_id"]
    assert len(case_bundle.fields) == len(case_data["case_bundle"]["facts"])
    assert case_bundle.metadata["policy_document_id"] == policy_doc_id
    assert case_bundle.metadata["criteria"][0] == case_data["criterion_id"]
