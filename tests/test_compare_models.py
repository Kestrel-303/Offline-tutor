import json
from pathlib import Path

import pytest
from compare_models import (
    ALL_X,
    NO_SOLUTION,
    check_answer,
    clean_answer,
    contains_latex,
    extract_final_answer,
    is_refusal,
    solution_set,
)

QUESTIONS = Path(__file__).parent / "data" / "questions.json"


@pytest.mark.parametrize(
    "answer", ["x=4", "x = 4", "4=x", "4", "8/2", "4.0", "x = 8/2", "2x = 8", "$x = 4$"]
)
def test_equivalent_answers_are_correct(answer: str) -> None:
    assert check_answer(answer, "4")


@pytest.mark.parametrize("answer", ["x = 5", "-4", "x = 4.1", "0.4", "x = 1/4"])
def test_wrong_answers_are_rejected(answer: str) -> None:
    assert not check_answer(answer, "4")


@pytest.mark.parametrize(
    "answer", ["", "banana", "x = y", "x = 4 = 5", "import os", None, NO_SOLUTION]
)
def test_unparseable_or_mismatched_answers_are_rejected(answer: str | None) -> None:
    assert not check_answer(answer, "4")


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [("x = \u22125", "x = -5"), ("3 \u00d7 4", "3 * 4"), ("8 \u00f7 2", "8 / 2")],
)
def test_clean_answer_maps_unicode_signs(raw: str, cleaned: str) -> None:
    assert clean_answer(raw) == cleaned


def test_unicode_signs_are_graded() -> None:
    assert check_answer("x = \u22125", "-5")
    assert check_answer("8 \u00f7 2", "4")
    assert check_answer("2 \u00d7 2", "4")


def test_fraction_and_decimal_are_equivalent() -> None:
    assert check_answer("x = 0.75", "3/4")
    assert check_answer("3/4", "0.75")


@pytest.mark.parametrize(
    "answer", ["no solution", "No solution.", "There are no solutions", "0 = 3"]
)
def test_no_solution_answers(answer: str) -> None:
    assert check_answer(answer, "no solution")
    assert not check_answer(answer, "all x")
    assert not check_answer(answer, "4")


@pytest.mark.parametrize(
    "answer", ["all x", "All real numbers", "infinitely many solutions", "x = x"]
)
def test_all_x_answers(answer: str) -> None:
    assert check_answer(answer, "all x")
    assert not check_answer(answer, "no solution")


def test_number_is_not_no_solution() -> None:
    assert not check_answer("x = 4", "no solution")


def test_solution_set_kinds() -> None:
    assert solution_set("2(x + 1) = 2x + 5") == NO_SOLUTION
    assert solution_set("3(x - 1) = 3x - 3") == ALL_X
    assert solution_set("5(x - 2) = 3x + 4") == 7


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("Subtract 3: 2x = 8. Divide by 2.\nFinal answer: x = 4", "x = 4"),
        ("Steps...\n**Final answer:** x = 4.", "x = 4"),
        ("Final Answer: $\\boxed{4}$", "4"),
        ("So 2x = 8, therefore x = 4.", "x = 4"),
        ("First x = 3 is wrong. Final answer: x = -4", "x = -4"),
        ("Final answer: no solution", NO_SOLUTION),
        ("The equation has no solution.", NO_SOLUTION),
        ("Final answer: all x", ALL_X),
        ("Every value works, so there are infinitely many solutions.", ALL_X),
        ("I am not sure.", None),
    ],
)
def test_extract_final_answer(reply: str, expected: str | None) -> None:
    assert extract_final_answer(reply) == expected


def test_extract_then_check_end_to_end() -> None:
    reply = "Move terms: 4 = x.\nFinal answer: 4 = x"
    assert check_answer(extract_final_answer(reply), "4")


def test_contains_latex() -> None:
    assert contains_latex("so \\(x = 4\\)")
    assert contains_latex("x = \\frac{8}{2}")
    assert contains_latex("$x = 4$")
    assert not contains_latex("Final answer: x = 4")


def test_is_refusal() -> None:
    assert is_refusal("Sorry, I can only help with linear equations.")
    assert is_refusal("I cannot help with that.")
    assert not is_refusal("Final answer: x = 4")


def test_question_file_expected_solutions_match_sympy() -> None:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    for q in questions:
        if q["should_refuse"]:
            assert q["expected_solution"] is None
            continue
        assert check_answer(q["equation"], q["expected_solution"]), q["id"]
