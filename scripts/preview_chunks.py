"""Write all chunks to data/extracted/chunk_preview.txt for manual review.

Prints only the file path and counts, never chunk text.
"""

from build_lessons_db import ROOT, load_lesson_pages

from offline_tutor.chunk import chunk_pages

OUT_PATH = ROOT / "data" / "extracted" / "chunk_preview.txt"


def main() -> None:
    chunks = chunk_pages(load_lesson_pages())
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for i, c in enumerate(chunks, start=1):
            f.write(
                f"===== chunk {i} | section {c.section} | heading {c.heading!r}"
                f" | kind {c.kind} | pages {c.page_start}-{c.page_end}"
                f" | {len(c.text)} chars =====\n{c.text}\n\n"
            )
    print(f"Wrote {OUT_PATH}")
    print(f"Chunks: {len(chunks)}")


if __name__ == "__main__":
    main()
