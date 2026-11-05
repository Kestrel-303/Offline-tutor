"""Search data/lessons.db and print result metadata (no chunk text).

Usage: python scripts/search_lessons.py "query"
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_lessons_db import DB_PATH  # noqa: E402

from offline_tutor.lesson_db import search  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit('Usage: python scripts/search_lessons.py "query"')
    if not DB_PATH.exists():
        sys.exit(f"{DB_PATH} not found; run scripts/build_lessons_db.py first.")
    conn = sqlite3.connect(DB_PATH)
    results = search(conn, sys.argv[1])
    if not results:
        print("No results.")
    for rank, r in enumerate(results, start=1):
        print(
            f"{rank}. relevance={r.relevance:.3f} kind={r.kind}"
            f" section={r.section} heading={r.heading!r}"
            f" pages={r.page_start}-{r.page_end} id={r.chunk_id} len={len(r.text)}"
        )
    conn.close()


if __name__ == "__main__":
    main()
