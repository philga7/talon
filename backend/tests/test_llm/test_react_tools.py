"""Tests for ReAct-style plain-text tool parsing."""

from __future__ import annotations

from app.llm.react_tools import parse_plain_text_tool_calls, strip_tool_blocks


def test_parse_returns_none_for_empty_content() -> None:
    assert parse_plain_text_tool_calls("") is None
    assert parse_plain_text_tool_calls("   \n  ") is None


def test_parse_returns_none_when_no_tool_blocks() -> None:
    assert parse_plain_text_tool_calls("Just some text.") is None
    assert parse_plain_text_tool_calls("I might say <tool> but not valid") is None


def test_parse_single_tool_with_args() -> None:
    content = '<tool>{"name": "searxng_search__search", "args": {"query": "weather"}}</tool>'
    out = parse_plain_text_tool_calls(content)
    assert out is not None
    assert len(out) == 1
    assert out[0]["type"] == "function"
    assert out[0]["function"]["name"] == "searxng_search__search"
    assert out[0]["function"]["arguments"] == '{"query": "weather"}'
    assert out[0]["id"].startswith("react-")


def test_parse_single_tool_with_arguments_string() -> None:
    content = '<tool>{"name": "searxng_search", "arguments": "{\\"query\\": \\"test\\"}"}</tool>'
    out = parse_plain_text_tool_calls(content)
    assert out is not None
    assert len(out) == 1
    assert out[0]["function"]["name"] == "searxng_search"
    assert "query" in out[0]["function"]["arguments"]


def test_parse_multiple_tool_blocks() -> None:
    content = (
        'Before. <tool>{"name": "a", "args": {}}</tool> '
        'Middle. <tool>{"name": "b", "args": {"x": 1}}</tool> After.'
    )
    out = parse_plain_text_tool_calls(content)
    assert out is not None
    assert len(out) == 2
    assert out[0]["function"]["name"] == "a"
    assert out[0]["function"]["arguments"] == "{}"
    assert out[1]["function"]["name"] == "b"
    assert out[1]["function"]["arguments"] == '{"x": 1}'


def test_parse_skips_invalid_json_continues_valid() -> None:
    content = (
        '<tool>not json</tool> '
        '<tool>{"name": "ok", "args": {}}</tool>'
    )
    out = parse_plain_text_tool_calls(content)
    assert out is not None
    assert len(out) == 1
    assert out[0]["function"]["name"] == "ok"


def test_parse_skips_block_without_name() -> None:
    content = '<tool>{"args": {"query": "x"}}</tool>'
    out = parse_plain_text_tool_calls(content)
    assert out is None


def test_parse_accepts_name_only_empty_args() -> None:
    content = '<tool>{"name": "searxng_search__search"}</tool>'
    out = parse_plain_text_tool_calls(content)
    assert out is not None
    assert len(out) == 1
    assert out[0]["function"]["name"] == "searxng_search__search"
    assert out[0]["function"]["arguments"] == "{}"


def test_strip_tool_blocks_removes_tags() -> None:
    text = 'Hello <tool>{"name": "x", "args": {}}</tool> world'
    assert strip_tool_blocks(text) == "Hello  world"


def test_strip_tool_blocks_removes_multiple() -> None:
    text = 'A <tool>{"name":"a","args":{}}</tool> B <tool>{"name":"b","args":{}}</tool> C'
    assert "tool" not in strip_tool_blocks(text)
    assert "A" in strip_tool_blocks(text) and "B" in strip_tool_blocks(text) and "C" in strip_tool_blocks(text)


def test_strip_tool_blocks_empty_unchanged() -> None:
    assert strip_tool_blocks("") == ""
    assert strip_tool_blocks("no tags") == "no tags"
