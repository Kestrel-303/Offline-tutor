"""Compare local Ollama models on linear-equation questions.

Dev tool only (not part of the app, which must stay offline). Uses the Python
standard library plus SymPy, and talks to a local Ollama server.

Correctness is checked with SymPy only, never by a language model.

Usage:
    python scripts/compare_models.py
    python scripts/compare_models.py --models qwen2.5:1.5b gemma3:1b --runs 1
"""

import argparse
import csv
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import sympy
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

OLLAMA_URL = "http://localhost:11434/api/chat"
TIMEOUT_SECONDS = 300
DEFAULT_MODELS = ["qwen2.5:1.5b", "llama3.2:1b", "gemma3:1b"]
DEFAULT_RUNS = 3
TEMPERATURE = 0.2
SEED = None  # Left unset so the 3 runs show real variation.

SYSTEM_PROMPT = (
    "You are a patient math tutor for high school students. You only help with "
    "linear equations in one variable x. Explain the steps briefly in plain "
    "text. Do not use LaTeX. End with one line in exactly this form:\n"
    "Final answer: x = <number>\n"
    "If the equation has no solution, end with: Final answer: no solution\n"
    "If every x is a solution, end with: Final answer: all x\n"
    "If the question is not about linear equations, reply only with: "
    "Sorry, I can only help with linear equations."
)

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = ROOT / "tests" / "data" / "questions.json"
RESULTS_DIR = ROOT / "results"

FIELDS = [
    "model",
    "question_id",
    "run",
    "reply",
    "total_seconds",
    "eval_tokens_per_sec",
    "final_answer_extracted",
    "answer_correct",
    "contains_latex",
    "refused",
]

X = sympy.Symbol("x")
NO_SOLUTION = "no solution"
ALL_X = "all x"

_TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)
# Unicode math signs mapped to ASCII. Written as escapes to keep the source ASCII.
_UNICODE_SIGNS = {
    "\u2212": "-",  # minus sign
    "\u2013": "-",  # en dash
    "\u00d7": "*",  # multiplication sign
    "\u22c5": "*",  # dot operator
    "\u00b7": "*",  # middle dot
    "\u00f7": "/",  # division sign
    "\u2215": "/",  # division slash
}
# Only these characters may reach parse_expr (it uses eval internally).
_SAFE_MATH = re.compile(r"^[0-9x+\-*/^().=\s]+$")

_NO_SOLUTION_PATTERNS = re.compile(
    r"\bno (real )?solutions?\b|\bnot solvable\b", re.IGNORECASE
)
_ALL_X_PATTERNS = re.compile(
    r"\ball x\b|\ball real numbers\b|\binfinitely many\b|\bevery (real )?"
    r"(number|x|value)\b|\bany (real )?(number|x|value)\b",
    re.IGNORECASE,
)
_FINAL_ANSWER = re.compile(r"final answer\s*[:\-]?\s*(.+)", re.IGNORECASE)
_X_EQUALS = re.compile(r"\bx\s*=\s*(-?[0-9][0-9./\s()+\-*]*)")
_LATEX = re.compile(
    r"\\\(|\\\)|\\\[|\\\]|\$[^$\n]+\$|\\(frac|boxed|cdot|times|text|div|left|right)\b"
)
_REFUSAL = re.compile(
    r"\b(can only help with|cannot help|can't help|can not help|"
    r"only help with linear equations|not able to help|unable to help)\b",
    re.IGNORECASE,
)


class OllamaNotRunningError(Exception):
    pass


# --- Answer extraction and checking (pure functions, unit tested) ----------


def clean_answer(text: str) -> str:
    """Strip markdown/LaTeX decoration and trailing punctuation."""
    text = re.sub(r"\\boxed\{([^{}]*)\}", r"\1", text)
    text = text.replace("**", "").replace("$", "").replace("`", "")
    text = text.replace("\\(", "").replace("\\)", "")
    for sign, ascii_sign in _UNICODE_SIGNS.items():
        text = text.replace(sign, ascii_sign)
    return text.strip().rstrip(".!").strip()


def extract_final_answer(reply: str) -> str | None:
    """Return the model's final answer as a string, or None if none found.

    Prefers the last "Final answer:" line; falls back to the last "x = ..."
    in the reply. No-solution / all-x wording is normalised.
    """
    matches = _FINAL_ANSWER.findall(reply)
    if matches:
        candidate = clean_answer(matches[-1])
    else:
        x_matches = _X_EQUALS.findall(clean_answer(reply))
        if not x_matches:
            if _NO_SOLUTION_PATTERNS.search(reply):
                return NO_SOLUTION
            if _ALL_X_PATTERNS.search(reply):
                return ALL_X
            return None
        candidate = "x = " + x_matches[-1].strip()

    if _NO_SOLUTION_PATTERNS.search(candidate):
        return NO_SOLUTION
    if _ALL_X_PATTERNS.search(candidate):
        return ALL_X
    return candidate or None


def _parse(text: str) -> sympy.Expr | None:
    if not _SAFE_MATH.match(text):
        return None
    try:
        expr = parse_expr(text, local_dict={"x": X}, transformations=_TRANSFORMATIONS)
    except (SyntaxError, TypeError, ValueError, sympy.SympifyError):
        return None
    return expr if isinstance(expr, sympy.Expr) else None


def solution_set(answer: str) -> sympy.Expr | str | None:
    """Turn an answer string into a single value, NO_SOLUTION, ALL_X or None.

    Accepts "x = 4", "4 = x", "8/2", "4.0", and also any linear equation in x.
    """
    answer = clean_answer(answer)
    lowered = answer.lower()
    if lowered == NO_SOLUTION or _NO_SOLUTION_PATTERNS.search(lowered):
        return NO_SOLUTION
    if lowered == ALL_X or _ALL_X_PATTERNS.search(lowered):
        return ALL_X

    if answer.count("=") > 1:
        return None
    if "=" not in answer:
        value = _parse(answer)
        if value is None or value.free_symbols:
            return None
        return value

    left, right = (_parse(side) for side in answer.split("="))
    if left is None or right is None:
        return None
    solutions = sympy.solveset(sympy.Eq(left, right), X, domain=sympy.S.Reals)
    if solutions == sympy.S.EmptySet:
        return NO_SOLUTION
    if solutions == sympy.S.Reals:
        return ALL_X
    if isinstance(solutions, sympy.FiniteSet) and len(solutions) == 1:
        (value,) = solutions.args
        return value if isinstance(value, sympy.Expr) else None
    return None


def check_answer(answer: str | None, expected: str) -> bool:
    """True if answer is mathematically equal to expected (checked by SymPy)."""
    if answer is None:
        return False
    got = solution_set(answer)
    want = solution_set(expected)
    if got is None or want is None:
        return False
    if isinstance(got, str) or isinstance(want, str):
        return got == want
    return abs(float(sympy.N(got - want))) < 1e-9


def contains_latex(reply: str) -> bool:
    return bool(_LATEX.search(reply))


def is_refusal(reply: str) -> bool:
    return bool(_REFUSAL.search(reply))


# --- Ollama -----------------------------------------------------------------


def load_questions(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["questions"]


def chat(model: str, prompt: str) -> tuple[dict[str, Any], float]:
    """Send one chat request. Returns (response JSON, wall-clock seconds)."""
    options: dict[str, Any] = {"temperature": TEMPERATURE}
    if SEED is not None:
        options["seed"] = SEED
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": options,
        }
    )
    request = urllib.request.Request(
        OLLAMA_URL,
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError as exc:
        raise OllamaNotRunningError(str(exc.reason)) from exc
    except ConnectionError as exc:
        raise OllamaNotRunningError(str(exc)) from exc
    return result, time.perf_counter() - start


def build_row(
    model: str, question: dict[str, Any], run: int, result: dict[str, Any], secs: float
) -> dict[str, Any]:
    reply = result.get("message", {}).get("content", "").strip()
    eval_count = result.get("eval_count")
    eval_duration = result.get("eval_duration")
    tok_per_sec = None
    if isinstance(eval_count, int) and isinstance(eval_duration, int) and eval_duration:
        tok_per_sec = round(eval_count / (eval_duration / 1e9), 2)

    refused = is_refusal(reply)
    extracted = None if refused else extract_final_answer(reply)
    expected = question.get("expected_solution")
    correct = None
    if not question["should_refuse"] and expected is not None:
        correct = check_answer(extracted, expected)
    return {
        "model": model,
        "question_id": question["id"],
        "run": run,
        "reply": reply,
        "total_seconds": round(secs, 3),
        "eval_tokens_per_sec": tok_per_sec,
        "final_answer_extracted": extracted,
        "answer_correct": correct,
        "contains_latex": contains_latex(reply),
        "refused": refused,
    }


def summarize(
    rows: list[dict[str, Any]], questions: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    summary = []
    for model in dict.fromkeys(r["model"] for r in rows):
        mrows = [r for r in rows if r["model"] == model]
        graded = [r for r in mrows if r["answer_correct"] is not None]
        secs = [r["total_seconds"] for r in mrows]
        refusal_ok = [
            r["refused"] == questions[r["question_id"]]["should_refuse"] for r in mrows
        ]
        summary.append(
            {
                "model": model,
                "correct_pct": (
                    100 * sum(r["answer_correct"] for r in graded) / len(graded)
                    if graded
                    else 0.0
                ),
                "median_s": statistics.median(secs),
                "max_s": max(secs),
                "latex_pct": 100 * sum(r["contains_latex"] for r in mrows) / len(mrows),
                "refusal_acc_pct": 100 * sum(refusal_ok) / len(refusal_ok),
            }
        )
    return summary


def print_summary(summary: list[dict[str, Any]]) -> None:
    header = f"{'model':<16}{'correct%':>10}{'median s':>10}{'max s':>9}"
    header += f"{'LaTeX%':>9}{'refusal acc%':>14}"
    print(header)
    print("-" * len(header))
    for s in summary:
        print(
            f"{s['model']:<16}{s['correct_pct']:>10.1f}{s['median_s']:>10.2f}"
            f"{s['max_s']:>9.2f}{s['latex_pct']:>9.1f}{s['refusal_acc_pct']:>14.1f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare local Ollama models on linear-equation questions."
    )
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    args = parser.parse_args()

    questions = load_questions(QUESTIONS_PATH)
    by_id = {q["id"]: q for q in questions}
    rows: list[dict[str, Any]] = []

    try:
        for model in args.models:
            print(f"[{model}] warming up ...", flush=True)
            try:
                chat(model, "Solve for x: x + 1 = 2")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                print(
                    f"ERROR: HTTP {exc.code} for '{model}': {detail}", file=sys.stderr
                )
                continue
            for q in questions:
                for run in range(1, args.runs + 1):
                    try:
                        result, secs = chat(model, q["prompt"])
                    except (urllib.error.HTTPError, TimeoutError) as exc:
                        print(
                            f"ERROR: {model} {q['id']} run {run}: {exc}",
                            file=sys.stderr,
                        )
                        continue
                    row = build_row(model, q, run, result, secs)
                    rows.append(row)
                    print(
                        f"  {q['id']} run {run}: {row['total_seconds']}s, "
                        f"answer={row['final_answer_extracted']!r}, "
                        f"correct={row['answer_correct']}, refused={row['refused']}",
                        flush=True,
                    )
    except OllamaNotRunningError as exc:
        print(
            f"ERROR: Could not reach Ollama at {OLLAMA_URL} ({exc}). "
            "Start it with `ollama serve` or open the Ollama app.",
            file=sys.stderr,
        )
        return 1

    if not rows:
        print("No results.", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / f"compare_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    config_path = RESULTS_DIR / f"compare_{stamp}_config.json"
    config = {
        "models": args.models,
        "runs": args.runs,
        "temperature": TEMPERATURE,
        "seed": SEED,
        "system_prompt": SYSTEM_PROMPT,
        "questions_file": str(QUESTIONS_PATH.relative_to(ROOT)),
    }
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"\nWrote {len(rows)} rows to {csv_path}")
    print(f"Config (system prompt, temperature) in {config_path}\n")
    print_summary(summarize(rows, by_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
