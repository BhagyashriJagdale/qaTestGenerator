"""Unit tests for _parse_json_safe in core/llm_client.py."""

import pytest
from core.llm_client import _parse_json_safe


def test_valid_json():
    assert _parse_json_safe('{"key": "value"}') == {"key": "value"}


def test_strips_markdown_json_fence():
    raw = '```json\n{"key": "value"}\n```'
    assert _parse_json_safe(raw) == {"key": "value"}


def test_strips_bare_fence():
    raw = '```\n{"key": "value"}\n```'
    assert _parse_json_safe(raw) == {"key": "value"}


def test_whitespace_around_json():
    assert _parse_json_safe('  \n{"a": 1}\n  ') == {"a": 1}


def test_nested_json():
    raw = '{"outer": {"inner": [1, 2, 3]}}'
    assert _parse_json_safe(raw) == {"outer": {"inner": [1, 2, 3]}}


def test_truncated_json_with_recoverable_object():
    # Truncated after a complete inner object — the inner } can anchor recovery
    truncated = '{"a": 1, "b": {"c": 2}} trailing garbage'
    result = _parse_json_safe(truncated)
    assert result["a"] == 1


def test_truncated_unrecoverable_raises():
    # No closing } anywhere — nothing to anchor on
    truncated = '{"manual_test_cases": [{"title": "Login'
    with pytest.raises(ValueError):
        _parse_json_safe(truncated)


def test_no_json_raises():
    with pytest.raises(ValueError, match="No JSON object found"):
        _parse_json_safe("this has no json at all")


def test_empty_string_raises():
    with pytest.raises(ValueError):
        _parse_json_safe("")


def test_json_array_is_parsed():
    # _parse_json_safe returns whatever json.loads returns — arrays are valid JSON
    result = _parse_json_safe("[1, 2, 3]")
    assert result == [1, 2, 3]
