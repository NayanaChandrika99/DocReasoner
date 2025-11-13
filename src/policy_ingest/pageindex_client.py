"""
Thin HTTP client for interacting with the hosted PageIndex API.

The client purposefully keeps behavior simple: it wraps upload, tree fetch,
retrieval submission, and retrieval polling with consistent headers and
timeouts. Higher-level modules should implement retries/circuit breakers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx


class PageIndexError(RuntimeError):
    """Raised when PageIndex responds with an unexpected payload or status."""


@dataclass
class PageIndexClient:
    """Small convenience wrapper around the PageIndex REST API."""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 30.0

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.getenv("PAGEINDEX_API_KEY")
        self.base_url = self.base_url or os.getenv("PAGEINDEX_BASE_URL", "https://api.pageindex.ai")
        if not self.base_url:
            raise PageIndexError("PAGEINDEX_BASE_URL is not configured")

    @property
    def available(self) -> bool:
        """Return True if the client has the credentials needed for live calls."""
        return bool(self.api_key)

    def upload_pdf(self, pdf_path: Path) -> str:
        """Upload a PDF and return the PageIndex document ID."""
        self._require_credentials()
        pdf_bytes = pdf_path.read_bytes()
        upload_url = f"{self.base_url.rstrip('/')}/doc/"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                upload_url,
                headers=self._headers(),
                files={"file": (pdf_path.name, pdf_bytes, "application/pdf")},
            )
            self._raise_for_status(response)
            payload = response.json()
            doc_id = payload.get("doc_id")
            if not doc_id:
                raise PageIndexError("upload response missing doc_id")
            return doc_id

    def get_tree(self, doc_id: str, include_summary: bool = True) -> Dict[str, Any]:
        """Fetch the processed tree for a given PageIndex document ID."""
        self._require_credentials()
        params = {"type": "tree", "format": "page"}
        if include_summary:
            params["summary"] = "true"
        tree_url = f"{self.base_url.rstrip('/')}/doc/{doc_id}/"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                tree_url,
                headers=self._headers(),
                params=params,
            )
            self._raise_for_status(response)
            return response.json()

    def submit_retrieval(self, doc_id: str, query: str, thinking: bool = True, strategy: Optional[str] = None) -> str:
        """Submit a retrieval request and return the retrieval_id."""
        self._require_credentials()
        payload = {"doc_id": doc_id, "query": query, "thinking": thinking}
        if strategy:
            payload["strategy"] = strategy
        retrieval_url = f"{self.base_url.rstrip('/')}/api/retrieval/"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                retrieval_url,
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
            )
            self._raise_for_status(response)
            retrieval_id = response.json().get("retrieval_id")
            if not retrieval_id:
                raise PageIndexError("retrieval submission missing retrieval_id")
            return retrieval_id

    def poll_retrieval(self, retrieval_id: str) -> Dict[str, Any]:
        """Fetch retrieval results."""
        self._require_credentials()
        poll_url = f"{self.base_url.rstrip('/')}/api/retrieval/{retrieval_id}/"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                poll_url,
                headers=self._headers(),
            )
            self._raise_for_status(response)
            return response.json()

    def llm_tree_search(self, doc_id: str, query: str, thinking: bool = True) -> Dict[str, Any]:
        """Run the default PageIndex LLM Tree Search and return the raw payload."""
        retrieval_id = self.submit_retrieval(doc_id=doc_id, query=query, thinking=thinking)
        return self.poll_retrieval(retrieval_id)

    def hybrid_tree_search(self, doc_id: str, query: str, top_k: int = 3) -> Dict[str, Any]:
        """Run the hybrid tree search mode (LLM + value function)."""
        retrieval_id = self.submit_retrieval(doc_id=doc_id, query=query, thinking=True, strategy="hybrid")
        return self.poll_retrieval(retrieval_id)

    def get_node_content(self, doc_id: str, node_id: str) -> Dict[str, Any]:
        """Fetch the full text for a specific node."""
        self._require_credentials()
        node_url = f"{self.base_url.rstrip('/')}/doc/{doc_id}/node/{node_id}/"
        params = {"format": "page"}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(node_url, headers=self._headers(), params=params)
            self._raise_for_status(response)
            return response.json()

    def _headers(self) -> Dict[str, str]:
        # Latest hosted docs expect `api_key` header rather than Bearer tokens.
        return {"api_key": self.api_key} if self.api_key else {}

    def _require_credentials(self) -> None:
        if not self.api_key:
            raise PageIndexError(
                "PAGEINDEX_API_KEY is not configured; set it in the environment before calling the API."
            )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PageIndexError(f"PageIndex API error: {exc}") from exc
