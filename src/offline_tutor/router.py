"""Router: decide how to handle a question before any model is involved.

route() returns one of three routes:

- solve_equation: the question contains a linear equation in one variable
  that the equation engine can solve.
- explain_lesson: the question's words fit the lesson vocabulary.
- refuse: anything else. The caller shows REFUSAL_MESSAGE and never calls
  the language model.

Design B: the refusal rule is deterministic word coverage, not a BM25 score
(off-topic and on-topic BM25 scores overlap, so no threshold separates
them). All constants below were fixed before any evaluation was run.

No language model is imported or called here.
"""

import re
import sqlite3
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path
from typing import Literal

from offline_tutor.equations import Classification, classify

Route = Literal["solve_equation", "explain_lesson", "refuse"]
Reason = Literal[
    "equation_detected",
    "nonlinear_equation",
    "no_content_words",
    "out_of_lesson_term",
    "no_anchor_term",
    "low_coverage",
    "lesson_match",
]
Action = Literal["solve", "refuse", "continue"]

REFUSAL_MESSAGE = "I can't help with that"

# First guess, chosen before seeing any result. Not measured.
MIN_COVERAGE = 0.6

STOPWORDS = frozenset(
    (
        "a an the of to in on at for from by with and or but if then so as is "
        "are was were be been am do does did can could would should will shall "
        "may might must have has had it its this that these those there here i "
        "me my we us our you your he she they them his her their what which who "
        "whom whose when where why how not no yes please tell show give explain "
        "help let know want need about into than also just very any some more "
        "most other such only own same too"
    ).split()
)

GENERIC_HEADING_WORDS = frozenset(
    ("example", "activity", "exercise", "unit", "section", "introduction", "review")
)

# Engine classification -> action. Only a linear equation in one variable is
# solvable by the engine. Systems, multi-variable equations, no equation and
# unreadable input continue to the word rules.
EQUATION_ACTIONS: dict[Classification, Action] = {
    "linear_one_var": "solve",
    "nonlinear": "refuse",
    "system": "continue",
    "linear_other": "continue",
    "no_equation": "continue",
    "invalid": "continue",
}

# Derived from docs/pdf_recon.md at commit 1d2dc76: every unit and section
# title except sections 3.1 and 3.2, tokenized as above (also dropping
# GENERIC_HEADING_WORDS), stemmed, minus every stem in the lesson vocabulary
# built from data/lessons.db. Neither file is read at runtime for this set.
# Removed further, regular, similar, summari because they are ordinary English
# words, not subject terms (Tomas, 2026-11-17, before any eval).
OUT_OF_LESSON_TERMS: frozenset[str] = frozenset(
    (
        "applic",
        "congruenc",
        "dimens",
        "inequ",
        "non",
        "polygon",
        "probabl",
        "statist",
        "trigonometri",
        "vector",
    )
)

# Anchor stems shorter than this ("on" from "one", "us" from "using") are not
# real subject words and are dropped.
MIN_ANCHOR_LENGTH = 3

_WORD = re.compile(r"[a-z]+")


@lru_cache(maxsize=1)
def _stem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='porter unicode61')")
    conn.execute("CREATE VIRTUAL TABLE v USING fts5vocab(t, 'row')")
    return conn


@cache
def stem(word: str) -> str:
    """Return the single term FTS5 'porter unicode61' makes from word.

    Same stemmer as the lessons index. If the tokenizer gives zero or more
    than one term, the lowercase word is returned unchanged.
    """
    conn = _stem_conn()
    with conn:
        conn.execute("INSERT INTO t (x) VALUES (?)", (word,))
        terms = [row[0] for row in conn.execute("SELECT term FROM v")]
        conn.execute("DELETE FROM t")
    return terms[0] if len(terms) == 1 else word.lower()


def content_words(
    text: str, extra_stopwords: frozenset[str] = frozenset()
) -> list[str]:
    """Lowercase letter runs, minus single letters, STOPWORDS and extras."""
    return [
        w
        for w in _WORD.findall(text.lower())
        if len(w) > 1 and w not in STOPWORDS and w not in extra_stopwords
    ]


def content_stems(text: str, extra_stopwords: frozenset[str] = frozenset()) -> set[str]:
    return {stem(w) for w in content_words(text, extra_stopwords)}


@dataclass(frozen=True)
class Lexicon:
    vocabulary: frozenset[str]
    anchors: frozenset[str]


def build_lexicon(db_path: str | Path) -> Lexicon:
    """Build the lexicon from lessons.db, opened read-only.

    vocabulary: stems of every content word in chunk headings and text.
    anchors: stems of heading words only, minus GENERIC_HEADING_WORDS and
    stems shorter than MIN_ANCHOR_LENGTH.
    """
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute("SELECT heading, text FROM chunks").fetchall()
    finally:
        conn.close()
    vocabulary: set[str] = set()
    anchors: set[str] = set()
    generic_stems = {stem(w) for w in GENERIC_HEADING_WORDS}
    for heading, text in rows:
        vocabulary |= content_stems(heading) | content_stems(text)
        anchors |= content_stems(heading, GENERIC_HEADING_WORDS) - generic_stems
    anchors = {a for a in anchors if len(a) >= MIN_ANCHOR_LENGTH}
    return Lexicon(frozenset(vocabulary), frozenset(anchors))


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    reason: Reason
    coverage: float | None = None
    matched: tuple[str, ...] = ()
    unmatched: tuple[str, ...] = ()
    banned_hits: tuple[str, ...] = ()
    anchor_hits: tuple[str, ...] = ()
    equation_label: str | None = None


def route(
    question: str, lexicon: Lexicon, banned: frozenset[str] = OUT_OF_LESSON_TERMS
) -> RouteDecision:
    """Route a question. Deterministic; never calls a language model."""
    label = classify(question)  # never raises
    action = EQUATION_ACTIONS.get(label, "continue")
    if action == "solve":
        return RouteDecision(
            "solve_equation", "equation_detected", equation_label=label
        )
    if action == "refuse":
        return RouteDecision("refuse", "nonlinear_equation", equation_label=label)

    content = content_stems(question)
    if not content:
        return RouteDecision("refuse", "no_content_words", equation_label=label)

    matched = tuple(sorted(content & lexicon.vocabulary))
    unmatched = tuple(sorted(content - lexicon.vocabulary))
    coverage = len(matched) / len(content)
    banned_hits = tuple(sorted(content & banned))
    anchor_hits = tuple(sorted(content & lexicon.anchors))

    def decide(r: Route, reason: Reason) -> RouteDecision:
        return RouteDecision(
            r, reason, coverage, matched, unmatched, banned_hits, anchor_hits, label
        )

    if banned_hits:
        return decide("refuse", "out_of_lesson_term")
    if not anchor_hits:
        return decide("refuse", "no_anchor_term")
    if coverage < MIN_COVERAGE:
        return decide("refuse", "low_coverage")
    return decide("explain_lesson", "lesson_match")
