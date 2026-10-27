from __future__ import annotations
from pathlib import Path

import pytest

from persistent_memory import load_memory, update_convention, format_memory_for_prompt
from triage_workflow import create_triage_issue, IssueTriage


class FakeMessage:
    def __init__(self, content=None, tool_calls=None, parsed=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.parsed = parsed


class FakeResponse:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})()]


class FakeChatCompletions:
    def __init__(self, owner):
        self.owner = owner

    def create(self, **kwargs):
        self.owner.seen_messages = kwargs["messages"]
        return FakeResponse(FakeMessage(tool_calls=[]))

    def parse(self, **kwargs):
        self.owner.seen_messages = kwargs["messages"]
        result = IssueTriage(
            status="classified",
            severity="P2",
            component="payment",
            needs_urgent_response=False,
            reason="Fake result for local test.",
        )
        return FakeResponse(FakeMessage(parsed=result))


class FakeClient:
    def __init__(self):
        self.seen_messages = []
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeChatCompletions(self)
        self.beta = type("Beta", (), {})()
        self.beta.chat = type("BetaChat", (), {})()
        self.beta.chat.completions = self.chat.completions


def test_memory_persists_across_reload(tmp_path: Path):
    path = tmp_path / "memory.json"
    update_convention("severity_policy", "Use P1 for widespread payment outages.", path)
    reloaded = load_memory(path)
    assert reloaded["conventions"]["severity_policy"] == "Use P1 for widespread payment outages."


def test_update_replaces_old_value_and_tracks_change(tmp_path: Path):
    path = tmp_path / "memory.json"
    update_convention("severity_policy", "Old rule", path)
    update_convention("severity_policy", "New rule", path)
    memory = load_memory(path)
    assert memory["conventions"]["severity_policy"] == "New rule"
    assert memory["history"][-1]["old_value"] == "Old rule"
    assert memory["history"][-1]["new_value"] == "New rule"


def test_unchanged_value_does_not_add_duplicate_history(tmp_path: Path):
    path = tmp_path / "memory.json"
    update_convention("owner_policy", "Use component ownership map", path)
    before = len(load_memory(path)["history"])
    update_convention("owner_policy", "Use component ownership map", path)
    assert len(load_memory(path)["history"]) == before


def test_memory_is_injected_into_model_system_message(tmp_path: Path):
    path = tmp_path / "memory.json"
    update_convention("severity_policy", "NEW RULE: widespread payment outage is P1", path)
    context = format_memory_for_prompt(load_memory(path))
    client = FakeClient()
    result = create_triage_issue(client, "fake-model", "Payment fails for all users", memory_context=context)
    system_message = client.seen_messages[0]["content"]
    assert "NEW RULE: widespread payment outage is P1" in system_message
    assert "PERSISTENT PROJECT MEMORY" in system_message
    assert result.triage.severity == "P2"


def test_blank_convention_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        update_convention(" ", "value", tmp_path / "memory.json")
