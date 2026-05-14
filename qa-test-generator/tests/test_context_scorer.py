"""Unit tests for pure functions in rag/context_scorer.py."""

import pytest
from rag.context_scorer import (
    filter_by_relevance,
    _build_block,
    score_and_trim,
    RELEVANCE_THRESHOLD,
    MAX_CONTEXT_CHARS,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _chunk(content: str, distance: float = 0.3, **meta) -> dict:
    return {"content": content, "distance": distance, "metadata": meta}


# ── filter_by_relevance ───────────────────────────────────────────────────────

def test_filter_keeps_within_threshold():
    chunks = [_chunk("relevant", distance=0.3), _chunk("irrelevant", distance=0.9)]
    result = filter_by_relevance(chunks)
    assert len(result) == 1
    assert result[0]["content"] == "relevant"


def test_filter_keeps_exactly_at_threshold():
    chunks = [_chunk("edge", distance=RELEVANCE_THRESHOLD)]
    assert filter_by_relevance(chunks) == chunks


def test_filter_drops_above_threshold():
    chunks = [_chunk("too far", distance=RELEVANCE_THRESHOLD + 0.01)]
    assert filter_by_relevance(chunks) == []


def test_filter_empty_input():
    assert filter_by_relevance([]) == []


def test_filter_missing_distance_treated_as_irrelevant():
    chunk = {"content": "no distance", "metadata": {}}
    # default distance=1.0 > threshold — should be dropped
    assert filter_by_relevance([chunk]) == []


def test_filter_custom_threshold():
    chunks = [_chunk("ok", distance=0.4), _chunk("too far", distance=0.6)]
    result = filter_by_relevance(chunks, threshold=0.5)
    assert len(result) == 1
    assert result[0]["content"] == "ok"


# ── _build_block ──────────────────────────────────────────────────────────────

def test_build_block_includes_header():
    chunks = [_chunk("some content")]
    block, count = _build_block(chunks, "My Title", char_budget=2000)
    assert "### My Title" in block
    assert count == 1


def test_build_block_always_includes_first_chunk():
    # Even with a tiny budget, the first chunk is always included (possibly truncated)
    chunks = [_chunk("A" * 5000)]
    block, count = _build_block(chunks, "T", char_budget=100)
    assert count == 1
    assert "A" in block


def test_build_block_truncates_first_chunk_with_ellipsis():
    chunks = [_chunk("A" * 5000)]
    block, _ = _build_block(chunks, "T", char_budget=300)
    assert "..." in block


def test_build_block_no_ellipsis_when_fits():
    chunks = [_chunk("short")]
    block, _ = _build_block(chunks, "T", char_budget=2000)
    assert not block.endswith("...")


def test_build_block_adds_second_chunk_when_budget_allows():
    chunks = [_chunk("first"), _chunk("second")]
    block, count = _build_block(chunks, "T", char_budget=2000)
    assert count == 2
    assert "first" in block
    assert "second" in block


def test_build_block_stops_adding_when_budget_exceeded():
    # Make each chunk large enough that only first fits
    chunks = [_chunk("A" * 100), _chunk("B" * 1000)]
    block, count = _build_block(chunks, "T", char_budget=200)
    # Second chunk won't fit
    assert count == 1


def test_build_block_meta_fn_applied():
    chunks = [_chunk("content", feature="Login", test_type="manual")]
    block, _ = _build_block(
        chunks, "Title", char_budget=2000,
        meta_fn=lambda m: f"**{m.get('feature')}**"
    )
    assert "**Login**" in block


# ── score_and_trim ────────────────────────────────────────────────────────────

def test_score_and_trim_both_empty():
    ctx, stats = score_and_trim([], [])
    assert ctx == ""
    assert stats["before_filter"] == 0
    assert stats["after_filter"] == 0
    assert stats["chars_used"] == 0


def test_score_and_trim_all_irrelevant():
    chunks = [_chunk("x", distance=0.99)]
    ctx, stats = score_and_trim(chunks, chunks)
    assert ctx == ""
    assert stats["after_filter"] == 0


def test_score_and_trim_only_test_chunks():
    tests = [_chunk("test chunk", distance=0.2)]
    ctx, stats = score_and_trim(tests, [])
    assert "Similar Test Cases" in ctx
    assert "Domain Knowledge" not in ctx
    assert stats["after_filter"] == 1


def test_score_and_trim_only_knowledge_chunks():
    knowledge = [_chunk("domain knowledge", distance=0.1)]
    ctx, stats = score_and_trim([], knowledge)
    assert "Domain Knowledge" in ctx
    assert "Similar Test Cases" not in ctx


def test_score_and_trim_both_present():
    tests = [_chunk("test", distance=0.2)]
    knowledge = [_chunk("knowledge", distance=0.1)]
    ctx, stats = score_and_trim(tests, knowledge)
    assert "Similar Test Cases" in ctx
    assert "Domain Knowledge" in ctx
    assert stats["after_filter"] == 2


def test_score_and_trim_respects_max_chars():
    big_content = "X" * 10000
    tests = [_chunk(big_content, distance=0.1)]
    ctx, stats = score_and_trim(tests, [], max_chars=500)
    assert stats["chars_used"] <= 600  # small slack for header/metadata overhead


def test_score_and_trim_stats_before_vs_after():
    # 2 test chunks: 1 relevant, 1 not. 1 knowledge chunk: relevant.
    tests = [_chunk("ok", distance=0.2), _chunk("bad", distance=0.9)]
    knowledge = [_chunk("good", distance=0.1)]
    _, stats = score_and_trim(tests, knowledge)
    assert stats["before_filter"] == 3
    assert stats["after_filter"] == 2
