"""Tests for offline_tutor.layout using made-up coordinates only.

Glyph boxes use size 12 on a baseline y: y0 = y - 9, y1 = y + 2.
Small (fraction) glyphs use size 8: y0 = y - 6, y1 = y + 2.
"""

from offline_tutor.layout import (
    FRACTION_MAX_GAP,
    FRACTION_X_TOL,
    TABLE_SEPARATOR,
    Bar,
    Token,
    group_table_rows,
    layout_page,
    reading_order,
    stack_fractions,
    wide_gap_lines,
)


def big(text: str, x0: float, x1: float, base: float = 100.0) -> Token:
    return Token(text, x0, base - 9, x1, base + 2, 12)


def num(text: str, x0: float, x1: float, bar_y: float = 96.0) -> Token:
    """Small token whose bottom sits 1 pt above the bar."""
    return Token(text, x0, bar_y - 9, x1, bar_y - 1, 8)


def den(text: str, x0: float, x1: float, bar_y: float = 96.0) -> Token:
    """Small token whose top sits 1 pt below the bar."""
    return Token(text, x0, bar_y + 1, x1, bar_y + 9, 8)


def test_simple_fraction() -> None:
    text, stats, rows = layout_page(
        [num("3", 10, 14), den("7", 10, 14)], [Bar(9, 15, 96)]
    )
    assert text == "3/7"
    assert (stats.merged, stats.ambiguous, rows) == (1, 0, 0)


def test_fraction_parts_with_operators_are_wrapped() -> None:
    rest, fractions, _ = stack_fractions(
        [num("a + 1", 10, 30), den("2", 18, 22)], [Bar(9, 31, 96)]
    )
    assert rest == []
    assert [f.text for f in fractions] == ["(a + 1)/2"]


def test_fraction_inside_equation() -> None:
    tokens = [
        big("2a +", 0, 25),
        num("1", 28, 32),
        den("5", 28, 32),
        big("= 9", 36, 55),
    ]
    text, stats, _ = layout_page(tokens, [Bar(27, 33, 96)])
    assert text == "2a + 1/5 = 9"
    assert stats.merged == 1


def test_two_fractions_side_by_side() -> None:
    tokens = [
        num("p", 10, 14),
        den("4", 10, 14),
        big("-", 18, 24),
        num("q", 28, 32),
        den("6", 28, 32),
    ]
    text, stats, rows = layout_page(tokens, [Bar(9, 15, 96), Bar(27, 33, 96)])
    assert text == "p/4 - q/6"
    assert (stats.merged, stats.ambiguous, rows) == (2, 0, 0)


def test_mixed_number_is_not_interpreted() -> None:
    # Documented behaviour: the whole part stays a separate token, so a mixed
    # number reads "5 2/3". Layout cannot tell it from a coefficient.
    tokens = [big("5", 0, 6), num("2", 8, 12), den("3", 8, 12)]
    text, stats, _ = layout_page(tokens, [Bar(7, 13, 96)])
    assert text == "5 2/3"
    assert stats.merged == 1


def test_table_two_rows_of_seven_cells() -> None:
    xs = [10 + 30 * i for i in range(7)]
    top = ["k", "0", "1", "2", "3", "4", "5"]
    bottom = ["m", "8", "6", "4", "2", "0", "-2"]
    tokens = [big(t, x, x + 8, base=200) for t, x in zip(top, xs, strict=True)]
    tokens += [big(t, x, x + 8, base=220) for t, x in zip(bottom, xs, strict=True)]
    text, _, rows = layout_page(tokens, [])
    assert rows == 2
    assert text.splitlines() == [
        TABLE_SEPARATOR.join(top),
        TABLE_SEPARATOR.join(bottom),
    ]


def test_two_cells_are_not_a_table() -> None:
    table, rest = group_table_rows([big("k", 0, 8), big("m", 40, 48)])
    assert table == []
    assert len(rest) == 2


def test_row_beside_a_fraction_is_not_a_table() -> None:
    # Gaps left by fraction tokens must not turn an equation into a table.
    tokens = [big("a", 0, 6), big("+", 20, 26), big("= 1", 40, 55)]
    fraction = Token("1/2", 9, 87, 15, 105, 8)
    table, rest = group_table_rows(tokens, [fraction])
    assert table == []
    assert len(rest) == 3


def test_ambiguous_two_numerators_left_unmerged() -> None:
    tokens = [num("1", 10, 13), num("2", 15, 18), den("3", 10, 14)]
    rest, fractions, stats = stack_fractions(tokens, [Bar(9, 19, 96)])
    assert fractions == []
    assert stats.ambiguous == 1
    assert rest == tokens


def test_token_shared_by_two_bars_is_ambiguous() -> None:
    # One small token between two bars could be a denominator or a numerator.
    tokens = [
        num("1", 10, 14, 90),
        Token("2", 10, 91, 14, 99, 8),
        den("3", 10, 14, 100),
    ]
    _, fractions, stats = stack_fractions(tokens, [Bar(9, 15, 90), Bar(9, 15, 100)])
    assert fractions == []
    assert stats.ambiguous == 2


def test_never_merges_across_bars() -> None:
    # Numerator over one bar and denominator under another bar.
    tokens = [num("1", 10, 14), den("2", 50, 54)]
    rest, fractions, stats = stack_fractions(tokens, [Bar(9, 15, 96), Bar(49, 55, 96)])
    assert fractions == []
    assert stats.ambiguous == 2
    assert rest == tokens


def test_horizontal_tolerance_edges() -> None:
    bar = Bar(10, 20, 96)
    inside = [num("1", 10 - FRACTION_X_TOL, 14), den("2", 12, 20 + FRACTION_X_TOL)]
    _, fractions, _ = stack_fractions(inside, [bar])
    assert [f.text for f in fractions] == ["1/2"]

    outside = [num("1", 10 - FRACTION_X_TOL - 0.1, 14), den("2", 12, 16)]
    _, fractions, stats = stack_fractions(outside, [bar])
    assert fractions == []
    assert stats.ambiguous == 1


def test_vertical_gap_edges() -> None:
    bar = Bar(10, 20, 100)
    at_limit = [
        Token("1", 11, 85, 15, 100 - FRACTION_MAX_GAP, 8),
        Token("2", 11, 100 + FRACTION_MAX_GAP, 15, 110, 8),
    ]
    _, fractions, _ = stack_fractions(at_limit, [bar])
    assert [f.text for f in fractions] == ["1/2"]

    too_far = [
        Token("1", 11, 85, 15, 100 - FRACTION_MAX_GAP - 0.1, 8),
        Token("2", 11, 100 + FRACTION_MAX_GAP, 15, 110, 8),
    ]
    _, fractions, stats = stack_fractions(too_far, [bar])
    assert fractions == []
    assert stats.ambiguous == 1


def test_reading_order_lines_then_x() -> None:
    tokens = [big("second", 0, 30, base=130), big("b", 40, 50), big("a", 0, 10)]
    assert [line.text for line in reading_order(tokens)] == ["a b", "second"]


def test_touching_spans_join_into_one_run() -> None:
    tokens = [big("2", 0, 6), big("a", 6, 12), big(" + 1", 12, 30)]
    text, _, _ = layout_page(tokens, [])
    assert text == "2a + 1"


def test_empty_input() -> None:
    text, stats, rows = layout_page([], [])
    assert text == ""
    assert (stats.merged, stats.ambiguous, rows) == (0, 0, 0)
    assert stack_fractions([], [Bar(0, 5, 10)])[2].ambiguous == 0
    assert group_table_rows([]) == ([], [])
    assert reading_order([]) == []


def test_wide_gap_line_is_reported() -> None:
    tokens = [big("Left column zorp", 0, 120), big("Right column quux", 170, 290)]
    lines = wide_gap_lines(tokens, [], 40.0)
    assert [line.text for line in lines] == ["Left column zorp Right column quux"]
    assert wide_gap_lines(tokens, [], 50.0) == []  # gap is exactly 50


def test_wide_gap_skips_table_rows_and_fraction_gaps() -> None:
    table = [big(c, x, x + 10, base=200) for c, x in [("a", 0), ("b", 60), ("c", 120)]]
    frac = [big("x =", 0, 20), num("1", 70, 75), den("2", 70, 75)]
    assert wide_gap_lines(table + frac, [Bar(70, 76, 96)], 40.0) == []
