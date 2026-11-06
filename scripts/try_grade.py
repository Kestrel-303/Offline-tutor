"""Grade one student answer with the answer grader (no model).

Usage: python scripts/try_grade.py --variable x --answer=45/2 "x = 22.5"
       python scripts/try_grade.py --outcome no_solution "no solution"
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from offline_tutor.grader import Expected, check_answer, to_rational  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variable", default=None)
    parser.add_argument("--answer", default=None, help="exact fraction, e.g. -3/2")
    parser.add_argument(
        "--outcome", default="unique", choices=["unique", "no_solution", "identity"]
    )
    parser.add_argument("text")
    args = parser.parse_args()
    if args.outcome == "unique" and args.answer is None:
        parser.error("--answer is required when --outcome is unique")
    answer = None if args.answer is None else to_rational(args.answer)
    result = check_answer(args.text, Expected(args.variable, args.outcome, answer))
    print(f"verdict: {result.verdict}")
    print(f"code: {result.code}")
    print(f"value_matches: {result.value_matches}")


if __name__ == "__main__":
    main()
