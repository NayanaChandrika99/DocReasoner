# ABOUTME: Defines canonical reason codes for controller/tool errors.
# ABOUTME: Keeps error taxonomy consistent across services.
"""Centralized reason codes used across the reasoning service."""


class ReasonCode:
    """String constants describing known error/fallback situations."""

    RATE_LIMITED = "rate_limited"
    MISSING_POLICY_DOCUMENT = "missing_policy_document_id"
    TOOL_TIMEOUT = "tool_timeout"
    TREESTORE_NO_TEXT = "treestore_missing_text"
    TREESTORE_NO_NODES = "treestore_no_nodes"
    PUBMED_DISABLED = "pubmed_disabled"
    PUBMED_CLIENT_MISSING = "pubmed_client_missing"
    PUBMED_ERROR = "pubmed_error"
*** End Patch
