"""Utilities for converting demo case JSON into CaseBundle models."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from reasoning_service.models.schema import CaseBundle, VLMField


def case_dict_to_case_bundle(case_data: Dict[str, Any]) -> Tuple[CaseBundle, str]:
    """
    Convert the CLI-style case JSON into a CaseBundle and policy_document_id.

    The CLI fixtures store facts under case_bundle.facts; this helper translates each fact into
    a VLMField and infers the policy document identifier from case_data["policy"]["doc_id"].
    """
    policy = case_data.get("policy", {})
    policy_doc_id = policy.get("doc_id")
    if not policy_doc_id:
        raise ValueError("Case is missing policy.doc_id, required for LLM controller evaluation.")

    facts = case_data.get("case_bundle", {}).get("facts", [])
    metadata = dict(case_data.get("case_bundle", {}).get("metadata", {}))

    criterion_id = case_data.get("criterion_id")
    if criterion_id:
        metadata.setdefault("criteria", [criterion_id])

    metadata["policy_document_id"] = policy_doc_id

    fields = []
    for fact in facts:
        bbox = fact.get("bbox") or [0, 0, 0, 0]
        if len(bbox) != 4:
            bbox = (bbox + [0, 0, 0, 0])[:4]
        page = fact.get("page") or 1
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1
        field_name = fact.get("field_name") or fact.get("field") or "unknown_field"
        fields.append(
            VLMField(
                field_name=field_name,
                value=fact.get("value"),
                confidence=float(fact.get("confidence", 0.9)),
                doc_id=fact.get("doc_id") or "case-note",
                page=max(1, page),
                bbox=list(bbox),
                field_class=fact.get("class"),
            )
        )

    case_bundle = CaseBundle(
        case_id=case_data.get("case_id", "unknown"),
        policy_id=policy.get("policy_id", "LCD-L34220"),
        fields=fields,
        metadata=metadata,
    )
    return case_bundle, policy_doc_id
