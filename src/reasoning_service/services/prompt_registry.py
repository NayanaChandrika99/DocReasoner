"""Prompt registry and comparison helpers."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PromptVersion:
    """Metadata for a stored prompt."""

    version_id: str
    prompt_text: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    author: str = "system"
    metadata: Dict[str, Any] = field(default_factory=dict)


class PromptRegistry:
    """Persist prompt versions to disk."""

    def __init__(self, path: Path | str = Path("data/prompt_registry.json")) -> None:
        self.path = Path(path)
        self._versions: List[PromptVersion] = []
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            payload = json.loads(self.path.read_text())
            self._versions = [
                PromptVersion(**item)
                for item in payload.get("versions", [])
            ]
        self._loaded = True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"versions": [asdict(v) for v in self._versions]}
        self.path.write_text(json.dumps(payload, indent=2))

    def add_version(
        self,
        prompt_text: str,
        author: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptVersion:
        """Add a new version and persist immediately."""
        self.load()
        version = PromptVersion(
            version_id=self._generate_version_id(),
            prompt_text=prompt_text,
            author=author,
            metadata=metadata or {},
        )
        self._versions.append(version)
        self.save()
        return version

    def latest(self) -> Optional[PromptVersion]:
        self.load()
        if not self._versions:
            return None
        return self._versions[-1]

    def list_versions(self, limit: int = 10) -> List[PromptVersion]:
        self.load()
        return self._versions[-limit:]

    def _generate_version_id(self) -> str:
        return f"prompt-{uuid.uuid4().hex[:8]}"


class PromptComparator:
    """Utility for comparing prompt versions using aggregate scores."""

    def compare(
        self,
        baseline_score: float,
        candidate_score: float,
        tolerance: float = 0.01,
    ) -> str:
        """Return textual verdict of the comparison."""
        delta = candidate_score - baseline_score
        if abs(delta) <= tolerance:
            return "no_change"
        return "improved" if delta > 0 else "regressed"
