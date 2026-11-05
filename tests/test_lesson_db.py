"""Tests for the SQLite FTS5 lesson database. All strings are made up."""

import sqlite3

import pytest

from offline_tutor.chunk import Chunk
from offline_tutor.lesson_db import (
    build_match_query,
    create_db,
    insert_chunks,
    search,
)

# Non-ASCII test characters, built with chr() so the formatter keeps the
# source ASCII-only.
E_ACUTE = chr(0x00E9)
LE = chr(0x2264)
MINUS = chr(0x2212)
LQ = chr(0x201C)
RQ = chr(0x201D)

ALL_KINDS = ["explanation", "example", "exercise"]


def _chunk(text: str, kind: str = "explanation", heading: str = "") -> Chunk:
    return Chunk("4.1", "Blah topic", heading, kind, 1, 1, text)


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = create_db(":memory:")
    insert_chunks(
        c,
        [
            _chunk("Blorbs are made of wibble."),  # id 1
            _chunk("A zorp equation has one unknown. Zorp equation zorp equation."),
            _chunk("Solve the zorp equations by flarging.", "example", "Example 1"),
            _chunk("Practice zorp equation questions.", "exercise", "Exercise 4.1"),
            _chunk("Quux grows near the river."),  # id 5
            _chunk("Quux grows near the river."),  # id 6, same as id 5
        ],
    )
    return c


def test_chunks_table_and_char_count(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT section, kind, char_count FROM chunks WHERE id = 1"
    ).fetchone()
    assert row == ("4.1", "explanation", len("Blorbs are made of wibble."))
    assert conn.execute("SELECT count(*) FROM chunks_fts").fetchone() == (6,)


def test_ranking_and_relevance(conn: sqlite3.Connection) -> None:
    results = search(conn, "zorp equation", kinds=ALL_KINDS)
    assert results[0].chunk_id == 2  # most occurrences
    assert {r.chunk_id for r in results} == {2, 3, 4}
    for r in results:
        assert r.relevance == -r.bm25
        assert r.bm25 < 0  # lower bm25 = better match
    assert [r.bm25 for r in results] == sorted(r.bm25 for r in results)


def test_porter_stemming(conn: sqlite3.Connection) -> None:
    assert {2, 3, 4} <= {r.chunk_id for r in search(conn, "equations", kinds=ALL_KINDS)}
    assert 3 in {r.chunk_id for r in search(conn, "flarg")}


def test_heading_is_indexed(conn: sqlite3.Connection) -> None:
    assert search(conn, "exercise", kinds=["exercise"])[0].chunk_id == 4


def test_ties_broken_by_id(conn: sqlite3.Connection) -> None:
    assert [r.chunk_id for r in search(conn, "quux")] == [5, 6]


def test_deterministic(conn: sqlite3.Connection) -> None:
    assert search(conn, "zorp river") == search(conn, "zorp river")


def test_kinds_filter(conn: sqlite3.Connection) -> None:
    assert [r.chunk_id for r in search(conn, "zorp", kinds=["example"])] == [3]
    assert search(conn, "zorp", kinds=[]) == []


def test_exercise_excluded_by_default(conn: sqlite3.Connection) -> None:
    assert {r.chunk_id for r in search(conn, "zorp equation")} == {2, 3}
    assert search(conn, "practice") == []


def test_exercise_included_on_request(conn: sqlite3.Connection) -> None:
    assert [r.chunk_id for r in search(conn, "practice", kinds=["exercise"])] == [4]
    ids = {r.chunk_id for r in search(conn, "zorp equation", kinds=ALL_KINDS)}
    assert 4 in ids


def test_limit(conn: sqlite3.Connection) -> None:
    assert len(search(conn, "zorp", limit=2)) == 2


def test_no_match_and_empty(conn: sqlite3.Connection) -> None:
    assert search(conn, "xyzzy") == []
    assert search(conn, "") == []
    assert search(conn, "what is the") == []


def test_build_match_query_basic() -> None:
    assert (
        build_match_query("How do I solve 3x + 5 = 20?")
        == '"solve" OR "3x" OR "5" OR "20"'
    )


@pytest.mark.parametrize(
    "text", ["", "   ", "the a an is of to how do i me what can you", "+-*()"]
)
def test_build_match_query_none(text: str) -> None:
    assert build_match_query(text) is None


def test_build_match_query_unicode() -> None:
    assert (
        build_match_query(f"Zorp {E_ACUTE}quation {LE} 3")
        == f'"zorp" OR "{E_ACUTE}quation" OR "3"'
    )


@pytest.mark.parametrize(
    "text",
    [
        'zorp "equation',
        "zorp (equation",
        "zorp) OR (",
        "-zorp",
        "zorp*",
        "NOT AND OR NEAR",
        "x - y = -3",
        "col:zorp ^zorp {zorp}",
        f"{E_ACUTE}quation {MINUS} {LQ}zorp{RQ}",
    ],
)
def test_special_characters_never_raise(conn: sqlite3.Connection, text: str) -> None:
    search(conn, text)
