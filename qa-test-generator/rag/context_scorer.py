"""
Context scorer for the RAG pipeline.

Uses the vector-distance scores already returned by ChromaDB to filter
and budget RAG context before LLM injection — zero extra LLM calls.

Distance convention (ChromaDB L2 / cosine): lower = more relevant.
RELEVANCE_THRESHOLD is the upper bound on distance to keep a chunk.
"""

RELEVANCE_THRESHOLD = 0.6   # drop chunks with distance > this
MAX_CONTEXT_CHARS = 3000    # hard cap on total injected context per generation call


def filter_by_relevance(chunks: list[dict], threshold: float = RELEVANCE_THRESHOLD) -> list[dict]:
    """Return only chunks whose ChromaDB distance is within the relevance threshold."""
    return [c for c in chunks if c.get("distance", 1.0) <= threshold]


def _build_block(
    chunks: list[dict],
    title: str,
    char_budget: int,
    meta_fn=None,
) -> tuple[str, int]:
    """
    Build a markdown context block from chunks, respecting char_budget.

    Always includes at least one chunk — truncated to fit the budget if needed —
    so a block is never silently dropped just because a single chunk is large.
    Subsequent chunks are only added if they fit within the remaining budget.

    Returns (block_string, chunks_included_count).
    """
    header = f"### {title}"
    lines = [header]
    used = len(header)

    for i, chunk in enumerate(chunks):
        meta = meta_fn(chunk.get("metadata", {})) if meta_fn else ""
        content = chunk["content"]

        if i == 0:
            # Always include the first chunk; truncate its content to fit the budget
            available = max(200, char_budget - used - len(meta) - 2)
            snippet = content[:available]
            suffix = "..." if len(content) > available else ""
        else:
            snippet = content[:400]
            suffix = "..." if len(content) > 400 else ""
            entry = f"\n{meta}\n{snippet}{suffix}"
            if used + len(entry) > char_budget:
                break

        entry = f"\n{meta}\n{snippet}{suffix}"  # built once; for i>0 this reuses the already-checked values
        lines.append(entry)
        used += len(entry)

    included = len(lines) - 1  # subtract header line
    return "\n".join(lines), included


def score_and_trim(
    test_case_chunks: list[dict],
    knowledge_chunks: list[dict],
    threshold: float = RELEVANCE_THRESHOLD,
    max_chars: int = MAX_CONTEXT_CHARS,
) -> tuple[str, dict]:
    """
    Filter chunks by relevance score, then build a context string within
    the total character budget.

    Budget allocation:
    - If both categories have relevant chunks: split budget 50/50.
    - If only one category has relevant chunks: give it the full budget.

    Returns:
        (context_string, stats_dict)
        stats_dict has keys: before_filter, after_filter, chars_used
    """
    before = len(test_case_chunks) + len(knowledge_chunks)

    relevant_tests = filter_by_relevance(test_case_chunks, threshold)
    relevant_knowledge = filter_by_relevance(knowledge_chunks, threshold)

    after = len(relevant_tests) + len(relevant_knowledge)

    if not relevant_tests and not relevant_knowledge:
        return "", {"before_filter": before, "after_filter": 0, "chars_used": 0}

    # Transfer unused budget: if one category is empty give full budget to the other
    both_present = bool(relevant_tests) and bool(relevant_knowledge)
    tests_budget = (max_chars // 2) if both_present else (max_chars if relevant_tests else 0)
    knowledge_budget = (max_chars // 2) if both_present else (max_chars if relevant_knowledge else 0)

    parts = []
    chars_used = 0

    if relevant_tests:
        block, _ = _build_block(
            relevant_tests,
            "Similar Test Cases",
            tests_budget,
            meta_fn=lambda m: f"**{m.get('feature', '')} · {m.get('test_type', '')}**",
        )
        parts.append(block)
        chars_used += len(block)

    if relevant_knowledge:
        block, _ = _build_block(
            relevant_knowledge,
            "Domain Knowledge",
            knowledge_budget,
            meta_fn=lambda m: f"**{m.get('knowledge_type', 'Info').title()} · {m.get('domain', '')}**",
        )
        parts.append(block)
        chars_used += len(block)

    context = "\n\n".join(parts)
    stats = {"before_filter": before, "after_filter": after, "chars_used": chars_used}
    return context, stats
