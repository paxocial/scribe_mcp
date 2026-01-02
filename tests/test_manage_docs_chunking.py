"""Tests for manage_docs vector chunking behavior."""

from scribe_mcp.tools.manage_docs import _chunk_text_for_vector


def test_chunking_splits_on_headings() -> None:
    text = (
        "# Section One\n"
        "Alpha paragraph.\n"
        "\n"
        "## Section Two\n"
        "Beta paragraph."
    )
    chunks = _chunk_text_for_vector(text, max_chars=1000)
    assert len(chunks) == 2
    assert chunks[0].startswith("# Section One")
    assert chunks[1].startswith("## Section Two")


def test_chunking_repeats_heading_when_split() -> None:
    text = (
        "## Split Section\n"
        "Para one is long enough to push over limit.\n\n"
        "Para two is also present and should force a split."
    )
    chunks = _chunk_text_for_vector(text, max_chars=40)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.startswith("## Split Section")
