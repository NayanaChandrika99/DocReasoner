"""Async-friendly wrapper around the shared retrieval service."""

from __future__ import annotations

import asyncio
from typing import Optional

from policy_ingest.pageindex_client import PageIndexClient
from retrieval.service import RetrievalService as CoreRetrievalService


class RetrievalService:
    """Expose the synchronous retrieval.service module through an async interface."""

    def __init__(self, pageindex_client: Optional[PageIndexClient] = None) -> None:
        self._client = pageindex_client or PageIndexClient()
        self._core = CoreRetrievalService(client=self._client)

    async def retrieve(self, document_id: str, query: str, top_k: int = 3):
        loop = asyncio.get_running_loop()
        # Core service does not currently use top_k, but we keep the signature for compatibility.
        return await loop.run_in_executor(None, self._core.search, query, document_id)

    async def close(self) -> None:
        """Placeholder for interface compatibility."""
        return None
