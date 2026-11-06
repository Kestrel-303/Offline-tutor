"""Answer grader: check a student's final answer against a verified answer.

No language model is involved. The expected answer comes from the equation
engine or a quiz template (both SymPy-verified); this module only compares.

Safety: student text is untrusted. It is length-capped, checked against a
strict allowlist ("__", "^" and "**" are refused outright), and the number
part is re-printed here with decimals rewritten as exact fractions
("1.5" -> "(15/10)") before it reaches parse_expr. Nothing here raises for
bad input: every problem becomes verdict "unparseable" with a code.

Comparison is exact. A decimal close to the answer but not equal to it
(0.33 for 1/3) is "incorrect" with code "rounded", never "correct".
"""

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

import sympy as sp
from sympy.parsing.sympy_parser import auto_number, auto_symbol, parse_expr

from offline_tutor.equations import _GLOBALS, _LOCALS, Outcome, normalize

Verdict = Literal["correct", "incorrect", "unparseable"]
Code = Literal[
    "ok",
    "wrong_value",
    "wrong_variable",
    "rounded",
    "wrong_outcome",
    "empty",
    "not_a_number",
    "mixed_number",
    "multiple_answers",
    "too_long",
    "unsafe",
]

MAX_ANSWER_LEN = 60
MAX_DIGITS = 40  # longer number literals are refused as "huge"
ROUNDING_TOLERANCE = sp.Rational(1, 100)

_PHRASES: dict[str, Outcome] = {
    "no solution": "no_solution",
    "no solutions": "no_solution",
    "none": "no_solution",
    "no real solution": "no_solution",
    "all x": "identity",
    "all real numbers": "identity",
    "infinitely many": "identity",
    "infinitely many solutions": "identity",
    "any number": "identity",
    "identity": "identity",
}
_ALLOWED = re.compile(r"[0-9A-Za-z+\-*/(). =]*")
_MULTIPLE = re.compile(r",|;|\b(?:or|and)\b", re.IGNORECASE)
_MIXED = re.compile(r"[+-]?\s*\d+\s+\d+\s*/\s*\d+")
_TOKEN = re.compile(r"\d+\.\d+|\d+|\.\d+|[A-Za-z]+|[+\-*/()]|\s+|.")
_NUMBER = re.compile(r"\d+\.\d+|\d+|\.\d+")
_TRANSFORMS = (auto_symbol, auto_number)


@dataclass(frozen=True)
class Expected:
    variable: str | None
    outcome: Outcome
    answer: sp.Rational | None


@dataclass(frozen=True)
class GradeResult:
    verdict: Verdict
    parsed: str | None
    code: Code
    value_matches: bool


def to_rational(text: str) -> sp.Rational:
    """Read a trusted fraction string such as "-3/2" (test data, CLI flags)."""
    value = sp.Rational(Fraction(text))
    if not isinstance(value, sp.Rational):
        raise ValueError(f"{text!r} is not a rational number")
    return value


class _Unparseable(Exception):
    def __init__(self, code: Code) -> None:
        super().__init__(code)
        self.code: Code = code


def _fraction_text(q: Fraction) -> str:
    return str(q.numerator) if q.denominator == 1 else f"{q.numerator}/{q.denominator}"


def _explicit_number(text: str) -> tuple[str, bool]:
    """Re-print a number expression for the parser.

    Returns (explicit_text, had_decimal). Letters, two numbers in a row and
    implied multiplication are refused.
    """
    if _MIXED.fullmatch(text.strip()):
        raise _Unparseable("mixed_number")
    out: list[str] = []
    prev = ""
    had_decimal = False
    for tok in _TOKEN.findall(text):
        if tok.isspace():
            continue
        if _NUMBER.fullmatch(tok):
            if len(tok.replace(".", "")) > MAX_DIGITS:
                raise _Unparseable("not_a_number")
            if prev in ("num", ")"):
                raise _Unparseable("not_a_number")
            if "." in tok:
                had_decimal = True
                out.append(f"({_fraction_text(Fraction(tok))})")
            else:
                out.append(tok)
            prev = "num"
        elif tok in "+-*/":
            out.append(tok)
            prev = "op"
        elif tok == "(":
            if prev in ("num", ")"):
                raise _Unparseable("not_a_number")
            out.append(tok)
            prev = "("
        elif tok == ")":
            out.append(tok)
            prev = ")"
        else:
            raise _Unparseable("not_a_number")
    if not out:
        raise _Unparseable("not_a_number")
    return "".join(out), had_decimal


def _parse_number(text: str) -> tuple[sp.Rational, bool]:
    explicit, had_decimal = _explicit_number(text)
    try:
        value = parse_expr(
            explicit,
            local_dict=dict(_LOCALS),
            global_dict=dict(_GLOBALS),
            transformations=_TRANSFORMS,
        )
    except Exception as exc:  # SymPy raises many types for malformed input.
        raise _Unparseable("not_a_number") from exc
    if not isinstance(value, sp.Rational):
        # Division by zero gives zoo or nan, which are not Rational.
        raise _Unparseable("not_a_number")
    return value, had_decimal


def _clean(text: str) -> str:
    s = " ".join(normalize(text).split())
    while s.endswith("."):
        s = s[:-1].rstrip()
    return s


def _split(s: str) -> tuple[str | None, str]:
    """Return (variable_letter_or_None, number_text)."""
    if s.count("=") > 1:
        raise _Unparseable("multiple_answers")
    if "=" not in s:
        return None, s
    left, right = (side.strip() for side in s.split("="))
    left_var = len(left) == 1 and left.isalpha()
    right_var = len(right) == 1 and right.isalpha()
    if left_var == right_var:
        # "x = y", "4 = 4", "2x = 8" or an empty side.
        raise _Unparseable("not_a_number")
    return (left, right) if left_var else (right, left)


def _grade(text: str, expected: Expected) -> GradeResult:
    if len(text) > MAX_ANSWER_LEN:
        raise _Unparseable("too_long")
    s = _clean(text)
    if not s:
        raise _Unparseable("empty")
    if "__" in s or "^" in s or "**" in s:
        raise _Unparseable("unsafe")

    phrase = _PHRASES.get(s.lower())
    if phrase is not None:
        if phrase == expected.outcome:
            return GradeResult("correct", phrase, "ok", True)
        return GradeResult("incorrect", phrase, "wrong_outcome", False)

    if _MULTIPLE.search(s):
        raise _Unparseable("multiple_answers")
    if not _ALLOWED.fullmatch(s):
        raise _Unparseable("unsafe")

    letter, number_text = _split(s)
    value, had_decimal = _parse_number(number_text)
    shown = _fraction_text(Fraction(int(value.p), int(value.q)))
    if letter is not None:
        shown = f"{letter} = {shown}"

    if expected.outcome != "unique" or expected.answer is None:
        return GradeResult("incorrect", shown, "wrong_outcome", False)
    matches = bool(value == expected.answer)
    if (
        letter is not None
        and expected.variable is not None
        and letter.lower() != expected.variable.lower()
    ):
        return GradeResult("incorrect", shown, "wrong_variable", matches)
    if matches:
        return GradeResult("correct", shown, "ok", True)
    if had_decimal and abs(value - expected.answer) <= ROUNDING_TOLERANCE:
        return GradeResult("incorrect", shown, "rounded", False)
    return GradeResult("incorrect", shown, "wrong_value", False)


def check_answer(student_text: str, expected: Expected) -> GradeResult:
    """Grade one answer. Never raises for bad student input."""
    try:
        return _grade(student_text, expected)
    except _Unparseable as exc:
        return GradeResult("unparseable", None, exc.code, False)
