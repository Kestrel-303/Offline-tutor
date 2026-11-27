"""Tests for the router. All questions and lesson strings are made up."""

import subprocess
import sys
from pathlib import Path
from typing import get_args

import pytest

from offline_tutor.chunk import Chunk
from offline_tutor.equations import Classification
from offline_tutor.lesson_db import create_db, insert_chunks
from offline_tutor.router import (
    EQUATION_ACTIONS,
    GENERIC_HEADING_WORDS,
    MIN_ANCHOR_LENGTH,
    MIN_COVERAGE,
    OUT_OF_LESSON_TERMS,
    REFUSAL_MESSAGE,
    STOPWORDS,
    TYPO_MIN_LENGTH,
    Lexicon,
    anchor_matches,
    build_lexicon,
    content_stems,
    content_words,
    edit_distance,
    route,
    stem,
)

SRC = Path(__file__).resolve().parents[1] / "src"


def _lexicon(text: str, heading: str) -> Lexicon:
    return Lexicon(
        frozenset(content_stems(text) | content_stems(heading)),
        frozenset(content_stems(heading, GENERIC_HEADING_WORDS)),
    )


@pytest.fixture
def lex() -> Lexicon:
    return _lexicon(
        "To solve a linear equation, move the variable terms to one side and"
        " the constants to the other side, then divide by the coefficient.",
        "Solving linear equations in one variable",
    )


EMPTY = Lexicon(frozenset(), frozenset())


# --- constants ---------------------------------------------------------------


def test_constants_are_fixed() -> None:
    assert MIN_COVERAGE == 0.6
    assert REFUSAL_MESSAGE == "I can't help with that"
    assert len(STOPWORDS) == 102
    assert GENERIC_HEADING_WORDS == {
        "example",
        "activity",
        "exercise",
        "unit",
        "section",
        "introduction",
        "review",
    }


def test_every_engine_label_has_an_action() -> None:
    assert set(EQUATION_ACTIONS) == set(get_args(Classification))
    assert EQUATION_ACTIONS["linear_one_var"] == "solve"
    assert EQUATION_ACTIONS["nonlinear"] == "refuse"


def test_banned_terms_are_ascii_and_sorted_stems() -> None:
    assert OUT_OF_LESSON_TERMS
    assert all(t.isascii() and t.isalpha() and t.islower() for t in OUT_OF_LESSON_TERMS)


def test_banned_terms_exact() -> None:
    assert OUT_OF_LESSON_TERMS == {
        "applic",
        "congruenc",
        "dimens",
        "inequ",
        "non",
        "polygon",
        "probabl",
        "statist",
        "trigonometri",
        "vector",
    }


@pytest.mark.parametrize("word", ["further", "regular", "similar", "summary"])
def test_ordinary_words_not_banned_by_default(word: str, lex: Lexicon) -> None:
    assert stem(word) not in OUT_OF_LESSON_TERMS
    assert route(f"solve a {word} linear equation", lex).banned_hits == ()


# --- stemming ----------------------------------------------------------------


@pytest.mark.parametrize(
    "words",
    [
        ("eliminate", "elimination"),
        ("equation", "equations"),
        ("solve", "solving", "solved"),
        ("substitute", "substitution"),
    ],
)
def test_stem_groups_word_forms(words: tuple[str, ...]) -> None:
    assert len({stem(w) for w in words}) == 1


def test_stem_is_deterministic() -> None:
    assert stem("variables") == stem("variables")


# --- tokenizing --------------------------------------------------------------


def test_stopwords_and_single_letters_dropped() -> None:
    assert content_words("What is the x of 7 apples? Tell me y!") == ["apples"]


def test_digits_and_symbols_ignored() -> None:
    assert content_words("3.2.1 + (zebra) * 42") == ["zebra"]


def test_extra_stopwords() -> None:
    assert content_words("Example 2: zebra", GENERIC_HEADING_WORDS) == ["zebra"]


@pytest.mark.parametrize("question", ["", "What is it?", "x y z", "123 + 4", "?!"])
def test_no_content_words(question: str, lex: Lexicon) -> None:
    d = route(question, lex)
    assert (d.route, d.reason) == ("refuse", "no_content_words")


# --- word rules --------------------------------------------------------------


def test_lesson_match(lex: Lexicon) -> None:
    d = route("How do I solve a linear equation?", lex)
    assert (d.route, d.reason) == ("explain_lesson", "lesson_match")
    assert d.coverage == 1.0
    assert d.unmatched == ()
    assert stem("solve") in d.anchor_hits


def test_banned_term_beats_perfect_coverage() -> None:
    lexicon = _lexicon("trigonometry", "trigonometry")
    banned = frozenset({stem("trigonometry")})
    d = route("Explain trigonometry", lexicon, banned=banned)
    assert (d.route, d.reason) == ("refuse", "out_of_lesson_term")
    assert d.coverage == 1.0
    assert d.banned_hits == (stem("trigonometry"),)


def test_high_coverage_without_anchor(lex: Lexicon) -> None:
    d = route("Divide the constants", lex)
    assert (d.route, d.reason) == ("refuse", "no_anchor_term")
    assert d.coverage == 1.0
    assert d.anchor_hits == ()


BOUNDARY = Lexicon(
    frozenset({stem("solve"), stem("linear"), stem("equation")}),
    frozenset({stem("solve")}),
)


@pytest.mark.parametrize(
    ("question", "coverage", "expected"),
    [
        ("solve linear equation zebra giraffe", 0.6, "explain_lesson"),  # 3 of 5
        ("solve linear zebra giraffe", 0.5, "refuse"),  # 2 of 4
        ("solve linear equation zebra", 0.75, "explain_lesson"),  # 3 of 4
    ],
)
def test_coverage_boundary(question: str, coverage: float, expected: str) -> None:
    d = route(question, BOUNDARY, banned=frozenset())
    assert d.coverage == coverage
    assert d.route == expected
    if expected == "refuse":
        assert d.reason == "low_coverage"
        assert d.unmatched == (stem("giraffe"), stem("zebra"))


def test_off_topic_refused(lex: Lexicon) -> None:
    assert route("What is the capital of France?", lex).route == "refuse"


# --- equation rule -----------------------------------------------------------


def test_linear_equation_wins_with_empty_lexicon() -> None:
    d = route("solve 4h + 6 = 0", EMPTY)
    assert (d.route, d.reason) == ("solve_equation", "equation_detected")
    assert d.equation_label == "linear_one_var"
    assert d.coverage is None


def test_nonlinear_equation_refused(lex: Lexicon) -> None:
    d = route("solve x^2 = 4", lex)
    assert (d.route, d.reason) == ("refuse", "nonlinear_equation")
    assert d.equation_label == "nonlinear"


def test_system_goes_to_word_rules(lex: Lexicon) -> None:
    d = route("solve x + y = 5, x - y = 1", lex)
    assert d.equation_label == "system"
    assert d.reason not in ("equation_detected", "nonlinear_equation")


def test_no_equation_label_recorded(lex: Lexicon) -> None:
    assert route("solve a linear equation", lex).equation_label == "no_equation"


def test_deterministic(lex: Lexicon) -> None:
    q = "Can you explain how to solve equations with one variable?"
    assert route(q, lex) == route(q, lex)


# --- isolation ---------------------------------------------------------------


def test_router_does_not_import_a_language_model() -> None:
    code = (
        "import sys, offline_tutor.router; "
        "print('llama_cpp' in sys.modules, 'ollama' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": str(SRC), "SYSTEMROOT": "C:\\Windows"},
    )
    assert out.stdout.strip() == "False False"


# --- lexicon -----------------------------------------------------------------


def test_build_lexicon_read_only(tmp_path: Path) -> None:
    db = tmp_path / "lessons.db"
    conn = create_db(db)
    insert_chunks(
        conn,
        [
            Chunk(
                "9.1",
                "Zorp",
                "Example 1 > Substitution method",
                "example",
                1,
                1,
                "Substitute the zorp value.",
            ),
            Chunk(
                "9.1",
                "Zorp",
                "Exercises for review",
                "exercise",
                2,
                2,
                "Practice flarging.",
            ),
        ],
    )
    conn.close()
    before = db.read_bytes()

    lexicon = build_lexicon(db)

    assert db.read_bytes() == before
    assert {stem("substitution"), stem("method")} <= lexicon.anchors
    for generic in ("example", "exercises", "review"):
        assert stem(generic) not in lexicon.anchors
    assert {stem("zorp"), stem("flarging"), stem("practice")} <= lexicon.vocabulary


def test_build_lexicon_drops_short_anchors(tmp_path: Path) -> None:
    assert MIN_ANCHOR_LENGTH == 3
    db = tmp_path / "lessons.db"
    conn = create_db(db)
    insert_chunks(
        conn,
        [
            Chunk(
                "9.1",
                "Zorp",
                "Zorp equations in one variable using tables",
                "explanation",
                1,
                1,
                "Flarge the zorp.",
            )
        ],
    )
    conn.close()

    lexicon = build_lexicon(db)

    assert stem("one") == "on" and stem("using") == "us"
    assert "on" not in lexicon.anchors
    assert "us" not in lexicon.anchors
    assert "variabl" in lexicon.anchors
    assert {"on", "us"} <= lexicon.vocabulary


# --- typed systems -----------------------------------------------------------


@pytest.mark.parametrize("question", ["x + y = 5, x - y = 1", "2x + y = 4; x = 1 + y"])
def test_typed_system_explains_without_words(question: str) -> None:
    d = route(question, EMPTY)
    assert (d.route, d.reason) == ("explain_lesson", "typed_system")
    assert d.equation_label == "system"
    assert d.coverage is None


def test_typed_system_with_banned_term_refused() -> None:
    term = next(t for t in sorted(OUT_OF_LESSON_TERMS) if stem(t) == t)
    d = route(f"{term} x + y = 5, x - y = 1", EMPTY)
    assert (d.route, d.reason) == ("refuse", "out_of_lesson_term")
    assert d.banned_hits == (term,)
    assert d.equation_label == "system"


def test_typed_system_with_only_stopwords() -> None:
    d = route("what is x + y = 5 and x - y = 1", EMPTY)
    assert (d.route, d.reason) == ("explain_lesson", "typed_system")


def test_plain_typed_system() -> None:
    d = route("x + y = 5, x - y = 1", EMPTY)
    assert (d.route, d.reason) == ("explain_lesson", "typed_system")


def test_system_with_nonlinear_equation_refused(lex: Lexicon) -> None:
    d = route("solve x^2 + y = 5, x - y = 1", lex)
    assert (d.route, d.reason) == ("refuse", "nonlinear_equation")


def test_single_linear_equation_still_solved() -> None:
    d = route("solve 3k - 2 = 7", EMPTY)
    assert (d.route, d.reason) == ("solve_equation", "equation_detected")


# --- inequality signs --------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    ["Solve 5x < 20", "5x > 20", "x \u2265 3", "2x \u2264 8", "x >= 1", "x <= 1"],
)
def test_inequality_sign_refused(question: str, lex: Lexicon) -> None:
    d = route(question, lex)
    assert (d.route, d.reason) == ("refuse", "inequality_sign")


@pytest.mark.parametrize("question", ["equation -> steps", "linear equation => solve"])
def test_arrows_are_not_inequalities(question: str, lex: Lexicon) -> None:
    assert route(question, lex).reason != "inequality_sign"


# --- anchor typos ------------------------------------------------------------


def test_edit_distance() -> None:
    assert edit_distance("linaar", "linear") == 1  # substitution
    assert edit_distance("varibl", "variabl") == 1  # deletion
    assert edit_distance("variabl", "varibl") == 1  # insertion
    assert edit_distance("linaer", "linear") == 2  # transposition
    assert edit_distance("", "abc") == 3
    assert edit_distance("same", "same") == 0


@pytest.fixture
def elim_lex() -> Lexicon:
    return _lexicon(
        "Add the two equations to eliminate one variable, then solve.",
        "Elimination method for linear equations in two variables",
    )


@pytest.mark.parametrize(
    ("question", "anchor"),
    [
        ("explain eliminashun", "elimin"),  # prefix
        ("solve linaar equations", "linear"),  # one substitution
        ("eliminate a varible", "variabl"),  # one deletion
    ],
)
def test_misspelled_anchor_passes_anchor_step(
    question: str, anchor: str, elim_lex: Lexicon
) -> None:
    assert TYPO_MIN_LENGTH == 5
    d = route(question, elim_lex)
    assert d.reason != "no_anchor_term"
    assert anchor in d.anchor_hits


def test_short_near_match_is_not_an_anchor(lex: Lexicon) -> None:
    assert stem("salving") == "salv" and stem("eqations") == "eqat"
    assert anchor_matches("salv", lex.anchors) == ()  # 4 vs 4 letters
    assert anchor_matches("eqat", lex.anchors) == ()  # 4 vs 5 letters
    d = route("salving eqations", lex)
    assert (d.route, d.reason) == ("refuse", "no_anchor_term")


def test_typo_does_not_reach_coverage_or_banned(elim_lex: Lexicon) -> None:
    d = route("eliminashun", elim_lex)
    assert d.unmatched == ("eliminashun",)
    assert d.banned_hits == ()


@pytest.mark.parametrize(
    "question", ["what is the capital of France", "explain polygons"]
)
def test_off_topic_still_refused(question: str, elim_lex: Lexicon) -> None:
    assert route(question, elim_lex).route == "refuse"
