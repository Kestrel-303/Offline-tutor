"""Tests for the lesson chunker. All strings are made up."""

from offline_tutor.chunk import (
    HARD_MAX,
    MIN_CHARS,
    Chunk,
    chunk_pages,
    chunk_pages_with_stats,
    classify_label,
    drop_label_only,
    find_section_pages,
    match_heading,
    split_examples,
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
        ("example", "4.1 Alpha > Example 1"),
        ("exercise", "4.1 Alpha > Exercise 4.1"),
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


def test_introduction_before_first_section_is_dropped() -> None:
    pages = [(3, _sentences(8, "intro") + "\n\n4.1 Alpha\n" + _sentences(5))]
    chunks, stats = chunk_pages_with_stats(pages)
    assert stats.intro_blocks_dropped == 1
    assert [c.section for c in chunks] == ["4.1"]
    assert "intro" not in chunks[0].text
    assert chunks[0].text.startswith("4.1 Alpha\n")


def test_heading_carries_subsection_title() -> None:
    text = "\n".join(
        [
            "4.1 Alpha topic",
            _sentences(5),
            "Example 1",
            _sentences(5, "zorp"),
            "4.1.2 Zorp by",
            "tables",
            _sentences(5),
            "Example 2",
            _sentences(5, "zorp"),
            "Activity 4.3",
            _sentences(5, "quux"),
            "4.2 Beta",
            _sentences(5),
            "Exercise 4.2",
            _sentences(5, "quux"),
        ]
    )
    headings = [(c.kind, c.heading) for c in chunk_pages([(1, text)])]
    assert headings == [
        ("explanation", ""),
        ("example", "4.1 Alpha topic > Example 1"),
        ("explanation", "4.1.2 Zorp by tables"),
        ("example", "4.1.2 Zorp by tables > Example 2"),
        ("exercise", "4.1.2 Zorp by tables > Activity 4.3"),
        ("explanation", ""),
        ("exercise", "4.2 Beta > Exercise 4.2"),
    ]


def test_tiny_label_only_chunk_is_dropped() -> None:
    label_only = Chunk("4.1", "A", "Summary", "summary", 1, 1, "Summary\n4.1.1 Zorp")
    body = Chunk("4.1", "A", "Example 1", "example", 1, 1, "Example 1\nZorp.")
    kept, dropped = drop_label_only([label_only, body])
    assert dropped == 1
    assert kept == [body]


def test_label_only_text_of_100_chars_is_kept() -> None:
    text = "Example 1\n4.1.1 " + "Z" * 84  # exactly 100 chars, all labels
    assert len(text) == 100
    c = Chunk("4.1", "Alpha", "", "example", 1, 1, text)
    assert drop_label_only([c]) == ([c], 0)


def test_multi_example_chunk_is_split_at_each_label() -> None:
    text = "Example 1\nZorp one.\n\nExample 2\nZorp two.\nExample 3:\nZorp three."
    c = Chunk("4.1", "Alpha", "4.1.1 Zorps > Example 1", "example", 2, 3, text)
    out, n = split_examples([c])
    assert n == 1
    assert [(x.heading, x.text) for x in out] == [
        ("4.1.1 Zorps > Example 1", "Example 1\nZorp one."),
        ("4.1.1 Zorps > Example 2", "Example 2\nZorp two."),
        ("4.1.1 Zorps > Example 3", "Example 3:\nZorp three."),
    ]
    assert all((x.page_start, x.page_end) == (2, 3) for x in out)


def test_split_example_pieces_stay_within_hard_max() -> None:
    big = _sentences(40, "zorp")  # about 2000 chars
    text = f"Example 1\n{big}\nExample 2\nZorp two."
    out, _ = split_examples([Chunk("4.1", "A", "Example 1", "example", 1, 1, text)])
    assert len(out) > 2
    assert all(len(x.text) <= HARD_MAX for x in out)
    assert out[-1].text == "Example 2\nZorp two."
    assert out[-1].heading == "Example 2"


def test_merged_tiny_examples_end_up_split() -> None:
    text = "4.1 Alpha\n" + _sentences(5) + "\nExample 1\nZorp.\nExample 2\nQuux."
    examples = [c for c in chunk_pages([(1, text)]) if c.kind == "example"]
    assert [c.heading for c in examples] == [
        "4.1 Alpha > Example 1",
        "4.1 Alpha > Example 2",
    ]
    assert [c.text for c in examples] == ["Example 1\nZorp.", "Example 2\nQuux."]
