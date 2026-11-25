"""solve_linear refuses function calls instead of dropping the function name."""

import pytest
import sympy as sp

from offline_tutor.equations import UnsupportedEquationError, solve_linear


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
