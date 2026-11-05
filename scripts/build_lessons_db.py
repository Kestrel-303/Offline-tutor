"""Build data/lessons.db from data/extracted/pages_layout.jsonl.

Run scripts/extract_layout.py first to write the pages file. Deletes and
recreates the database on each run. Prints counts only, never page text.
Options pick another pages file (e.g. the plain data/extracted/pages.jsonl),
database path, and an optional chunk preview file.
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from offline_tutor.chunk import (  # noqa: E402
    Chunk,
    ChunkStats,
    chunk_pages_with_stats,
    find_section_pages,
)
from offline_tutor.lesson_db import create_db, insert_chunks  # noqa: E402
from offline_tutor.normalize import normalize_page  # noqa: E402

PAGES_PATH = ROOT / "data" / "extracted" / "pages_layout.jsonl"
DB_PATH = ROOT / "data" / "lessons.db"

# Lesson range: page where FIRST_SECTION starts through the page before
# STOP_SECTION starts. EXPECTED_RANGE is a sanity check (1-based PDF pages).
FIRST_SECTION = "3.1"
STOP_SECTION = "3.3"
EXPECTED_RANGE = (117, 133)
MAX_RANGE_DRIFT = 1


def load_lesson_pages(pages_path: Path = PAGES_PATH) -> list[tuple[int, str]]:
    """Return normalized (page, text) pairs for the detected lesson range."""
    if not pages_path.exists():
        sys.exit(
            f"{pages_path} not found; run scripts/extract_layout.py first to write it."
        )
    with pages_path.open(encoding="utf-8") as f:
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


def print_counts(
    pages: list[tuple[int, str]], chunks: list[Chunk], stats: ChunkStats
) -> None:
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
    print(f"Introduction blocks dropped: {stats.intro_blocks_dropped}")
    print(f"Label-only chunks dropped: {stats.label_only_dropped}")
    print(f"Multi-example chunks split: {stats.example_splits}")


def write_preview(path: Path, chunks: list[Chunk]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i, c in enumerate(chunks, start=1):
            f.write(
                f"===== chunk {i} | section {c.section} | heading {c.heading!r}"
                f" | kind {c.kind} | pages {c.page_start}-{c.page_end}"
                f" | {len(c.text)} chars =====\n{c.text}\n\n"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the lessons database.")
    parser.add_argument("--pages-file", type=Path, default=PAGES_PATH)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--preview", type=Path, default=None)
    args = parser.parse_args()

    pages = load_lesson_pages(args.pages_file)
    chunks, stats = chunk_pages_with_stats(pages)
    args.db.unlink(missing_ok=True)
    conn = create_db(args.db)
    insert_chunks(conn, chunks)
    conn.close()
    print(f"Wrote {args.db}")
    if args.preview is not None:
        write_preview(args.preview, chunks)
        print(f"Wrote {args.preview}")
    print_counts(pages, chunks, stats)


if __name__ == "__main__":
    main()
