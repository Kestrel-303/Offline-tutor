"""SQLite FTS5 lesson database: store chunks and search them.

Standard-library sqlite3 only. The FTS5 table is kept in sync by direct
inserts (its rowid equals chunks.id) rather than external content with
triggers: the database is rebuilt from scratch and never updated in place,
so direct inserts are the simpler choice.

Scores: SQLite FTS5 bm25() returns a value where LOWER (more negative) means
a BETTER match. Results also carry relevance = -bm25, so higher is better.
No refusal threshold is applied here.
"""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from offline_tutor.chunk import Chunk

STOPWORDS = frozenset(
    {"the", "a", "an", "is", "of", "to", "how", "do", "i", "me", "what", "can", "you"}
)

# Kinds left out of search() unless the caller passes kinds explicitly:
# exercises are practice questions without worked answers.
DEFAULT_EXCLUDED_KINDS = ("exercise",)

_SCHEMA = """
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    section TEXT NOT NULL,
    section_title TEXT NOT NULL,
    heading TEXT NOT NULL,
    kind TEXT NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_count INTEGER NOT NULL
);
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    heading, section_title, text, tokenize='porter unicode61'
);
"""


@dataclass
class SearchResult:
    chunk_id: int
    bm25: float  # lower is better (SQLite FTS5 convention)
    relevance: float  # -bm25, higher is better
    section: str
    heading: str
    kind: str
    page_start: int
    page_end: int
    text: str


def create_db(path: str | Path) -> sqlite3.Connection:
    """Open a database at path (":memory:" allowed) and create the tables."""
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    return conn


def insert_chunks(conn: sqlite3.Connection, chunks: Iterable[Chunk]) -> None:
    """Insert chunks into the chunks table and the FTS index (same rowid)."""
    with conn:
        for c in chunks:
            cur = conn.execute(
                "INSERT INTO chunks (section, section_title, heading, kind,"
                " page_start, page_end, text, char_count)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    c.section,
                    c.section_title,
                    c.heading,
                    c.kind,
                    c.page_start,
                    c.page_end,
                    c.text,
                    len(c.text),
                ),
            )
            conn.execute(
                "INSERT INTO chunks_fts (rowid, heading, section_title, text)"
                " VALUES (?, ?, ?, ?)",
                (cur.lastrowid, c.heading, c.section_title, c.text),
            )


def build_match_query(user_text: str) -> str | None:
    """Turn free text into a safe FTS5 MATCH string, or None if nothing left.

    Lowercases, replaces every character that is not a letter, digit or
    space with a space, drops STOPWORDS, double-quotes each token and joins
    with OR. Quoting plain alphanumeric tokens means FTS5 operators and
    punctuation in the input can never cause a syntax error.
    """
    cleaned = "".join(ch if ch.isalnum() else " " for ch in user_text.lower())
    tokens = [t for t in cleaned.split() if t not in STOPWORDS]
    if not tokens:
        return None
    return " OR ".join(f'"{t}"' for t in tokens)


def search(
    conn: sqlite3.Connection,
    user_text: str,
    limit: int = 5,
    kinds: Iterable[str] | None = None,
) -> list[SearchResult]:
    """Return up to limit chunks ordered by bm25 (best first), ties by id.

    kinds, if given, restricts results to those chunk kinds; by default every
    kind except DEFAULT_EXCLUDED_KINDS is searched. Returns [] for empty or
    unmatchable queries.
    """
    query = build_match_query(user_text)
    if query is None:
        return []
    sql = (
        "SELECT c.id, bm25(chunks_fts) AS score, c.section, c.heading, c.kind,"
        " c.page_start, c.page_end, c.text"
        " FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid"
        " WHERE chunks_fts MATCH ?"
    )
    params: list[object] = [query]
    if kinds is None:
        excluded = list(DEFAULT_EXCLUDED_KINDS)
        sql += f" AND c.kind NOT IN ({', '.join('?' * len(excluded))})"
        params.extend(excluded)
    else:
        kind_list = list(kinds)
        if not kind_list:
            return []
        sql += f" AND c.kind IN ({', '.join('?' * len(kind_list))})"
        params.extend(kind_list)
    sql += " ORDER BY score, c.id LIMIT ?"
    params.append(limit)
    return [
        SearchResult(row[0], row[1], -row[1], *row[2:])
        for row in conn.execute(sql, params)
    ]
