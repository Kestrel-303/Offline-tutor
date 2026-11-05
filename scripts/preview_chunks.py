"""Write every chunk in data/lessons.db to data/extracted/chunk_preview.txt
for manual review. Reads the built database, so chunk ids match it; run
scripts/build_lessons_db.py first.

Prints only the file path and counts, never chunk text.
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from build_lessons_db import DB_PATH  # noqa: E402

OUT_PATH = ROOT / "data" / "extracted" / "chunk_preview.txt"


def main() -> None:
    if not DB_PATH.exists():
        sys.exit(f"{DB_PATH} not found; run scripts/build_lessons_db.py first.")
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, section, heading, kind, page_start, page_end, char_count, text"
        " FROM chunks ORDER BY id"
    ).fetchall()
    conn.close()
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for cid, section, heading, kind, start, end, n, text in rows:
            f.write(
                f"===== chunk {cid} | section {section} | heading {heading!r}"
                f" | kind {kind} | pages {start}-{end} | {n} chars =====\n"
                f"{text}\n\n"
            )
    print(f"Wrote {OUT_PATH} from {DB_PATH}")
    print(f"Chunks: {len(rows)}")


if __name__ == "__main__":
    main()
