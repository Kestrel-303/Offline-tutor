# PDF recon: Grade 9 math textbook

Date: 2026-10-30. Tool: PyMuPDF 2.0 (`import pymupdf`), `page.get_text()` default mode.
This file contains only titles, page numbers and observations. No textbook text.

## File
- `data/G9-Mathematics-STB-2023-web.pdf` (19.1 MB, not committed)
- 375 pages, about 411,000 extracted characters (median 1,120 per page).
- **Text-based: yes.** Only 4 pages have under 50 characters: PDF pages 3, 11, 374, 375 (likely cover/image/blank pages). No OCR needed.
- Full page text extracted to `data/extracted/pages.jsonl` (git-ignored via `data/*`).

## Units
The PDF has no embedded outline (`get_toc()` is empty). Ranges below come from the running "Unit N:" page headers. PDF page = printed page + 11.

| Unit | Title | PDF pages |
|---|---|---|
| 1 | Further on Sets | 12-37 |
| 2 | The Number System | 38-115 |
| 3 | Solving Equations | 116-161 |
| 4 | Solving Inequalities | 162-195 |
| 5 | Introduction to Trigonometry | 196-217 |
| 6 | Regular Polygons | 218-249 |
| 7 | Congruency and Similarity | 250-287 |
| 8 | Vectors in Two Dimensions | 288-321 |
| 9 | Statistics and Probability | 322-375 |

Contents pages: PDF 8-10.

## Where "linear equations" lives
25 pages match "linear equation(s)" (case-insensitive). Excluding the contents page (8), 21 are in Unit 3 and 3 in Unit 4 (163, 168, 171, likely linear inequalities).

Unit 3 sections (from the contents page, printed page + 11):

| Section | Title | PDF pages (approx.) |
|---|---|---|
| 3.1 | Revision on Linear Equation in One Variable | 117-119 |
| 3.2 | Systems of Linear Equations in Two Variables | 120-133 |
| 3.3 | Solving Non-linear Equations | 134-153 |
| 3.4 | Applications of Equations | 154-157 |
| - | Summary / Review Exercise | 158-161 |

**Candidate scope:** Unit 3, sections 3.1 and 3.2 (PDF 117-133), plus the linear parts of 3.4 and the summary/review (154-161). 3.1 is short (about 3 pages) and is labelled a revision, so one-variable content is thin; 3.2 (two-variable systems) is the bulk. Decide whether scope = 3.1 only (matches the current one-variable eval/questions) or 3.1 + 3.2. Section 3.3 is out of scope.

Top match pages: 158 (7), 117 (6), 121 (6), 120 (5).

## Extraction problems seen
1. **Parentheses come out as Ethiopic letters.** `(` and `)` are extracted as U+123A and U+123B (about 290 times in Unit 3). Must be mapped back before indexing or parsing with SymPy.
2. **Math italic letters.** Variables are Unicode math italic (U+1D465 for x, U+1D466 for y, U+1D44E for a, ...). They will not match a plain `x` in FTS5 search or SymPy. Normalize with NFKC.
3. **Unicode minus** (U+2212, ~500 in Unit 3), plus ≠, ≥, ±, √. Map minus to `-`.
4. **Split equations.** Displayed equations are broken across lines, e.g. the left side and `=` on one line and the right side on the next. Stacked fractions are likely split the same way (not yet checked one by one).
5. **Odd spacing.** Missing space before operators (`2x+ 3`), long runs of leading spaces from centered math, many whitespace-only lines.
6. **Repeated header and footer.** Every page starts with "Unit N: Title" and ends with the printed page number. Strip both before chunking.
7. **Bullets and box labels on their own lines** (a bullet, then the keyword on the next line), and sidebar keyword lists mixed into the body.
8. **Contents page** has dot leaders extracted as replacement characters (U+FFFD) and underscore leaders.
9. Ligatures: none noticed in the sampled pages, but not searched for systematically.

Not checked: tables, images with embedded equations, exercise answer keys (if any).
