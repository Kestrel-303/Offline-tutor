"""Normalize text extracted from textbook PDF pages.

Pure functions only: no file or network access. Non-ASCII characters are
written as \\u escapes.
"""

import re
import unicodedata

# U+123A and U+123B verified by the builder against the PDF on page 117;
# other pages not yet checked.
BRACKET_MAP = {
    "ሺ": "(",
    "ሻ": ")",
}

_SYMBOL_MAP = {
    "−": "-",  # minus sign
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "•": "- ",  # bullet
    "�": "",  # replacement character
}

# Four or more dots, optionally space-separated (". . . ."). Runs after NFKC,
# so an ellipsis U+2026 is already "...". A single "..." is kept.
_LEADER_RE = re.compile(r"(?:\. ?){3,}\.")
_HEADER_RE = re.compile(r"Unit\s+\d+\s*:\s*\S.*")
_PAGE_NUMBER_RE = re.compile(r"\d{1,3}")
_SPACES_RE = re.compile(r"[ \t]+")
_MANY_BLANKS_RE = re.compile(r"\n{4,}")

# Equation joining (see join_split_equations).
_MAX_JOIN_LEN = 30
_TRAILING_OP_RE = re.compile(r"(?:=|[+*/×÷]|(?:^|[\s\d)])-)$")
_MATH_START_RE = re.compile(r"[\w(]")


def apply_nfkc(text: str) -> str:
    """Unicode NFKC: math-italic letters become plain letters."""
    return unicodedata.normalize("NFKC", text)


def replace_symbols(text: str) -> str:
    """Minus, curly quotes and bullets to ASCII; drop U+FFFD and dot leaders."""
    for old, new in _SYMBOL_MAP.items():
        text = text.replace(old, new)
    return _LEADER_RE.sub(" ", text)


def map_brackets(text: str) -> str:
    """Map mis-encoded bracket glyphs to ASCII brackets."""
    for old, new in BRACKET_MAP.items():
        text = text.replace(old, new)
    return text


def strip_header_footer(text: str) -> str:
    """Drop a "Unit N: <title>" first line and a bare page-number last line.

    Only the first and last non-blank lines are checked.
    """
    lines = text.split("\n")
    nonblank = [i for i, line in enumerate(lines) if line.strip()]
    drop: set[int] = set()
    if nonblank and _HEADER_RE.fullmatch(lines[nonblank[0]].strip()):
        drop.add(nonblank[0])
    if nonblank and _PAGE_NUMBER_RE.fullmatch(lines[nonblank[-1]].strip()):
        drop.add(nonblank[-1])
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)


def clean_whitespace(text: str) -> str:
    """Collapse spaces, trim lines, collapse 3+ blank lines to one."""
    lines = [_SPACES_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return _MANY_BLANKS_RE.sub("\n\n", text).strip("\n")


def join_split_equations(text: str) -> tuple[str, int]:
    """Join displayed equations split across lines. Returns (text, joins).

    Heuristic (conservative; when unsure, do not join). Line B is appended
    to the line A directly above it only if all of these hold:
    - A ends with "=", "+", "*", "/", U+00D7 or U+00F7, or with "-" preceded
      by whitespace, a digit or ")" (so word hyphenation like "self-" is
      not joined);
    - B is non-blank (never join across a blank line);
    - B is at most _MAX_JOIN_LEN characters (a short number/token line);
    - B starts with a letter, digit or "(" and is not a "- " bullet.
    Joined lines are re-checked, so a chain like "a =" / "b +" / "c" joins.
    """
    out: list[str] = []
    joins = 0
    for line in text.split("\n"):
        if (
            out
            and _TRAILING_OP_RE.search(out[-1])
            and line
            and len(line) <= _MAX_JOIN_LEN
            and _MATH_START_RE.match(line)
        ):
            out[-1] = f"{out[-1]} {line}"
            joins += 1
        else:
            out.append(line)
    return "\n".join(out), joins


def normalize_page_with_stats(text: str) -> tuple[str, int]:
    """Normalize one page; also return the number of lines joined."""
    text = apply_nfkc(text)
    text = replace_symbols(text)
    text = map_brackets(text)
    text = strip_header_footer(text)
    text = clean_whitespace(text)
    return join_split_equations(text)


def normalize_page(text: str) -> str:
    """Normalize the text of one extracted textbook page."""
    return normalize_page_with_stats(text)[0]
