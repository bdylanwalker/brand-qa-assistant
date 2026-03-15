"""Unit tests for the agent runner JSON parsing helpers."""

import pytest
from src.agent import runner as runner_module


def test_parse_json_valid():
    raw = '{"url": "https://x.com", "overall": "pass", "score": 90, "findings": [], "summary": "ok"}'
    result = runner_module._parse_json(raw, "https://x.com")
    assert result["overall"] == "pass"
    assert result["score"] == 90


def test_parse_json_embedded_in_prose():
    raw = 'Here is my analysis: {"url": "https://x.com", "overall": "warn", "score": 65, "findings": [], "summary": "issues found"} End of report.'
    result = runner_module._parse_json(raw, "https://x.com")
    assert result["score"] == 65


def test_parse_json_no_json_returns_error_dict():
    raw = "I could not complete the analysis."
    result = runner_module._parse_json(raw, "https://x.com")
    assert result["overall"] == "fail"
    assert result["score"] == 0
    assert "url" in result


def test_parse_json_invalid_json_returns_error_dict():
    raw = '{"url": "https://x.com", "overall": "pass", BROKEN}'
    result = runner_module._parse_json(raw, "https://x.com")
    assert result["overall"] == "fail"


def test_extract_text_from_message_with_text_block():
    class FakeTextValue:
        value = "Hello from agent"

    class FakeBlock:
        text = FakeTextValue()

    class FakeMessage:
        content = [FakeBlock()]

    text = runner_module._extract_text(FakeMessage())
    assert text == "Hello from agent"
