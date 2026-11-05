"""Write data/extracted/pages_layout.jsonl with layout-aware text for Unit 3.

PDF pages LAYOUT_RANGE are rebuilt from positioned spans and fraction bars
(see offline_tutor.layout); every other page is copied from pages.jsonl
unchanged. Prints counts only, never page text. Dev-time tool (pymupdf).
"""

import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pymupdf  # noqa: E402

from offline_tutor.layout import Bar, Token, layout_page  # noqa: E402

PDF_PATH = ROOT / "data" / "G9-Mathematics-STB-2023-web.pdf"
PAGES_PATH = ROOT / "data" / "extracted" / "pages.jsonl"
OUT_PATH = ROOT / "data" / "extracted" / "pages_layout.jsonl"
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


def main() -> None:
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
