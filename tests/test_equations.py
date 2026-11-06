"""Tests for the equation engine. Cases are shared with a future Kotlin port."""

import json
import string
from pathlib import Path
from typing import Any

import pytest
import sympy as sp

from offline_tutor import equations
from offline_tutor.equations import (
    EquationError,
    InvalidInputError,
    NoEquationError,
    UnsupportedEquationError,
    VerificationError,
    classify,
    extract_equations,
    sanitize,
    solve_linear,
)

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "tests" / "equation_cases.json").read_text("utf-8"))

# Non-ASCII test characters, built with chr() so the source stays ASCII-only.
MINUS = chr(0x2212)
TIMES = chr(0x00D7)
DIVIDE = chr(0x00F7)
FRACTION_SLASH = chr(0x2044)
E_ACUTE = chr(0x00E9)

# Expected results for dev questions that contain "=". Every other dev
# question must classify as no_equation.
DEV_EXPECTED = {
    "d01": ("linear_one_var", "5"),
    "d05": ("linear_one_var", "8"),
    "d07": ("linear_one_var", "9"),
    "b01": ("linear_one_var", "70"),
    "b02": ("linear_one_var", "5"),
    "b03": ("linear_one_var", "45/2"),
    "b04": ("linear_one_var", "-3/2"),
    "d16": ("system", None),
    "d25": ("nonlinear", None),
}


def test_case_file_size() -> None:
    assert len(CASES) >= 40
    assert len({c["id"] for c in CASES}) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case(case: dict[str, Any]) -> None:
    assert classify(case["input"]) == case["classification"]
    if case["classification"] != "linear_one_var":
        with pytest.raises(EquationError):
            solve_linear(case["input"])
        return
    sol = solve_linear(case["input"])
    assert sol.variable == case["variable"]
    assert sol.outcome == case["outcome"]
    expected = None if case["answer"] is None else sp.Rational(case["answer"])
    assert sol.answer == expected


def test_dev_questions() -> None:
    path = ROOT / "eval" / "dev_questions.json"
    questions = json.loads(path.read_text("utf-8"))
    for q in questions:
        kind, answer = DEV_EXPECTED.get(q["id"], ("no_equation", None))
        assert classify(q["question"]) == kind, q["id"]
        if answer is not None:
            assert solve_linear(q["question"]).answer == sp.Rational(answer), q["id"]
    with_equals = {q["id"] for q in questions if "=" in q["question"]}
    assert with_equals == set(DEV_EXPECTED)


# --- Sanitizing ---------------------------------------------------------------


def test_sanitize_maps_unicode_and_strips_end() -> None:
    assert sanitize(f"3x {MINUS} 5 = 10?") == "3x - 5 = 10"
    assert sanitize(f"2{TIMES}x = 8.") == "2*x = 8"
    assert sanitize(f"x {DIVIDE} 2 = 3") == "x / 2 = 3"
    assert sanitize(f"x{FRACTION_SLASH}2 = 3") == "x/2 = 3"


@pytest.mark.parametrize(
    "text",
    [
        "x = open('a')",
        "x__y = 1",
        "x = 1; y = 2",
        "x = 1 # c",
        "x" + " + 1" * 40 + " = 3",
        f"x = {E_ACUTE}",
        "x = [1]",
    ],
)
def test_sanitize_rejects(text: str) -> None:
    with pytest.raises(InvalidInputError):
        sanitize(text)


def test_power_is_nonlinear_without_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("parse_expr must not be called")

    monkeypatch.setattr(equations, "parse_expr", boom)
    assert classify("9**9**9 = x") == "nonlinear"
    assert classify("x^2 = 4") == "nonlinear"


def test_only_safe_strings_reach_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    real = equations.parse_expr

    def spy(s: str, *args: Any, **kwargs: Any) -> Any:
        seen.append(s)
        return real(s, *args, **kwargs)

    monkeypatch.setattr(equations, "parse_expr", spy)
    for case in CASES:
        classify(case["input"])
    allowed = set(string.digits + string.ascii_letters + "+-*/(). ")
    assert seen
    assert all(set(s) <= allowed for s in seen)
    assert not any("__" in s or "open" in s for s in seen)


# --- Extraction ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("what is the solution for 3x - 10 = 200?", ["3x - 10 = 200"]),
        ("2a + 3 =4a - 7 find a", ["2a + 3 =4a - 7"]),
        ("4/5 x +5=23", ["4/5 x +5=23"]),
        ("solve 4h + 6 = 0", ["4h + 6 = 0"]),
        ("Solve x/3 + 2 = 5", ["x/3 + 2 = 5"]),
        ("how to find x when 2x - 7 = 9", ["2x - 7 = 9"]),
        ("Solve x + y = 5 and x - y = 1 by addition.", ["x + y = 5", "x - y = 1"]),
        ("x + y = 5, x - y = 1", ["x + y = 5", "x - y = 1"]),
        ("What is a linear equation?", []),
    ],
)
def test_extract(text: str, expected: list[str]) -> None:
    assert extract_equations(text) == expected


def test_interpreted_shows_fraction_reading() -> None:
    assert solve_linear("4/5 x +5=23").interpreted == "(4/5)*x + 5 = 23"
    assert solve_linear("4/5x+5=23").interpreted == "(4/5)*x + 5 = 23"
    assert solve_linear("2(x+3)=14").interpreted == "2*(x + 3) = 14"


# --- Steps --------------------------------------------------------------------

LINEAR_INPUTS = [c["input"] for c in CASES if c["classification"] == "linear_one_var"]


@pytest.mark.parametrize("text", LINEAR_INPUTS)
def test_step_wording(text: str) -> None:
    steps = solve_linear(text).steps
    assert steps
    for step in steps:
        assert step.strip()
        assert "\\" not in step and "$" not in step
        assert step.isascii()
    assert steps[-1].startswith("Check:")


def test_step_order_and_wording() -> None:
    steps = solve_linear("4/5 x +5=23").steps
    assert steps[0].startswith("Multiply both sides by 5")
    assert "Divide both sides by 4" in steps[2]
    assert "45/2" in steps[3] and "22.5" in steps[3]
    assert solve_linear("2(x+3)=14").steps[0].startswith("Expand the brackets")
    assert "no solution" in " ".join(solve_linear("2x+3=2x+5").steps)
    assert "identity" in " ".join(solve_linear("3x+3=3(x+1)").steps)
    assert "about 0.3333" in " ".join(solve_linear("3x = 1").steps)


# --- Errors and verification -------------------------------------------------


def test_error_types() -> None:
    with pytest.raises(NoEquationError):
        solve_linear("What is a linear equation?")
    with pytest.raises(InvalidInputError):
        solve_linear("x/0 = 1")
    with pytest.raises(UnsupportedEquationError) as info:
        solve_linear("Solve x + y = 5 and x - y = 1")
    assert info.value.kind == "system"


def test_wrong_solver_answer_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(equations, "_solver", lambda expr, var: [sp.Integer(6)])
    with pytest.raises(VerificationError):
        solve_linear("3x + 5 = 20")


def test_solver_answer_for_no_solution_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(equations, "_solver", lambda expr, var: [sp.Integer(1)])
    with pytest.raises(VerificationError):
        solve_linear("2x+3=2x+5")
