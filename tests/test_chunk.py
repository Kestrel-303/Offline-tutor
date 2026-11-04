"""Tests for the lesson chunker. All strings are made up."""

from offline_tutor.chunk import (
    HARD_MAX,
    MIN_CHARS,
    chunk_pages,
    classify_label,
    find_section_pages,
    match_heading,
)

# Non-ASCII test characters, built with chr() so the formatter keeps the
# source ASCII-only.
E_ACUTE = chr(0x00E9)
LE = chr(0x2264)


def _sentences(n: int, word: str = "lorem") -> str:
    """n made-up lines of about 50 chars, each ending a sentence."""
    return "\n".join(
        f"Line {i} says {word} ipsum dolor sit amet blah." for i in range(n)
    )


def test_match_heading_levels() -> None:
    assert match_heading("4.2 Zorp equations") == ("4.2", "Zorp equations")
    assert match_heading("4.2.1 Zorp by tables") == ("4.2.1", "Zorp by tables")


def test_match_heading_rejects_numbers_and_long_lines() -> None:
    assert match_heading("100.00. Find the cost.") is None
    assert match_heading("4.2 " + "Long " * 30) is None
    assert match_heading("x = 4.2") is None


def test_classify_label_kinds() -> None:
    assert classify_label("Example 3") == "example"
    assert classify_label("Example") == "example"
    assert classify_label("Exercise 4.1") == "exercise"
    assert classify_label("Activity 4.2") == "exercise"
    assert classify_label("Summary") == "summary"
    assert classify_label("Definition 4.1") == "explanation"
    assert classify_label("Remark:") == "explanation"


def test_classify_label_ignores_prose_starting_with_label_word() -> None:
    assert classify_label("Note that zorps are blue.") is None
    assert classify_label("Example 3 shows a zorp.") is None


def test_find_section_pages_skips_contents_page() -> None:
    contents = "4.1 Alpha\n4.2 Beta\n4.3 Gamma"
    pages = [(10, contents), (11, "4.1 Alpha\nText."), (14, "4.2 Beta\nMore.")]
    assert find_section_pages(pages) == {"4.1": 11, "4.2": 14}


def test_sections_and_subheading_metadata() -> None:
    text = (
        "4.1 Alpha topic\n"
        + _sentences(5)
        + "\n\n4.1.1 Zorp by\ntables\n"
        + _sentences(5)
    )
    chunks = chunk_pages([(7, text)])
    assert [c.section for c in chunks] == ["4.1", "4.1"]
    assert chunks[0].section_title == "Alpha topic"
    assert chunks[0].heading == ""
    assert chunks[1].heading == "4.1.1 Zorp by tables"
    assert chunks[1].text.startswith("4.1.1 Zorp by\ntables\n")


def test_kind_from_labels() -> None:
    text = "\n".join(
        [
            "4.1 Alpha",
            _sentences(5),
            "Example 1",
            _sentences(5, "zorp"),
            "Exercise 4.1",
            _sentences(5, "quux"),
            "Summary",
            _sentences(5, "wibble"),
        ]
    )
    chunks = chunk_pages([(1, text)])
    assert [(c.kind, c.heading) for c in chunks] == [
        ("explanation", ""),
        ("example", "Example 1"),
        ("exercise", "Exercise 4.1"),
        ("summary", "Summary"),
    ]
    assert chunks[1].text.startswith("Example 1\n")


def test_heading_followed_directly_by_heading_stays_with_text() -> None:
    text = "4.2 Beta\n4.2.1 Beta by tables\n" + _sentences(5)
    chunks = chunk_pages([(1, text)])
    assert len(chunks) == 1
    assert chunks[0].text.startswith("4.2 Beta\n4.2.1 Beta by tables\n")
    assert chunks[0].section == "4.2"


def test_oversize_paragraph_is_split_within_limit() -> None:
    chunks = chunk_pages([(1, "4.1 Alpha\n" + _sentences(60))])
    assert len(chunks) > 1
    assert all(len(c.text) <= HARD_MAX for c in chunks)
    assert chunks[0].text.startswith("4.1 Alpha\n")


def test_single_huge_line_is_split_at_sentences() -> None:
    line = " ".join(f"Zorp {i} is blue." for i in range(300))
    chunks = chunk_pages([(1, "4.1 Alpha\n" + line)])
    assert len(chunks) > 1
    assert all(len(c.text) <= HARD_MAX for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)


def test_example_under_hard_max_stays_whole() -> None:
    body = _sentences(22, "zorp")  # about 1100 chars, above TARGET_MAX
    text = "4.1 Alpha\n" + _sentences(5) + "\nExample 2\n" + body
    examples = [c for c in chunk_pages([(1, text)]) if c.kind == "example"]
    assert len(examples) == 1
    assert examples[0].text == "Example 2\n" + body


def test_tiny_chunk_merges_into_previous_same_kind() -> None:
    text = "4.1 Alpha\n" + _sentences(6) + "\nDefinition 4.1\nA zorp is blue."
    chunks = chunk_pages([(1, text)])
    assert len(chunks) == 1
    assert chunks[0].text.endswith("Definition 4.1\nA zorp is blue.")
    assert chunks[0].heading == ""


def test_tiny_chunk_not_merged_across_kind() -> None:
    text = "4.1 Alpha\n" + _sentences(6) + "\nExample 1\nZorp."
    chunks = chunk_pages([(1, text)])
    assert [c.kind for c in chunks] == ["explanation", "example"]
    assert len(chunks[1].text) < MIN_CHARS


def test_chunk_spans_pages() -> None:
    pages = [(5, "4.1 Alpha\n" + _sentences(3)), (6, _sentences(3, "zorp"))]
    chunks = chunk_pages(pages)
    assert len(chunks) == 1
    assert (chunks[0].page_start, chunks[0].page_end) == (5, 6)


def test_chunks_never_end_mid_line() -> None:
    text = "4.1 Alpha\n" + _sentences(50) + "\n\n" + _sentences(30, "zorp")
    lines = set(text.split("\n"))
    for c in chunk_pages([(1, text)]):
        for line in c.text.split("\n"):
            assert line == "" or line in lines


def test_non_ascii_text_is_kept() -> None:
    text = "4.1 Alpha\n" + _sentences(4) + f"\nZorp {E_ACUTE}quation {LE} 3."
    chunks = chunk_pages([(1, text)])
    assert f"{E_ACUTE}quation {LE}" in chunks[0].text
