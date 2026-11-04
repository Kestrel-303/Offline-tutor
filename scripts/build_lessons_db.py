"""Build data/lessons.db from data/extracted/pages.jsonl. Prints counts only.

Deletes and recreates the database on each run. Never prints page text.
"""

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from offline_tutor.chunk import Chunk, chunk_pages, find_section_pages
from offline_tutor.lesson_db import create_db, insert_chunks
from offline_tutor.normalize import normalize_page

ROOT = Path(__file__).resolve().parent.parent
PAGES_PATH = ROOT / "data" / "extracted" / "pages.jsonl"
DB_PATH = ROOT / "data" / "lessons.db"

# Lesson range: page where FIRST_SECTION starts through the page before
# STOP_SECTION starts. EXPECTED_RANGE is a sanity check (1-based PDF pages).
FIRST_SECTION = "3.1"
STOP_SECTION = "3.3"
EXPECTED_RANGE = (117, 133)
MAX_RANGE_DRIFT = 1


def load_lesson_pages() -> list[tuple[int, str]]:
    """Return normalized (page, text) pairs for the detected lesson range."""
    with PAGES_PATH.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    pages = [(int(r["page"]), normalize_page(r["text"])) for r in rows]
    starts = find_section_pages(pages)
    if FIRST_SECTION not in starts or STOP_SECTION not in starts:
        sys.exit(f"Section {FIRST_SECTION} or {STOP_SECTION} heading not found.")
    first, last = starts[FIRST_SECTION], starts[STOP_SECTION] - 1
    if (
        abs(first - EXPECTED_RANGE[0]) > MAX_RANGE_DRIFT
        or abs(last - EXPECTED_RANGE[1]) > MAX_RANGE_DRIFT
    ):
        sys.exit(f"Detected range {first}-{last} differs from {EXPECTED_RANGE}.")
    return [(p, t) for p, t in pages if first <= p <= last]


def print_counts(pages: list[tuple[int, str]], chunks: list[Chunk]) -> None:
    lengths = [len(c.text) for c in chunks]
    print(f"Pages used: {len(pages)} ({pages[0][0]}-{pages[-1][0]})")
    print(f"Chunks: {len(chunks)}")
    for section, n in sorted(Counter(c.section for c in chunks).items()):
        print(f"  section {section or '(none)'}: {n}")
    for kind, n in sorted(Counter(c.kind for c in chunks).items()):
        print(f"  kind {kind}: {n}")
    print(
        f"Length min / median / max: {min(lengths)} / "
        f"{statistics.median(lengths):g} / {max(lengths)}"
    )
    print(f"Empty heading: {sum(1 for c in chunks if not c.heading)}")


def main() -> None:
    pages = load_lesson_pages()
    chunks = chunk_pages(pages)
    DB_PATH.unlink(missing_ok=True)
    conn = create_db(DB_PATH)
    insert_chunks(conn, chunks)
    conn.close()
    print(f"Wrote {DB_PATH}")
    print_counts(pages, chunks)


if __name__ == "__main__":
    main()
