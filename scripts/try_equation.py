"""Classify and solve one question with the equation engine (no model).

Usage: python scripts/try_equation.py "question text"
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from offline_tutor.equations import EquationError, classify, solve_linear  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit('Usage: python scripts/try_equation.py "question text"')
    text = sys.argv[1]
    kind = classify(text)
    print(f"classification: {kind}")
    if kind != "linear_one_var":
        return
    try:
        sol = solve_linear(text)
    except EquationError as exc:
        print(f"error: {type(exc).__name__}: {exc}")
        return
    print(f"interpreted: {sol.interpreted}")
    print("steps:")
    for i, step in enumerate(sol.steps, start=1):
        print(f"  {i}. {step}")
    print(f"outcome: {sol.outcome}")
    print(f"answer: {sol.answer}")


if __name__ == "__main__":
    main()
