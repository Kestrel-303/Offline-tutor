"""Count equation lines that SymPy can parse, before and after layout extraction.

For PDF pages CHECK_RANGE, normalizes the text from pages.jsonl (old) and
pages_layout.jsonl (new), takes lines containing "=", and counts lines whose
every "="-separated side parses with implicit multiplication. Prints counts
only, never page text.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from sympy.parsing.sympy_parser import (  # noqa: E402
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from offline_tutor.normalize import normalize_page  # noqa: E402

EXTRACTED = ROOT / "data" / "extracted"
OLD_PATH = EXTRACTED / "pages.jsonl"
NEW_PATH = EXTRACTED / "pages_layout.jsonl"
CHECK_RANGE = (117, 133)

_TRANSFORMS = (*standard_transformations, implicit_multiplication_application)


def side_parses(side: str) -> bool:
    if not side.strip():
        return False
    try:
        parse_expr(side, transformations=_TRANSFORMS, evaluate=False)
    except Exception:  # SymPy raises many types for unparseable input.
        return False
    return True


def line_parses(line: str) -> bool:
    return all(side_parses(side) for side in line.split("="))


def count(path: Path) -> tuple[int, int]:
    """Return (equation lines, lines that parse) for CHECK_RANGE."""
    total = ok = 0
    with path.open(encoding="utf-8") as f:
        for raw in f:
            rec = json.loads(raw)
            if not CHECK_RANGE[0] <= int(rec["page"]) <= CHECK_RANGE[1]:
                continue
            for line in normalize_page(rec["text"]).splitlines():
                if "=" in line:
                    total += 1
                    ok += line_parses(line)
    return total, ok


def main() -> None:
    for label, path in (("before", OLD_PATH), ("after", NEW_PATH)):
        total, ok = count(path)
        print(f"{label}: {ok} of {total} lines with '=' parse")


if __name__ == "__main__":
    main()
