"""solve_linear refuses function calls instead of dropping the function name."""

import pytest
import sympy as sp

from offline_tutor.equations import (
    MAX_QUESTION_LEN,
    InvalidInputError,
    NoEquationError,
    UnsupportedEquationError,
    solve_linear,
)


@pytest.mark.parametrize(
    "text",
    ["sqrt(2)*x = 4", "sin(x) = 0.5", "log(x) = 1", "abs(x) = 2", "exp(x) = 3"],
)
def test_function_call_raises(text: str) -> None:
    with pytest.raises(UnsupportedEquationError) as info:
        solve_linear(text)
    assert info.value.kind == "nonlinear"


@pytest.mark.parametrize(
    ("text", "answer"),
    [("2x + 3 = 7", 2), ("2(x + 1) = 6", 2)],
)
def test_linear_still_solved(text: str, answer: int) -> None:
    solution = solve_linear(text)
    assert solution.outcome == "unique"
    assert solution.variable == "x"
    assert solution.answer == sp.Rational(answer)


@pytest.mark.parametrize(
    ("text", "outcome"),
    [("x + 1 = x + 2", "no_solution"), ("x + 1 = x + 1", "identity")],
)
def test_special_outcomes_unchanged(text: str, outcome: str) -> None:
    solution = solve_linear(text)
    assert solution.outcome == outcome
    assert solution.answer is None


@pytest.mark.parametrize("text", ["sqrt 2 x = 4", "sin x = 0.5", "ln x = 1"])
def test_function_name_without_bracket_raises(text: str) -> None:
    with pytest.raises(UnsupportedEquationError) as info:
        solve_linear(text)
    assert info.value.kind == "nonlinear"


def test_function_call_without_equation_is_no_equation() -> None:
    with pytest.raises(NoEquationError):
        solve_linear("what is sqrt(2)?")


@pytest.mark.parametrize(
    ("text", "answer"),
    [("help me solve 2x + 3 = 7 please", 2), ("Solve for x in 3x - 5 = 10", 5)],
)
def test_linear_in_sentence_still_solved(text: str, answer: int) -> None:
    solution = solve_linear(text)
    assert solution.outcome == "unique"
    assert solution.variable == "x"
    assert solution.answer == sp.Rational(answer)


def test_over_long_function_call_is_invalid() -> None:
    text = "sqrt(2)*x = 4 " + "and more words " * 40
    assert len(text) > MAX_QUESTION_LEN
    with pytest.raises(InvalidInputError):
        solve_linear(text)
