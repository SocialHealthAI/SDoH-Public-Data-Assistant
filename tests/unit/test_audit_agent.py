"""Unit tests for public-data audit formatting (no live LLM)."""
from types import SimpleNamespace

from audit_agent import format_tool_steps_for_audit


def test_format_tool_steps_for_audit_includes_tools_and_steps():
    action = SimpleNamespace(tool="search_sdoh_indicators", tool_input={"query": "diabetes"})
    steps = [(action, "found 3 candidates")]
    text = format_tool_steps_for_audit("Tool 1: search_sdoh_indicators", steps)

    assert "Tool 1: search_sdoh_indicators" in text
    assert "search_sdoh_indicators" in text
    assert "diabetes" in text
    assert "found 3 candidates" in text
    assert "INTERMEDIATE REASONING STEPS" in text
