"""Terminal tutor (no model yet): type a question, get a reply.

Usage: python scripts/tutor_terminal.py [--db data/lessons.db]
An empty line, "quit" or "exit" ends the session.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from offline_tutor.router import build_lexicon  # noqa: E402
from offline_tutor.tutor import answer  # noqa: E402

DEFAULT_DB = ROOT / "data" / "lessons.db"
EXIT_WORDS = frozenset({"quit", "exit"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    db_path: Path = args.db
    if not db_path.exists():
        sys.exit(f"{db_path} not found; run scripts/build_lessons_db.py first.")
    lexicon = build_lexicon(db_path)
    print('Ask a question about linear equations. Type "quit" to stop.')
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line or line.lower() in EXIT_WORDS:
            break
        print(answer(line, lexicon, db_path).text)
        print()


if __name__ == "__main__":
    main()
