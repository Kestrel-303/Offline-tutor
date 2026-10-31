"""Tests for the page normalizer. All strings are made up."""

from offline_tutor.normalize import (
    BRACKET_MAP,
    join_split_equations,
    normalize_page,
    normalize_page_with_stats,
)


def test_nfkc_math_italic_letters_become_plain() -> None:
    assert normalize_page("\U0001d465 + \U0001d466 = 3") == "x + y = 3"


def test_minus_sign_becomes_hyphen() -> None:
    assert normalize_page("5 − 2 = 3") == "5 - 2 = 3"


def test_curly_quotes_become_straight() -> None:
    assert normalize_page("“foo” and ‘bar’") == "\"foo\" and 'bar'"


def test_bullet_becomes_dash() -> None:
    assert normalize_page("• first item") == "- first item"


def test_replacement_character_removed() -> None:
    assert normalize_page("ab�c") == "abc"


def test_dotted_leaders_removed() -> None:
    assert normalize_page("Topic one........ 12x") == "Topic one 12x"
    assert normalize_page("Topic two . . . . . 7x") == "Topic two 7x"
    assert normalize_page("Topic three…… 9x") == "Topic three 9x"


def test_single_ellipsis_kept() -> None:
    assert normalize_page("1, 2, 3, ...") == "1, 2, 3, ..."
    assert normalize_page("1, 2, …") == "1, 2, ..."


def test_bracket_map() -> None:
    assert BRACKET_MAP == {"ሺ": "(", "ሻ": ")"}
    assert normalize_page("2ሺx + 1ሻ = 6") == "2(x + 1) = 6"


def test_header_and_page_number_stripped() -> None:
    text = "  Unit 7: Made Up Title Here\nBody line.\n\n 42 \n"
    assert normalize_page(text) == "Body line."


def test_header_with_other_number_and_title() -> None:
    assert normalize_page("Unit 12 : Another Fake Topic\nBody.") == "Body."


def test_unit_line_not_first_is_kept() -> None:
    text = "Intro line.\nUnit 3: Kept Because Not First\nMore."
    assert normalize_page(text) == text


def test_number_not_last_is_kept() -> None:
    assert normalize_page("Body.\n42\nEnd.") == "Body.\n42\nEnd."


def test_whitespace_cleanup() -> None:
    text = "   a   b  \t c   \n\n\n\n\nnext    line   \n\n\nthird"
    assert normalize_page(text) == "a b c\n\nnext line\n\n\nthird"


def test_join_line_ending_in_equals() -> None:
    assert normalize_page("2x + 3 =\n11\nend") == "2x + 3 = 11\nend"


def test_join_line_ending_in_operator() -> None:
    assert normalize_page("3x +\n4 = 10") == "3x + 4 = 10"
    assert normalize_page("7 -\nx = 2") == "7 - x = 2"
    assert normalize_page("6 ×\n(x + 1)") == "6 × (x + 1)"


def test_join_chain() -> None:
    assert normalize_page("y =\n2x +\n5\nend") == "y = 2x + 5\nend"


def test_join_count() -> None:
    result = normalize_page_with_stats("a =\n1\nb =\n2\nend")
    assert result == ("a = 1\nb = 2\nend", 2)


def test_no_join_word_hyphenation() -> None:
    assert normalize_page("a well-\nknown fact") == "a well-\nknown fact"


def test_no_join_across_blank_line() -> None:
    assert normalize_page("x =\n\n4\nend") == "x =\n\n4\nend"


def test_no_join_long_next_line() -> None:
    text = "so we get =\nthis line is far too long to be an equation part"
    assert normalize_page(text) == text


def test_no_join_bullet_next_line() -> None:
    assert normalize_page("x =\n• item") == "x =\n- item"


def test_no_join_without_trailing_operator() -> None:
    assert normalize_page("x = 4\n5\nend") == "x = 4\n5\nend"


def test_join_split_equations_direct() -> None:
    assert join_split_equations("") == ("", 0)
    assert join_split_equations("a /\nb") == ("a / b", 1)


def test_bare_number_as_last_line_is_dropped() -> None:
    # Known limitation: a final short number line is treated as a page number
    # even when it is an equation result, so it is removed before joining.
    assert normalize_page("x =\n4") == "x ="


def test_empty_page() -> None:
    assert normalize_page("") == ""
    assert normalize_page("  \n \n") == ""
