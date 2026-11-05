"""Layout-aware text reconstruction from positioned text and fraction bars.

Pure functions on plain data. The PDF adapter (scripts/extract_layout.py)
converts pages to Token and Bar values; nothing here reads files or PDFs.

Coordinates are PDF points with y growing downward. Token boxes are expected
to be tight glyph boxes (baseline-derived), not the font's full line box.
"""

import re
from dataclasses import dataclass, replace
from itertools import pairwise

# Horizontal slack when testing that a numerator/denominator lies within the
# bar's x extent.
FRACTION_X_TOL = 1.5
# Max vertical gap between a numerator's bottom (or denominator's top) and the
# bar. Negative values allow a slight overlap of the estimated glyph box.
FRACTION_MAX_GAP = 4.0
FRACTION_MIN_GAP = -1.0

# Adjacent tokens on the same baseline with this x gap or less join into one
# run before any other step (spans split by font changes or space glyphs).
RUN_MAX_GAP = 1.5
# Tokens whose bottoms differ by at most this are on the same baseline.
BASELINE_TOL = 1.0
# Font sizes within this are treated as equal when joining runs.
SIZE_TOL = 0.5

# Table rows: at least this many cells, each at most this many characters,
# with at least this x gap between neighbouring cells.
TABLE_MIN_CELLS = 3
TABLE_MAX_CELL_CHARS = 12
TABLE_MIN_GAP = 6.0
TABLE_SEPARATOR = " | "

# Tokens whose vertical centres are within this of a line's first token
# belong to that line.
LINE_CENTER_TOL = 4.0

_OPERATOR_RE = re.compile(r"[\s+\-*/=\u2212\u00d7\u00f7]")


@dataclass(frozen=True)
class Token:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class Bar:
    x0: float
    x1: float
    y: float


@dataclass(frozen=True)
class TextLine:
    y: float
    x: float
    text: str


@dataclass(frozen=True)
class FractionStats:
    merged: int = 0
    ambiguous: int = 0


def join_runs(tokens: list[Token]) -> list[Token]:
    """Join tokens that touch on the same baseline at the same size."""
    out: list[Token] = []
    for t in sorted(tokens, key=lambda t: t.x0):
        for k, prev in enumerate(out):
            if (
                abs(prev.y1 - t.y1) <= BASELINE_TOL
                and abs(prev.size - t.size) <= SIZE_TOL
                and -RUN_MAX_GAP <= t.x0 - prev.x1 <= RUN_MAX_GAP
            ):
                out[k] = replace(
                    prev,
                    text=prev.text + t.text,
                    x1=max(prev.x1, t.x1),
                    y0=min(prev.y0, t.y0),
                )
                break
        else:
            out.append(t)
    return [replace(t, text=t.text.strip()) for t in out if t.text.strip()]


def _wrap(part: str) -> str:
    return f"({part})" if _OPERATOR_RE.search(part) else part


def _inside(t: Token, bar: Bar) -> bool:
    return t.x0 >= bar.x0 - FRACTION_X_TOL and t.x1 <= bar.x1 + FRACTION_X_TOL


def stack_fractions(
    tokens: list[Token], bars: list[Bar]
) -> tuple[list[Token], list[Token], FractionStats]:
    """Merge numerator/denominator pairs around each bar into "n/d" tokens.

    Returns (unmerged tokens, fraction tokens, stats).

    A bar merges only when exactly one token sits just above it and exactly
    one just below, and neither token is a candidate for any other bar.
    Otherwise all its candidates stay unmerged and the bar counts as
    ambiguous. Bars with no candidates at all are ignored.
    """
    candidates: list[tuple[list[int], list[int]]] = []
    for bar in bars:
        above = [
            i
            for i, t in enumerate(tokens)
            if _inside(t, bar) and FRACTION_MIN_GAP <= bar.y - t.y1 <= FRACTION_MAX_GAP
        ]
        below = [
            i
            for i, t in enumerate(tokens)
            if _inside(t, bar) and FRACTION_MIN_GAP <= t.y0 - bar.y <= FRACTION_MAX_GAP
        ]
        candidates.append((above, below))

    claims: dict[int, int] = {}
    for above, below in candidates:
        for i in above + below:
            claims[i] = claims.get(i, 0) + 1

    used: set[int] = set()
    merged: list[Token] = []
    ambiguous = 0
    for above, below in candidates:
        if not above and not below:
            continue
        if (
            len(above) != 1
            or len(below) != 1
            or any(claims[i] > 1 for i in above + below)
        ):
            ambiguous += 1
            continue
        num, den = tokens[above[0]], tokens[below[0]]
        used.update((above[0], below[0]))
        merged.append(
            Token(
                text=f"{_wrap(num.text)}/{_wrap(den.text)}",
                x0=min(num.x0, den.x0),
                y0=num.y0,
                x1=max(num.x1, den.x1),
                y1=den.y1,
                size=num.size,
            )
        )
    rest = [t for i, t in enumerate(tokens) if i not in used]
    return rest, merged, FractionStats(len(merged), ambiguous)


def group_table_rows(
    tokens: list[Token], fractions: list[Token] | None = None
) -> tuple[list[TextLine], list[Token]]:
    """Find rows of short, spaced cells on one baseline.

    A row that shares a line with any fraction token is not a table: the gaps
    between its cells are where the fractions sit.

    Returns the rows (cells joined with TABLE_SEPARATOR in x order) and the
    tokens that were not part of any row.
    """
    rows: list[list[Token]] = []
    for t in sorted(tokens, key=lambda t: t.y1):
        if rows and abs(rows[-1][0].y1 - t.y1) <= BASELINE_TOL:
            rows[-1].append(t)
        else:
            rows.append([t])

    table: list[TextLine] = []
    rest: list[Token] = []
    for row in rows:
        cells = sorted(row, key=lambda t: t.x0)
        gaps_ok = all(b.x0 - a.x1 >= TABLE_MIN_GAP for a, b in pairwise(cells))
        short = all(len(c.text) <= TABLE_MAX_CELL_CHARS for c in cells)
        centre = cells[0].center_y
        near_fraction = any(
            abs(f.center_y - centre) <= LINE_CENTER_TOL for f in fractions or []
        )
        if len(cells) >= TABLE_MIN_CELLS and gaps_ok and short and not near_fraction:
            text = TABLE_SEPARATOR.join(c.text for c in cells)
            table.append(TextLine(cells[0].y1, cells[0].x0, text))
        else:
            rest.extend(row)
    return table, rest


def reading_order(tokens: list[Token]) -> list[TextLine]:
    """Group tokens into lines by vertical centre, then order each by x."""
    lines: list[list[Token]] = []
    for t in sorted(tokens, key=lambda t: (t.center_y, t.x0)):
        if lines and abs(lines[-1][0].center_y - t.center_y) <= LINE_CENTER_TOL:
            lines[-1].append(t)
        else:
            lines.append([t])
    out: list[TextLine] = []
    for line in lines:
        cells = sorted(line, key=lambda t: t.x0)
        out.append(TextLine(line[0].y1, cells[0].x0, " ".join(c.text for c in cells)))
    return out


def layout_page(tokens: list[Token], bars: list[Bar]) -> tuple[str, FractionStats, int]:
    """Rebuild a page's text. Returns (text, fraction stats, table rows)."""
    runs = join_runs(tokens)
    rest, fractions, stats = stack_fractions(runs, bars)
    table, rest = group_table_rows(rest, fractions)
    lines = sorted(
        table + reading_order(rest + fractions), key=lambda line: (line.y, line.x)
    )
    return "\n".join(line.text for line in lines), stats, len(table)
