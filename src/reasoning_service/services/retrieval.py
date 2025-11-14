"""Async-friendly wrapper around the shared retrieval service."""

from __future__ import annotations

import asyncio
from typing import Optional

from policy_ingest.pageindex_client import PageIndexClient
from retrieval.service import RetrievalService as CoreRetrievalService
from retrieval.service import TreeStoreRetrievalService
from reasoning_service.config import settings
from reasoning_service.services.treestore_client import TreeStoreClient


class RetrievalService:
    """Expose the synchronous retrieval modules through an async interface."""

    def __init__(
        self,
        pageindex_client: Optional[PageIndexClient] = None,
        treestore_client: Optional[TreeStoreClient] = None,
        backend: Optional[str] = None,
    ) -> None:
        self.backend = (backend or settings.retrieval_backend).lower()
        if self.backend == "treestore":
            self._treestore_client = treestore_client or TreeStoreClient()
            self._core = TreeStoreRetrievalService(client=self._treestore_client)
        else:
            self._client = pageindex_client or PageIndexClient()
            self._core = CoreRetrievalService(client=self._client)
            self.backend = "pageindex"

    async def retrieve(
        self,
        document_id: str,
        query: str,
        top_k: int = 3,
        version_id: Optional[str] = None,
    ):
        loop = asyncio.get_running_loop()
        if self.backend == "treestore":
            return await loop.run_in_executor(
                None,
                self._core.search,
                query,
                document_id,
                version_id,
                top_k,
            )
        # Core service does not currently use top_k, but we keep the signature for compatibility.
        return await loop.run_in_executor(None, self._core.search, query, document_id)

    async def close(self) -> None:
        """Placeholder for interface compatibility."""
        return None
