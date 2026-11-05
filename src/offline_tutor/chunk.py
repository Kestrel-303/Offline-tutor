"""Split normalized textbook pages into lesson chunks for retrieval.

Pure functions only: no file or network access.

Pipeline (each step is a small helper below):
1. to_lines: flatten pages into (page, line) pairs; blank lines are kept as
   paragraph markers.
2. split_blocks: start a new block at every section heading ("3.2 Title"),
   sub-heading ("3.2.1 Title") or standalone label line ("Example 2",
   "Exercise 3.1", "Summary"). A heading/label line always opens the block
   that holds the text after it.
3. pack_block: cut each block at blank-line paragraphs into chunks of about
   TARGET_MIN..TARGET_MAX characters, never above HARD_MAX. Cuts happen only
   between lines; an oversized paragraph is cut after a line that ends a
   sentence. A worked example of at most HARD_MAX characters stays whole.
4. drop_label_only: a chunk under LABEL_ONLY_MAX characters whose lines are
   all headings or labels has no body and is dropped.
5. merge_tiny: a chunk under MIN_CHARS is merged into the previous chunk of
   the same section and kind when the result stays within HARD_MAX.
6. split_examples: a chunk holding two or more example labels is split at
   each label.

Text before the first numbered section heading (the unit introduction) is
dropped in step 2. Example and exercise chunks carry their context in the
heading: "3.2.2 Title > Example 1", or "3.1 Section title > Example 1" when
no subsection heading has been seen in the section.
"""

import re
from dataclasses import dataclass
from itertools import pairwise

TARGET_MIN = 600
TARGET_MAX = 1000
HARD_MAX = 1500
MIN_CHARS = 200
LABEL_ONLY_MAX = 100
HEADING_SEP = " > "

# "3.2 Title" / "3.2.1 Title". The title must start with a letter, so a line
# like "100.00. Find ..." is not a heading. Long lines are prose, not headings.
_HEADING_RE = re.compile(r"(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\s+([A-Za-z].*)")
_MAX_HEADING_LEN = 80
# A wrapped heading title continues on a short line starting lowercase.
_MAX_TITLE_CONT_LEN = 50

# Standalone label lines only ("Example 1", "Exercise 3.1", "Remark:").
# Lines that merely start with the word ("Note that ...") are prose.
_LABEL_RE = re.compile(
    r"(Unit Summary|Summary|Key Terms|Review Exercises?|Example|Exercise|"
    r"Activity|Definition|Note|Remark)(?:\s+\d+(?:\.\d+)*)?\s*:?",
)
LABEL_KINDS = {
    "Example": "example",
    "Exercise": "exercise",
    "Review Exercise": "exercise",
    "Review Exercises": "exercise",
    "Activity": "exercise",
    "Summary": "summary",
    "Unit Summary": "summary",
    "Key Terms": "summary",
}
DEFAULT_KIND = "explanation"
# Label kinds whose heading carries the section/subsection context.
CONTEXT_KINDS = {"example", "exercise"}

# A page with this many distinct level-2 headings is a contents list.
_CONTENTS_MIN_HEADINGS = 3

_SENTENCE_END_RE = re.compile(r"[.?!:]$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.?!])\s+")

Line = tuple[int, str]  # (pdf_page_number, text); text "" marks a blank line


@dataclass
class Chunk:
    section: str
    section_title: str
    heading: str
    kind: str
    page_start: int
    page_end: int
    text: str


@dataclass
class _Block:
    section: str
    section_title: str
    heading: str
    kind: str
    lines: list[Line]
    head_count: int = 0
    subsection: str = ""  # "3.2.1 Title" of the nearest subsection, if any


@dataclass
class ChunkStats:
    intro_blocks_dropped: int = 0
    label_only_dropped: int = 0
    example_splits: int = 0


def match_heading(line: str) -> tuple[str, str] | None:
    """Return (number, title) if the line is a numbered heading."""
    if len(line) > _MAX_HEADING_LEN:
        return None
    m = _HEADING_RE.fullmatch(line)
    return (m.group(1), m.group(2)) if m else None


def classify_label(line: str) -> str | None:
    """Return the kind for a standalone label line, or None if not a label."""
    m = _LABEL_RE.fullmatch(line)
    if not m:
        return None
    return LABEL_KINDS.get(m.group(1), DEFAULT_KIND)


def find_section_pages(pages: list[tuple[int, str]]) -> dict[str, int]:
    """Map each level-2 section number ("3.1") to the page where it starts.

    Contents pages (with _CONTENTS_MIN_HEADINGS or more distinct level-2
    headings) are skipped. The first occurrence wins.
    """
    found: dict[str, int] = {}
    for page, text in pages:
        numbers = []
        for line in text.split("\n"):
            h = match_heading(line)
            if h and h[0].count(".") == 1:
                numbers.append(h[0])
        if len(set(numbers)) >= _CONTENTS_MIN_HEADINGS:
            continue
        for number in numbers:
            found.setdefault(number, page)
    return found


def to_lines(pages: list[tuple[int, str]]) -> list[Line]:
    """Flatten pages into (page, line) pairs, keeping blank lines."""
    return [(page, line) for page, text in pages for line in text.split("\n")]


def _join_title(lines: list[Line], i: int, title: str) -> tuple[str, int]:
    """Append a wrapped title continuation line. Returns (title, lines used)."""
    if i + 1 < len(lines):
        nxt = lines[i + 1][1]
        if nxt and len(nxt) <= _MAX_TITLE_CONT_LEN and nxt[0].islower():
            return f"{title} {nxt}", 2
    return title, 1


def split_blocks(lines: list[Line]) -> list[_Block]:
    """Split lines into blocks at headings and standalone labels.

    A level-2 heading sets section and section_title; a level-3 heading or a
    label sets heading. Kind comes from the label (see LABEL_KINDS) and is
    "explanation" after a heading. Text before the first heading gets an
    empty section. Example and exercise labels get a context heading (see
    the module docstring).
    """
    blocks = [_Block("", "", "", DEFAULT_KIND, [])]
    i = 0
    while i < len(lines):
        page, text = lines[i]
        h = match_heading(text)
        kind = None if h else classify_label(text)
        if not h and not kind:
            blocks[-1].lines.append((page, text))
            i += 1
            continue
        prev = blocks[-1]
        section, title, heading, used = prev.section, prev.section_title, "", 1
        subsection = prev.subsection
        if h:
            full, used = _join_title(lines, i, h[1])
            if h[0].count(".") == 1:
                section, title, subsection = h[0], full, ""
            else:
                heading = subsection = f"{h[0]} {full}"
            kind = DEFAULT_KIND
        else:
            heading = text.rstrip(":").strip()
            if kind in CONTEXT_KINDS:
                context = subsection or f"{section} {title}".strip()
                if context:
                    heading = f"{context}{HEADING_SEP}{heading}"
        assert kind is not None
        blocks.append(
            _Block(section, title, heading, kind, lines[i : i + used], used, subsection)
        )
        i += used
    return _fold_empty(blocks)


def _fold_empty(blocks: list[_Block]) -> list[_Block]:
    """Prepend the lines of a block with no body (only its heading lines) to
    the next block, so a heading line never sits apart from its text."""
    out: list[_Block] = []
    carry: list[Line] = []
    for b in blocks:
        b.lines = carry + b.lines
        body = b.lines[len(carry) + b.head_count :]
        if any(t for _, t in body):
            out.append(b)
            carry = []
        else:
            carry = [line for line in b.lines if line[1]]
    if carry:
        if out:
            out[-1].lines.extend(carry)
        else:
            out.append(_Block("", "", "", DEFAULT_KIND, carry))
    return out


def paragraphs(lines: list[Line]) -> list[list[Line]]:
    """Group lines into paragraphs separated by blank lines."""
    out: list[list[Line]] = [[]]
    for line in lines:
        if line[1]:
            out[-1].append(line)
        elif out[-1]:
            out.append([])
    return [p for p in out if p]


def _size(lines: list[Line]) -> int:
    return sum(len(t) for _, t in lines) + max(len(lines) - 1, 0)


def split_long_line(line: Line) -> list[Line]:
    """Cut a single line over HARD_MAX at sentence boundaries (last resort)."""
    page, text = line
    pieces: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        while len(sentence) > HARD_MAX:
            pieces.append(sentence[:HARD_MAX])
            sentence = sentence[HARD_MAX:]
        if pieces and len(pieces[-1]) + 1 + len(sentence) <= TARGET_MAX:
            pieces[-1] = f"{pieces[-1]} {sentence}"
        else:
            pieces.append(sentence)
    return [(page, p) for p in pieces]


def split_paragraph(para: list[Line]) -> list[list[Line]]:
    """Cut an oversized paragraph between lines.

    A cut is made after a line ending a sentence (".", "?", "!", ":") once
    the piece has at least TARGET_MIN characters, or forced before a line
    that would push the piece over HARD_MAX.
    """
    if _size(para) <= TARGET_MAX:
        return [para]
    flat: list[Line] = []
    for line in para:
        flat.extend(split_long_line(line) if len(line[1]) > HARD_MAX else [line])
    pieces: list[list[Line]] = [[]]
    for line in flat:
        if pieces[-1] and _size(pieces[-1] + [line]) > HARD_MAX:
            pieces.append([])
        pieces[-1].append(line)
        size = _size(pieces[-1])
        if size >= TARGET_MIN and (
            _SENTENCE_END_RE.search(line[1]) or size >= TARGET_MAX
        ):
            pieces.append([])
    return [p for p in pieces if p]


def _render(paras: list[list[Line]]) -> str:
    return "\n\n".join("\n".join(t for _, t in p) for p in paras)


def _make_chunk(block: _Block, paras: list[list[Line]]) -> Chunk:
    pages = [page for p in paras for page, _ in p]
    return Chunk(
        block.section,
        block.section_title,
        block.heading,
        block.kind,
        min(pages),
        max(pages),
        _render(paras),
    )


def pack_block(block: _Block) -> list[Chunk]:
    """Pack a block's paragraphs into chunks (see module docstring)."""
    paras = paragraphs(block.lines)
    if not paras:
        return []
    if block.kind == "example" and len(_render(paras)) <= HARD_MAX:
        return [_make_chunk(block, paras)]
    pieces = [piece for p in paras for piece in split_paragraph(p)]
    chunks: list[Chunk] = []
    cur: list[list[Line]] = []
    for piece in pieces:
        size = len(_render(cur + [piece]))
        if cur and (
            size > HARD_MAX or (size > TARGET_MAX and len(_render(cur)) >= TARGET_MIN)
        ):
            chunks.append(_make_chunk(block, cur))
            cur = []
        cur.append(piece)
    if cur:
        chunks.append(_make_chunk(block, cur))
    return chunks


def _is_heading_or_label(line: str) -> bool:
    return match_heading(line) is not None or classify_label(line) is not None


def drop_label_only(chunks: list[Chunk]) -> tuple[list[Chunk], int]:
    """Drop chunks under LABEL_ONLY_MAX chars whose non-blank lines are all
    headings or labels. Returns (kept chunks, number dropped)."""
    kept = [
        c
        for c in chunks
        if len(c.text) >= LABEL_ONLY_MAX
        or not all(_is_heading_or_label(t) for t in c.text.split("\n") if t)
    ]
    return kept, len(chunks) - len(kept)


def split_examples(chunks: list[Chunk]) -> tuple[list[Chunk], int]:
    """Split each chunk holding two or more example label lines at every
    label. Text before the first label stays with the first piece. A piece
    over HARD_MAX is cut further between lines (see split_paragraph).

    Pieces keep the parent's page range (line pages are not tracked after
    packing), and their heading context with the new label. Returns (chunks,
    number of chunks split).
    """
    out: list[Chunk] = []
    split = 0
    for c in chunks:
        lines = c.text.split("\n")
        starts = [i for i, t in enumerate(lines) if classify_label(t) == "example"]
        if len(starts) < 2:
            out.append(c)
            continue
        split += 1
        context = c.heading.rpartition(HEADING_SEP)[0]
        bounds = [0, *starts[1:], len(lines)]
        for a, b in pairwise(bounds):
            label = lines[max(a, starts[0])].rstrip(":").strip()
            heading = f"{context}{HEADING_SEP}{label}" if context else label
            body = [(c.page_start, t) for t in lines[a:b]]
            while body and not body[-1][1]:
                body.pop()
            for piece in split_paragraph(body) if _size(body) > HARD_MAX else [body]:
                text = "\n".join(t for _, t in piece)
                out.append(
                    Chunk(
                        c.section,
                        c.section_title,
                        heading,
                        "example",
                        c.page_start,
                        c.page_end,
                        text,
                    )
                )
    return out, split


def merge_tiny(chunks: list[Chunk]) -> list[Chunk]:
    """Merge chunks under MIN_CHARS into the previous same-section, same-kind
    chunk when the merged text stays within HARD_MAX. The merged chunk keeps
    the previous chunk's heading."""
    out: list[Chunk] = []
    for c in chunks:
        prev = out[-1] if out else None
        if (
            prev
            and len(c.text) < MIN_CHARS
            and prev.section == c.section
            and prev.kind == c.kind
            and len(prev.text) + 2 + len(c.text) <= HARD_MAX
        ):
            prev.text = f"{prev.text}\n\n{c.text}"
            prev.page_end = max(prev.page_end, c.page_end)
        else:
            out.append(c)
    return out


def chunk_pages_with_stats(
    pages: list[tuple[int, str]],
) -> tuple[list[Chunk], ChunkStats]:
    """Chunk a list of (pdf_page_number, normalized_page_text) and report
    what was dropped or split (see module docstring)."""
    stats = ChunkStats()
    blocks = split_blocks(to_lines(pages))
    kept = [b for b in blocks if b.section]
    stats.intro_blocks_dropped = len(blocks) - len(kept)
    chunks, stats.label_only_dropped = drop_label_only(
        [c for b in kept for c in pack_block(b)]
    )
    chunks, stats.example_splits = split_examples(merge_tiny(chunks))
    return chunks, stats


def chunk_pages(pages: list[tuple[int, str]]) -> list[Chunk]:
    """Chunk a list of (pdf_page_number, normalized_page_text)."""
    return chunk_pages_with_stats(pages)[0]
