"""Tests for the prompt registry."""

from pathlib import Path

from reasoning_service.services.prompt_registry import PromptRegistry


def test_prompt_registry_add_and_list(tmp_path: Path):
    registry_path = tmp_path / "registry.json"
    registry = PromptRegistry(path=registry_path)
    registry.add_version(prompt_text="prompt v1", author="tester", metadata={"score": 0.7})
    registry.add_version(prompt_text="prompt v2", author="tester", metadata={"score": 0.8})

    assert registry.latest().prompt_text == "prompt v2"
    versions = registry.list_versions()
    assert len(versions) == 2
    assert versions[0].prompt_text == "prompt v1"
    assert versions[1].metadata["score"] == 0.8
