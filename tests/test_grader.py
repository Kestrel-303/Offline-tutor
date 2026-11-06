"""Tests for the answer grader. Cases are shared with a future Kotlin port."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sympy as sp

from offline_tutor import grader
from offline_tutor.grader import Expected, check_answer, to_rational

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "tests" / "grader_cases.json").read_text("utf-8"))
EQUATION_CASES = json.loads((ROOT / "tests" / "equation_cases.json").read_text("utf-8"))


def _expected(e: dict[str, Any]) -> Expected:
    answer = None if e["answer"] is None else to_rational(e["answer"])
    return Expected(e["variable"], e["outcome"], answer)


def test_case_file_size() -> None:
    assert len(CASES) >= 50
    assert len({c["id"] for c in CASES}) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case(case: dict[str, Any]) -> None:
    result = check_answer(case["input"], _expected(case["expected"]))
    assert result.verdict == case["verdict"]
    assert result.code == case["code"]
    assert result.value_matches == case["value_matches"]
    if result.verdict == "unparseable":
        assert result.parsed is None


# --- Sanitizing ---------------------------------------------------------------

UNSAFE = [
    "__import__('os').system('x')",
    "open('a')",
    "9**9**9",
    "x^2",
    "x = 4; y = 5",
    "4 # c",
    "x = [4]",
    "lambda: 4",
    "4" * 5000,
    "   ",
]


@pytest.mark.parametrize("text", UNSAFE)
def test_unsafe_never_reaches_parser(
    text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("parse_expr must not be called")

    monkeypatch.setattr(grader, "parse_expr", boom)
    result = check_answer(text, Expected("x", "unique", sp.Integer(4)))
    assert result.verdict == "unparseable"


def test_only_numbers_reach_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    real = grader.parse_expr

    def spy(s: str, *args: Any, **kwargs: Any) -> Any:
        seen.append(s)
        return real(s, *args, **kwargs)

    monkeypatch.setattr(grader, "parse_expr", spy)
    for case in CASES:
        check_answer(case["input"], _expected(case["expected"]))
    assert seen
    assert all(set(s) <= set("0123456789+-*/()") for s in seen)


def test_decimals_become_exact_fractions() -> None:
    result = check_answer("x = 0.1", Expected("x", "unique", to_rational("1/10")))
    assert result.verdict == "correct"
    assert result.parsed == "x = 1/10"


def test_never_raises_on_odd_input() -> None:
    expected = Expected("x", "unique", sp.Integer(4))
    for text in ["(", ")", "4/", "/4", "()", "x =", "= 4", "=", "4/(2-2)", "-", "."]:
        assert check_answer(text, expected).verdict == "unparseable", text


# --- Property: the engine's own answers grade as correct ---------------------

UNIQUE = [c for c in EQUATION_CASES if c.get("outcome") == "unique"]


def _exact_decimal(q: sp.Rational) -> str | None:
    d = int(q.q)
    for p in (2, 5):
        while d % p == 0:
            d //= p
    if d != 1 or q.q == 1:
        return None
    return f"{(Decimal(int(q.p)) / Decimal(int(q.q))).normalize():f}"


@pytest.mark.parametrize("case", UNIQUE, ids=[c["id"] for c in UNIQUE])
def test_engine_answers_grade_correct(case: dict[str, Any]) -> None:
    answer = to_rational(case["answer"])
    expected = Expected(case["variable"], "unique", answer)
    forms = [str(answer), f"{case['variable']} = {answer}"]
    decimal = _exact_decimal(answer)
    if decimal is not None:
        forms.append(decimal)
    for form in forms:
        assert check_answer(form, expected).verdict == "correct", form
    wrong = str(answer + 1)
    if len(wrong) <= grader.MAX_ANSWER_LEN:  # e39's answer + 1 is 61 chars
        assert check_answer(wrong, expected).verdict == "incorrect"
