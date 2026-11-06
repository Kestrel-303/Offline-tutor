"""Equation engine: find, classify and solve linear equations with SymPy.

No language model is involved. Every answer comes from SymPy's solver and is
then verified by substituting it back into both sides with exact arithmetic.

Safety: student text is untrusted. Raw text is never passed to SymPy. Each
equation is first sanitized with a strict allowlist, then re-tokenized here
into an explicit string (only numbers, single letters, + - * / ( ) and =),
and only that string reaches parse_expr, with every single ASCII letter
mapped to a Symbol and an empty builtins table.

Reading of fractions: "4/5 x" and "4/5x" are both read as (4/5)*x, never as
4/(5*x). A number fraction directly followed by an implied multiplication is
wrapped in brackets (for example "(4/5)*x + 5 = 23") so the tutor can echo
the reading back to the student.

Display: `interpreted` and the steps show implicit multiplication the way a
textbook does ("(4/5)x + 5 = 23", "2(x + 3) = 14"). The explicit string with
"*" is kept internally and is the only thing that reaches the parser.
"""

import math
import re
import string
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any, Literal

import sympy as sp
from sympy.parsing.sympy_parser import (
    auto_number,
    auto_symbol,
    implicit_multiplication,
    parse_expr,
    rationalize,
)

Classification = Literal[
    "linear_one_var", "system", "linear_other", "nonlinear", "no_equation", "invalid"
]
Outcome = Literal["unique", "no_solution", "identity"]

MAX_EQUATION_LEN = 120
MAX_QUESTION_LEN = 500

# Unicode signs students paste from phones or PDFs, mapped to ASCII. Built
# with chr() so the source stays ASCII-only.
_UNICODE_MAP = str.maketrans(
    {
        chr(0x2212): "-",  # minus sign
        chr(0x2013): "-",  # en dash
        chr(0x00D7): "*",  # multiplication sign
        chr(0x00B7): "*",  # middle dot
        chr(0x00F7): "/",  # division sign
        chr(0x2044): "/",  # fraction slash
        chr(0x2215): "/",  # division slash
    }
)
_ALLOWED = re.compile(r"[0-9A-Za-z+\-*/().,=^ ]*")
_TOKEN = re.compile(r"\d+\.\d+|\d+|\.\d+|[A-Za-z]+|[+\-*/()=^]|\s+|.", re.DOTALL)
_NUMBER = re.compile(r"\d+\.\d+|\d+|\.\d+")

_LOCALS: dict[str, Any] = {c: sp.Symbol(c) for c in string.ascii_letters}
_GLOBALS: dict[str, Any] = {
    "__builtins__": {},
    "Integer": sp.Integer,
    "Rational": sp.Rational,
    "Float": sp.Float,
    "Symbol": sp.Symbol,
}
_TRANSFORMS = (auto_symbol, auto_number, rationalize, implicit_multiplication)


class EquationError(ValueError):
    """Base class for all equation engine errors."""


class InvalidInputError(EquationError):
    """Text is unsafe, malformed or cannot be parsed as an equation."""


class NoEquationError(EquationError):
    """The text contains no equation."""


class UnsupportedEquationError(EquationError):
    """The equation is valid but not a linear equation in one variable."""

    def __init__(self, kind: Classification) -> None:
        super().__init__(f"unsupported equation type: {kind}")
        self.kind: Classification = kind


class VerificationError(EquationError):
    """The solver's answer did not check out. Never shown as an answer."""


@dataclass(frozen=True)
class Solution:
    variable: str
    interpreted: str
    steps: tuple[str, ...]
    outcome: Outcome
    answer: sp.Rational | None


@dataclass(frozen=True)
class _Parsed:
    interpreted: str
    lhs: sp.Expr
    rhs: sp.Expr
    symbols: tuple[sp.Symbol, ...]
    has_brackets: bool
    decimals: tuple[str, ...]


def normalize(text: str) -> str:
    """Map unicode minus/times/divide/fraction-slash signs to ASCII."""
    return text.translate(_UNICODE_MAP)


def sanitize(text: str) -> str:
    """Return a safe equation string or raise InvalidInputError."""
    s = normalize(text).strip()
    while s and s[-1] in "?.":
        s = s[:-1].rstrip()
    if len(s) > MAX_EQUATION_LEN:
        raise InvalidInputError(f"equation is longer than {MAX_EQUATION_LEN} chars")
    if "__" in s:
        raise InvalidInputError("'__' is not allowed")
    if not _ALLOWED.fullmatch(s):
        raise InvalidInputError("equation contains characters that are not allowed")
    return s


def _is_math_token(tok: str) -> bool:
    if tok.isspace() or tok in "+-*/()=^":
        return True
    if _NUMBER.fullmatch(tok):
        return True
    return len(tok) == 1 and tok in string.ascii_letters


def extract_equations(text: str) -> list[str]:
    """Return every equation in a question, in order.

    Each equation is the maximal run of math tokens (numbers, single
    letters, operators, brackets) around an "=". A word of two or more
    letters, a comma or any other character ends the run.
    """
    runs: list[list[str]] = [[]]
    for tok in _TOKEN.findall(normalize(text)):
        if _is_math_token(tok):
            runs[-1].append(tok)
        else:
            runs.append([])
    return [s for s in ("".join(r).strip() for r in runs) if "=" in s]


def _explicit(equation: str) -> tuple[str, bool, tuple[str, ...]]:
    """Re-print an equation with explicit "*" and bracketed number fractions.

    Returns (interpreted, has_brackets, decimal_literals).
    """
    out: list[str] = []
    kinds: list[str] = []  # "num", "var", "op", "(", ")" per output token
    has_brackets = False
    decimals: list[str] = []
    for tok in _TOKEN.findall(equation):
        if tok.isspace():
            continue
        if _NUMBER.fullmatch(tok):
            kind = "num"
            if "." in tok:
                decimals.append(tok)
        elif tok.isalpha():
            if len(tok) != 1:
                raise InvalidInputError("words are not allowed inside an equation")
            kind = "var"
        elif tok in "+-*/=":
            kind = "op"
        elif tok in "()":
            kind = tok
            has_brackets = True
        else:
            raise InvalidInputError(f"unexpected character {tok!r}")
        prev = kinds[-1] if kinds else None
        if prev == "num" and kind == "num":
            raise InvalidInputError("two numbers in a row")
        if prev in ("num", "var", ")") and kind in ("num", "var", "("):
            # Implied multiplication. Bracket a leading number fraction so
            # "4/5x" reads as (4/5)*x.
            if (
                len(kinds) >= 3
                and kinds[-3:] == ["num", "op", "num"]
                and out[-2] == "/"
                and (len(kinds) == 3 or out[-4] in ("+", "-", "=", "("))
            ):
                out[-3:] = ["(", out[-3], "/", out[-1], ")"]
                kinds[-3:] = ["(", "num", "op", "num", ")"]
            out.append("*")
            kinds.append("op")
        out.append(tok)
        kinds.append(kind)

    text = ""
    for i, tok in enumerate(out):
        unary = tok == "-" and (i == 0 or out[i - 1] in ("+", "-", "*", "/", "=", "("))
        if tok == "=" or (tok in "+-" and not unary):
            text += f" {tok} "
        else:
            text += tok
    return text, has_brackets, tuple(decimals)


_IMPLICIT_STAR = re.compile(r"(?<=[0-9)])\*(?=[A-Za-z(])")


def display(explicit: str) -> str:
    """Drop "*" between a number or ")" and a letter or "(": "3*x" -> "3x"."""
    return _IMPLICIT_STAR.sub("", explicit)


def _parse_side(side: str) -> sp.Expr:
    if not side.strip():
        raise InvalidInputError("one side of the equation is empty")
    try:
        expr = parse_expr(
            side,
            local_dict=dict(_LOCALS),
            global_dict=dict(_GLOBALS),
            transformations=_TRANSFORMS,
        )
    except Exception as exc:  # SymPy raises many types for malformed input.
        raise InvalidInputError(f"could not read {side!r}") from exc
    if not isinstance(expr, sp.Expr):
        raise InvalidInputError(f"could not read {side!r}")
    if expr.has(sp.zoo, sp.oo, -sp.oo, sp.nan):
        raise InvalidInputError("division by zero")
    return expr


def _parse_equation(raw: str) -> _Parsed:
    interpreted, has_brackets, decimals = _explicit(sanitize(raw))
    sides = interpreted.split(" = ")
    if interpreted.count("=") != 1 or len(sides) != 2:
        raise InvalidInputError("an equation needs exactly one '='")
    lhs, rhs = _parse_side(sides[0]), _parse_side(sides[1])
    found = [s for s in lhs.free_symbols | rhs.free_symbols if isinstance(s, sp.Symbol)]
    symbols = tuple(sorted(found, key=lambda s: s.name))
    return _Parsed(interpreted, lhs, rhs, symbols, has_brackets, decimals)


def _is_nonlinear(p: _Parsed) -> bool:
    for side in (p.lhs, p.rhs):
        if sp.denom(sp.together(side)).free_symbols:
            return True
    diff = sp.expand(p.lhs - p.rhs)
    if not p.symbols:
        return False
    if not diff.is_polynomial(*p.symbols):
        return True
    return sp.Poly(diff, *p.symbols).total_degree() > 1


def _analyze(text: str) -> tuple[Classification, list[_Parsed]]:
    if "=" not in text:
        return "no_equation", []
    if len(text) > MAX_QUESTION_LEN or "__" in text:
        return "invalid", []
    if "^" in text or "**" in text:
        return "nonlinear", []
    equations = extract_equations(text)
    if not equations:
        return "invalid", []
    try:
        parsed = [_parse_equation(e) for e in equations]
    except InvalidInputError:
        return "invalid", []
    if any(_is_nonlinear(p) for p in parsed):
        return "nonlinear", parsed
    if len(parsed) >= 2:
        return "system", parsed
    if not parsed[0].symbols:
        return "invalid", parsed
    if len(parsed[0].symbols) == 1:
        return "linear_one_var", parsed
    return "linear_other", parsed


def classify(text: str) -> Classification:
    """Classify a question. Never raises; unsafe input gives "invalid"."""
    return _analyze(text)[0]


def _solver(expr: Any, var: sp.Symbol) -> list[Any]:
    """SymPy's solver, kept separate so tests can replace it."""
    return sp.solve(expr, var)


# --- Step wording -----------------------------------------------------------


def _to_fraction(r: Any) -> Fraction:
    if not isinstance(r, sp.Rational):
        raise VerificationError(f"{r!r} is not an exact rational number")
    return Fraction(int(r.p), int(r.q))


def _num(q: Fraction) -> str:
    return str(q.numerator) if q.denominator == 1 else f"{q.numerator}/{q.denominator}"


def _term(c: Fraction, v: str) -> str:
    """Format c*v for a positive or negative coefficient c."""
    if c == 1:
        return v
    if c == -1:
        return f"-{v}"
    if c.denominator == 1:
        return f"{c.numerator}{v}"
    sign = "-" if c < 0 else ""
    return f"{sign}({_num(abs(c))}){v}"


def _linear(a: Fraction, b: Fraction, v: str) -> str:
    """Format a*v + b."""
    if a == 0:
        return _num(b)
    text = _term(a, v)
    if b > 0:
        text += f" + {_num(b)}"
    elif b < 0:
        text += f" - {_num(-b)}"
    return text


def _decimal(q: Fraction) -> str:
    d = q.denominator
    for p in (2, 5):
        while d % p == 0:
            d //= p
    with localcontext() as ctx:
        ctx.prec = 50
        value = Decimal(q.numerator) / Decimal(q.denominator)
    if d == 1:
        return f"{value.normalize():f}"
    return f"about {float(q):.4f}"


def _coeffs(expr: sp.Expr, var: sp.Symbol) -> tuple[Fraction, Fraction]:
    e = sp.expand(expr)
    return _to_fraction(e.coeff(var, 1)), _to_fraction(e.coeff(var, 0))


def _build_steps(p: _Parsed, var: sp.Symbol, answer: Fraction | None) -> list[str]:
    v = var.name
    a1, b1 = _coeffs(p.lhs, var)
    a2, b2 = _coeffs(p.rhs, var)
    steps: list[str] = []

    def eq() -> str:
        return f"{_linear(a1, b1, v)} = {_linear(a2, b2, v)}"

    if p.has_brackets:
        steps.append(f"Expand the brackets: {eq()}.")
    if p.decimals:
        pairs = ", ".join(f"{d} = {_num(Fraction(d))}" for d in p.decimals)
        steps.append(f"Write the decimals as fractions: {pairs}.")
    den = math.lcm(*(c.denominator for c in (a1, b1, a2, b2)))
    if den > 1:
        a1, b1, a2, b2 = (c * den for c in (a1, b1, a2, b2))
        steps.append(f"Multiply both sides by {den} to clear the fractions: {eq()}.")

    if a1 == 1 and b1 == 0 and a2 == 0:
        steps.append(f"The equation already has {v} alone on the left side.")
    else:
        if a1 == 0 and a2 != 0:
            a1, b1, a2, b2 = a2, b2, a1, b1
            steps.append(f"Swap the two sides so the {v} term is on the left: {eq()}.")
        if a2 != 0:
            moved = _term(abs(a2), v)
            verb = f"Subtract {moved} from" if a2 > 0 else f"Add {moved} to"
            a1, a2 = a1 - a2, Fraction(0)
            steps.append(
                f"{verb} both sides to move the {v} terms to the left: {eq()}."
            )
        if a1 == 0:
            truth = "always" if b1 == b2 else "never"
            ending = (
                "Every number is a solution (the equation is an identity)."
                if b1 == b2
                else "So the equation has no solution."
            )
            steps.append(
                f"The {v} terms cancel, leaving {_num(b1)} = {_num(b2)}, which is "
                f"{truth} true. {ending}"
            )
            return steps
        if b1 != 0:
            verb = f"Subtract {_num(b1)} from" if b1 > 0 else f"Add {_num(-b1)} to"
            b1, b2 = Fraction(0), b2 - b1
            steps.append(
                f"{verb} both sides to move the constants to the right: {eq()}."
            )
        if a1 != 1:
            steps.append(f"Divide both sides by {_num(a1)}: {v} = {_num(b2 / a1)}.")

    assert answer is not None
    if answer.denominator == 1:
        steps.append(f"Answer: {v} = {_num(answer)}.")
    else:
        steps.append(
            f"Answer: {v} = {_num(answer)}, which is {_decimal(answer)} as a decimal."
        )
    return steps


def solve_linear(text: str) -> Solution:
    """Solve a linear equation in one variable found in `text`.

    Raises NoEquationError, InvalidInputError, UnsupportedEquationError
    (for systems, nonlinear and multi-variable equations) or
    VerificationError if the solver's answer fails the substitution check.
    """
    kind, parsed = _analyze(text)
    if kind == "no_equation":
        raise NoEquationError("no equation found")
    if kind == "invalid":
        raise InvalidInputError("the equation could not be read safely")
    if kind != "linear_one_var":
        raise UnsupportedEquationError(kind)
    p = parsed[0]
    var = p.symbols[0]
    v = var.name
    diff: Any = sp.expand(p.lhs - p.rhs)
    a = diff.coeff(var, 1)

    if a == 0:
        outcome: Outcome = "identity" if diff == 0 else "no_solution"
        if _solver(diff, var):
            raise VerificationError(f"solver found a solution for an {outcome}")
        steps = _build_steps(p, var, None)
        if outcome == "identity":
            steps.append(
                f"Check: both sides simplify to {display(sp.sstr(sp.expand(p.lhs)))}, "
                f"so they are equal for every value of {v}."
            )
        else:
            steps.append(
                f"Check: left side minus right side is always {sp.sstr(diff)}, never 0."
            )
        return Solution(v, display(p.interpreted), tuple(steps), outcome, None)

    roots = _solver(diff, var)
    if len(roots) != 1:
        raise VerificationError(f"expected one solution, solver gave {roots!r}")
    answer = roots[0]
    if not isinstance(answer, sp.Rational):
        raise VerificationError(f"solution {answer!r} is not rational")
    left = p.lhs.subs(var, answer)
    right = p.rhs.subs(var, answer)
    if not (left.is_Rational and right.is_Rational and left == right):
        raise VerificationError(
            f"{v} = {answer} does not satisfy {display(p.interpreted)}: "
            f"{left} != {right}"
        )
    frac = _to_fraction(answer)
    steps = _build_steps(p, var, frac)
    steps.append(
        f"Check: put {v} = {_num(frac)} into {display(p.interpreted)}. "
        f"Left side: {_num(_to_fraction(left))}. "
        f"Right side: {_num(_to_fraction(right))}. Both sides are equal."
    )
    return Solution(v, display(p.interpreted), tuple(steps), "unique", answer)
