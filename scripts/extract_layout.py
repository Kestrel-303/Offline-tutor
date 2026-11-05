"""Write data/extracted/pages_layout.jsonl with layout-aware text for Unit 3.

PDF pages LAYOUT_RANGE are rebuilt from positioned spans and fraction bars
(see offline_tutor.layout); every other page is copied from pages.jsonl
unchanged. Prints counts only, never page text. Dev-time tool (pymupdf).

--report-wide-gaps writes nothing; it counts lines on WIDE_GAP_PAGES with a
gap wider than WIDE_GAP_PT between neighbouring spans (possible two-column
text) and lists the chunks in data/lessons.db that overlap each page. Run
scripts/build_lessons_db.py first.
"""

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pymupdf  # noqa: E402

from offline_tutor.layout import Bar, Token, layout_page, wide_gap_lines  # noqa: E402
from offline_tutor.normalize import normalize_page  # noqa: E402

PDF_PATH = ROOT / "data" / "G9-Mathematics-STB-2023-web.pdf"
PAGES_PATH = ROOT / "data" / "extracted" / "pages.jsonl"
OUT_PATH = ROOT / "data" / "extracted" / "pages_layout.jsonl"
DB_PATH = ROOT / "data" / "lessons.db"
LAYOUT_RANGE = (116, 161)

# Fraction bars in this book are thin filled rectangles about 0.84 pt tall.
# Table borders are 0.48 pt and frame lines are wider than BAR_MAX_WIDTH.
BAR_MIN_THICKNESS = 0.6
BAR_MAX_THICKNESS = 1.2
BAR_MIN_WIDTH = 2.0
BAR_MAX_WIDTH = 80.0

# Span bboxes from the math font are far taller than the glyphs, so token
# boxes are estimated from the baseline: top = baseline - ASCENT * size,
# bottom = baseline + DESCENT * size.
ASCENT = 0.75
DESCENT = 0.2

# --report-wide-gaps: pages to measure and the gap (pt) counted as "wide".
WIDE_GAP_PAGES = (117, 133)
WIDE_GAP_PT = 40.0


def page_tokens(page: pymupdf.Page) -> list[Token]:
    tokens: list[Token] = []
    layout = cast(dict[str, Any], page.get_text("dict"))
    for block in layout["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if not span["text"]:
                    continue
                x0, _, x1, _ = span["bbox"]
                base, size = span["origin"][1], span["size"]
                tokens.append(
                    Token(
                        span["text"],
                        x0,
                        base - ASCENT * size,
                        x1,
                        base + DESCENT * size,
                        size,
                    )
                )
    return tokens


def page_bars(page: pymupdf.Page) -> list[Bar]:
    bars: list[Bar] = []
    for drawing in page.get_drawings():
        if drawing.get("fill") is None:
            continue
        for item in drawing["items"]:
            if item[0] != "re":
                continue
            r = item[1]
            if (
                BAR_MIN_THICKNESS <= r.height <= BAR_MAX_THICKNESS
                and BAR_MIN_WIDTH <= r.width <= BAR_MAX_WIDTH
            ):
                bars.append(Bar(r.x0, r.x1, (r.y0 + r.y1) / 2))
    return bars


def report_wide_gaps() -> None:
    """Print wide-gap line counts per page and the chunks overlapping each
    page. A line is attributed to the overlapping chunk whose text contains
    the normalized line; lines found in no chunk count as unattributed."""
    if not DB_PATH.exists():
        sys.exit(f"{DB_PATH} not found; run scripts/build_lessons_db.py first.")
    conn = sqlite3.connect(DB_PATH)
    chunks = conn.execute(
        "SELECT id, kind, section, page_start, page_end, text FROM chunks ORDER BY id"
    ).fetchall()
    conn.close()
    doc = pymupdf.open(PDF_PATH)
    by_kind: Counter[str] = Counter()
    total = 0
    print(f"Wide gap threshold: {WIDE_GAP_PT:g} pt")
    for pno in range(WIDE_GAP_PAGES[0], WIDE_GAP_PAGES[1] + 1):
        page = doc[pno - 1]
        lines = wide_gap_lines(page_tokens(page), page_bars(page), WIDE_GAP_PT)
        overlap = [c for c in chunks if c[3] <= pno <= c[4]]
        total += len(lines)
        print(f"page {pno}: wide-gap lines {len(lines)}")
        for cid, kind, section, *_ in overlap:
            print(f"  chunk id={cid} kind={kind} section={section}")
        for line in lines:
            norm = normalize_page(line.text).strip()
            owner = next((c for c in overlap if norm and norm in c[5]), None)
            by_kind[owner[1] if owner else "unattributed"] += 1
    reading = sum(by_kind[k] for k in ("example", "explanation", "summary"))
    print(f"Total wide-gap lines: {total}")
    print(f"  in example/explanation/summary chunks: {reading}")
    print(f"  in exercise chunks: {by_kind['exercise']}")
    print(
        f"  unattributed (line text not found in an overlapping chunk): "
        f"{by_kind['unattributed']}"
    )
    for kind, n in sorted(by_kind.items()):
        print(f"  by kind {kind}: {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Layout-aware extraction.")
    parser.add_argument(
        "--report-wide-gaps",
        action="store_true",
        help="count possible two-column lines; writes no files",
    )
    if parser.parse_args().report_wide_gaps:
        report_wide_gaps()
        return
    doc = pymupdf.open(PDF_PATH)
    processed = merged = ambiguous = rows = 0
    with PAGES_PATH.open(encoding="utf-8") as src:
        records = [json.loads(line) for line in src]
    with OUT_PATH.open("w", encoding="utf-8") as out:
        for rec in records:
            pno = int(rec["page"])
            if LAYOUT_RANGE[0] <= pno <= LAYOUT_RANGE[1]:
                page = doc[pno - 1]
                text, stats, n_rows = layout_page(page_tokens(page), page_bars(page))
                rec = {"page": pno, "text": text}
                processed += 1
                merged += stats.merged
                ambiguous += stats.ambiguous
                rows += n_rows
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote {OUT_PATH}")
    print(f"pages processed: {processed}")
    print(f"fractions merged: {merged}")
    print(f"fractions left ambiguous: {ambiguous}")
    print(f"table rows built: {rows}")


if __name__ == "__main__":
    main()
