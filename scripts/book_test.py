"""Quick check: are the textbook PDF pages text-based or scanned?

Prints the number of extracted text characters for the first pages.
Pages with ~0 characters are likely scanned images and would need OCR.

Usage:
    python scripts/book_test.py
"""

from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "data" / "G9-Mathematics-STB-2023-web.pdf"
MAX_PAGES = 20

with pymupdf.open(PDF_PATH) as doc:
    print(f"{PDF_PATH.relative_to(ROOT)}: {doc.page_count} pages")
    for page in doc.pages(0, min(MAX_PAGES, doc.page_count)):
        n = len(page.get_text().strip())
        print(f"page {page.number + 1:>3}: {n} chars")
