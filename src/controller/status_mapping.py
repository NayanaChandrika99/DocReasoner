"""Helpers for mapping CLI controller statuses onto API enums."""

from typing import Dict

from reasoning_service.models.schema import DecisionStatus

CLI_STATUS_TO_API: Dict[str, DecisionStatus] = {
    "ready": DecisionStatus.MET,
    "not_ready": DecisionStatus.MISSING,
    "not-ready": DecisionStatus.MISSING,
    "uncertain": DecisionStatus.UNCERTAIN,
}


def map_cli_status_to_api(status: str) -> DecisionStatus:
    """Map a CLI decision status string onto the API's DecisionStatus enum."""
    normalized = (status or "").lower()
    return CLI_STATUS_TO_API.get(normalized, DecisionStatus.UNCERTAIN)
