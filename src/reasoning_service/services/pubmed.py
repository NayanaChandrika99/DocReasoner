# ABOUTME: Provides minimal PubMed client utilities for evidence tools.
# ABOUTME: Exposes caching helpers for the pubmed_search tool.
"""PubMed client and caching utilities."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx


class PubMedClientError(RuntimeError):
    """Raised when PubMed API interactions fail."""


@dataclass
class PubMedStudy:
    """Normalized PubMed study metadata."""

    pmid: str
    title: str
    abstract: Optional[str] = None
    publication_date: Optional[str] = None
    url: Optional[str] = None
    journal: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    quality_tag: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pmid": self.pmid,
            "title": self.title,
            "abstract": self.abstract,
            "publication_date": self.publication_date,
            "url": self.url,
            "journal": self.journal,
            "authors": self.authors,
            "quality_tag": self.quality_tag,
        }


class PubMedCache:
    """In-memory cache for PubMed responses."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}

    def get(self, condition: str, treatment: str) -> Optional[Dict[str, Any]]:
        key = (condition.lower(), treatment.lower())
        entry = self._store.get(key)
        if not entry:
            return None
        timestamp, value = entry
        if time.time() - timestamp > self.ttl_seconds:
            self._store.pop(key, None)
            return None
        return value

    def set(self, condition: str, treatment: str, value: Dict[str, Any]) -> None:
        key = (condition.lower(), treatment.lower())
        self._store[key] = (time.time(), value)


class PubMedClient:
    """Thin HTTP client for NCBI E-Utilities."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(self, condition: str, treatment: str, max_results: int = 3) -> List[PubMedStudy]:
        """Search PubMed and return normalized study metadata."""
        query = " ".join(part for part in [condition, treatment] if part).strip()
        if not query:
            return []

        ids = self._search_ids(query=query, max_results=max_results)
        if not ids:
            return []
        summaries = self._fetch_summaries(ids)
        return summaries

    def _search_ids(self, query: str, max_results: int) -> List[str]:
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
        }
        if self.api_key:
            params["api_key"] = self.api_key
        url = f"{self.base_url}/esearch.fcgi"
        try:
            response = httpx.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            return payload.get("esearchresult", {}).get("idlist", [])
        except Exception as exc:  # noqa: BLE001
            raise PubMedClientError(f"PubMed search failed: {exc}") from exc

    def _fetch_summaries(self, ids: List[str]) -> List[PubMedStudy]:
        params = {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "json",
        }
        if self.api_key:
            params["api_key"] = self.api_key
        url = f"{self.base_url}/esummary.fcgi"
        try:
            response = httpx.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json().get("result", {})
        except Exception as exc:  # noqa: BLE001
            raise PubMedClientError(f"PubMed summary fetch failed: {exc}") from exc

        studies: List[PubMedStudy] = []
        for pmid in ids:
            meta = payload.get(pmid)
            if not meta:
                continue
            title = meta.get("title") or "Untitled"
            study = PubMedStudy(
                pmid=pmid,
                title=title,
                abstract=meta.get("elocationid"),
                publication_date=meta.get("pubdate"),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                journal=(meta.get("fulljournalname") or meta.get("source")),
                authors=[auth.get("name") for auth in meta.get("authors", []) if auth.get("name")],
            )
            study.quality_tag = self._quality_from_text(study)
            studies.append(study)
        return studies

    @staticmethod
    def _quality_from_text(study: PubMedStudy) -> str:
        text = " ".join(filter(None, [study.title, study.abstract or ""])).lower()
        if any(keyword in text for keyword in ["randomized", "randomised", "prospective"]):
            return "high"
        if any(keyword in text for keyword in ["retrospective", "cohort"]):
            return "medium"
        return "low"
