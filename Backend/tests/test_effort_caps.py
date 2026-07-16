import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from providers.effort_caps import get_effort_caps, map_effort


def test_auto_always_first_and_empty_mapping():
    for p, m in [("subscription", "claude-opus-4-8"), ("openai", "gpt-5.5"),
                 ("nvidia", "z-ai/glm-5.2"), ("google", "gemini-3.5-flash"),
                 ("subscription", "cursor-composer")]:
        caps = get_effort_caps(p, m)
        assert caps["levels"][0] == "auto"
        assert map_effort(p, m, "auto") == {}


def test_claude_model_gating():
    assert "xhigh" in get_effort_caps("subscription", "claude-fable-5")["levels"]
    assert "xhigh" not in get_effort_caps("subscription", "claude-sonnet-4-6")["levels"]
    assert get_effort_caps("subscription", "claude-haiku-4-5")["levels"] == ["auto"]
    assert map_effort("subscription", "claude-opus-4-8", "max") == {"sdk_effort": "max"}
    # Desteklenmeyen seviye → sessizce auto (haiku'ya max istenirse hiçbir şey gitmez)
    assert map_effort("subscription", "claude-haiku-4-5", "max") == {}


def test_codex_max_only_on_56():
    assert "max" in get_effort_caps("subscription", "gpt-5.6-sol")["levels"]
    assert "max" not in get_effort_caps("subscription", "gpt-5.5")["levels"]
    assert map_effort("subscription", "gpt-5.6-terra", "xhigh") == {
        "cli_config": {"model_reasoning_effort": "xhigh"}}


def test_gemini_level_vs_budget_mutually_exclusive():
    r3 = map_effort("google", "gemini-3.5-flash", "high")
    assert r3 == {"gemini_thinking_level": "high"}
    r25 = map_effort("google", "gemini-2.5-flash", "high")
    assert r25 == {"gemini_thinking_budget": -1}
    assert "gemini_thinking_level" not in r25 and "gemini_thinking_budget" not in r3


def test_nvidia_glm_toggle_and_nemotron_low():
    assert map_effort("nvidia", "z-ai/glm-5.2", "off") == {
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    low = map_effort("nvidia", "nvidia/nemotron-3-super-120b-a12b", "low")
    assert low["extra_body"]["chat_template_kwargs"] == {"enable_thinking": True, "low_effort": True}


def test_anthropic_extra_body_and_copilot_flags():
    assert map_effort("anthropic", "claude-opus-4-8", "xhigh") == {
        "anthropic_extra_body": {"output_config": {"effort": "xhigh"}}}
    assert map_effort("subscription", "copilot-claude-sonnet-4.6", "max") == {
        "cli_flags": ["--effort", "max"]}
    # copilot gpt modelinde max listede yok → boş
    assert map_effort("subscription", "copilot-gpt-5.2", "max") == {}
