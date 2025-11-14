# ABOUTME: Loads GEPA evaluation cases and manages controller executions.
# ABOUTME: Provides caching so prompt candidates reuse prior evaluations.
"""Dataset loader and evaluation runner for GEPA prompt optimization."""

from __future__ import annotations

import hashlib
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Protocol, Tuple

from reasoning_service.models.schema import CaseBundle, CriterionResult
from reasoning_service.services.react_controller import ReActController as LLMReActController
from reasoning_service.services.retrieval import RetrievalService as AsyncRetrievalService
from reasoning_service.utils.case_conversion import case_dict_to_case_bundle


@dataclass
class EvaluationCase:
    """Represents a single case for prompt evaluation."""

    case_bundle: CaseBundle
    policy_document_id: str
    source: str


class DatasetLoader(Protocol):
    """Protocol for loading evaluation cases."""

    def load(self) -> List[EvaluationCase]:
        ...


class FileSystemDatasetLoader:
    """Loads evaluation cases from JSON files or directories."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> List[EvaluationCase]:
        entries: List[EvaluationCase] = []
        path = self.path

        def _add_entry(data: Dict[str, Any], source: str) -> None:
            case_bundle, policy_doc_id = case_dict_to_case_bundle(data)
            entries.append(
                EvaluationCase(
                    case_bundle=case_bundle,
                    policy_document_id=policy_doc_id,
                    source=source,
                )
            )

        if path.is_dir():
            for file in sorted(path.glob("*.json")):
                _add_entry(json.loads(file.read_text()), str(file))
        elif path.is_file():
            payload = json.loads(path.read_text())
            if isinstance(payload, list):
                for idx, case in enumerate(payload):
                    _add_entry(case, f"{path}:{idx}")
            elif isinstance(payload, dict) and "cases" in payload:
                for idx, case in enumerate(payload["cases"]):
                    _add_entry(case, f"{path}:{idx}")
            else:
                _add_entry(payload, str(path))
        else:
            raise FileNotFoundError(f"Dataset not found at {path}")

        return entries


class EvaluationCache:
    """Caches evaluation results keyed by prompt text and case payload."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    def get(self, prompt_text: str, evaluation_case: EvaluationCase) -> Optional[List[Dict[str, Any]]]:
        key = self._key(prompt_text, evaluation_case)
        entry = self._store.get(key)
        if not entry:
            return None
        timestamp, payload = entry
        if time.time() - timestamp > self.ttl_seconds:
            self._store.pop(key, None)
            return None
        return payload

    def set(
        self,
        prompt_text: str,
        evaluation_case: EvaluationCase,
        serialized_results: List[Dict[str, Any]],
    ) -> None:
        key = self._key(prompt_text, evaluation_case)
        self._store[key] = (time.time(), serialized_results)

    def _key(self, prompt_text: str, evaluation_case: EvaluationCase) -> str:
        digest = hashlib.sha256()
        digest.update(prompt_text.encode("utf-8"))
        digest.update(evaluation_case.policy_document_id.encode("utf-8"))
        digest.update(evaluation_case.source.encode("utf-8"))
        serialized_bundle = json.dumps(
            evaluation_case.case_bundle.model_dump(mode="json"),
            sort_keys=True,
            default=str,
        )
        digest.update(serialized_bundle.encode("utf-8"))
        return digest.hexdigest()


class GEPAEvaluationRunner:
    """Executes the real controller across evaluation cases with caching."""

    def __init__(
        self,
        controller_provider: Optional[
            Callable[[str], AsyncIterator[LLMReActController]]
        ] = None,
        cache: Optional[EvaluationCache] = None,
    ) -> None:
        self.controller_provider = controller_provider or self._default_controller_provider
        self.cache = cache or EvaluationCache()

    async def evaluate_prompt(
        self,
        prompt_text: str,
        cases: List[EvaluationCase],
    ) -> List[CriterionResult]:
        """Evaluate the given prompt text across the provided cases."""
        results: List[CriterionResult] = []
        async with self.controller_provider(prompt_text) as controller:
            for item in cases:
                cached = self.cache.get(prompt_text, item)
                if cached:
                    results.extend(CriterionResult(**payload) for payload in cached)
                    continue

                evaluated = await controller.evaluate_case(
                    case_bundle=item.case_bundle,
                    policy_document_id=item.policy_document_id,
                )
                serialized = [res.model_dump() for res in evaluated]
                self.cache.set(prompt_text, item, serialized)
                results.extend(evaluated)
        return results

    @asynccontextmanager
    async def _default_controller_provider(
        self,
        prompt_text: str,
    ) -> AsyncIterator[LLMReActController]:
        retrieval_service = AsyncRetrievalService()
        controller = LLMReActController(
            retrieval_service=retrieval_service,
            system_prompt=prompt_text,
        )
        try:
            yield controller
        finally:
            await retrieval_service.close()
