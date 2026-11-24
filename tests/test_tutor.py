"""Tests for the terminal tutor core (no model).

Every question and chunk text here is made up. The lesson database is a tiny
temporary SQLite file built in the test.
"""

import ast
from pathlib import Path
from typing import Any

import pytest

import offline_tutor.tutor as tutor
from offline_tutor.chunk import Chunk
from offline_tutor.equations import InvalidInputError
from offline_tutor.lesson_db import create_db, insert_chunks
from offline_tutor.router import REFUSAL_MESSAGE, Lexicon, build_lexicon
from offline_tutor.tutor import TutorReply, answer

TUTOR_SOURCE = Path(tutor.__file__)

LESSON_CHUNKS = [
    Chunk(
        "9.1",
        "Made up linear equations",
        "9.1.1 Solving linear equations",
        "explanation",
        1,
        1,
        "A linear equation in one variable keeps both sides balanced.",
    ),
    Chunk(
        "9.1",
        "Made up linear equations",
        "9.1.2 Balancing linear equations",
        "explanation",
        2,
        2,
        "Do the same thing to both sides of a linear equation.",
    ),
]


def _make_db(path: Path, chunks: list[Chunk]) -> Path:
    conn = create_db(path)
    insert_chunks(conn, chunks)
    conn.close()
    return path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return _make_db(tmp_path / "lessons.db", LESSON_CHUNKS)


@pytest.fixture
def lexicon(db_path: Path) -> Lexicon:
    return build_lexicon(db_path)


def _forbid_solver(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(text: str) -> Any:
        raise AssertionError("solve_linear must not be called")

    monkeypatch.setattr(tutor, "solve_linear", boom)


def test_refusal_is_exact_message_and_never_solves(
    monkeypatch: pytest.MonkeyPatch, lexicon: Lexicon, db_path: Path
) -> None:
    _forbid_solver(monkeypatch)
    reply = answer("what is the capital of France", lexicon, db_path)
    assert reply.kind == "refusal"
    assert reply.text == REFUSAL_MESSAGE
    assert reply.interpreted is None
    assert reply.route_reason != ""


def test_refusal_never_calls_explainer(lexicon: Lexicon, db_path: Path) -> None:
    def explainer(messages: list[dict[str, str]]) -> str:
        raise AssertionError("explainer must not be called on refusal")

    reply = answer("what is the capital of France", lexicon, db_path, explainer)
    assert reply.text == REFUSAL_MESSAGE


def test_nonlinear_equation_is_refused(
    monkeypatch: pytest.MonkeyPatch, lexicon: Lexicon, db_path: Path
) -> None:
    _forbid_solver(monkeypatch)
    reply = answer("solve x^2 = 9", lexicon, db_path)
    assert reply.kind == "refusal"
    assert reply.text == REFUSAL_MESSAGE
    assert reply.route_reason == "nonlinear_equation"


def test_linear_equation_is_solved(lexicon: Lexicon, db_path: Path) -> None:
    reply = answer("solve 2x + 3 = 7", lexicon, db_path)
    assert reply.kind == "solved"
    assert reply.route_reason == "equation_detected"
    assert reply.interpreted == "2x + 3 = 7"
    assert reply.text.startswith("I read your equation as: 2x + 3 = 7")
    assert "1. " in reply.text
    assert reply.text.rstrip().endswith("Answer: x = 2.")


def test_no_solution_equation_is_solved_with_answer_line(
    lexicon: Lexicon, db_path: Path
) -> None:
    reply = answer("x + 1 = x + 2", lexicon, db_path)
    assert reply.kind == "solved"
    assert "I read your equation as: x + 1 = x + 2" in reply.text
    assert reply.text.rstrip().endswith("Answer: no solution.")


@pytest.mark.parametrize(
    "error", [InvalidInputError("made up"), RuntimeError("made up")]
)
def test_solver_raising_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
    lexicon: Lexicon,
    db_path: Path,
    error: Exception,
) -> None:
    def boom(text: str) -> Any:
        raise error

    monkeypatch.setattr(tutor, "solve_linear", boom)
    reply = answer("2x + 3 = 7", lexicon, db_path)
    assert reply.kind == "unreadable"
    assert reply.interpreted is None
    assert "equation" in reply.text.lower()
    assert REFUSAL_MESSAGE not in reply.text


def test_explainer_text_comes_after_steps(lexicon: Lexicon, db_path: Path) -> None:
    seen: list[list[dict[str, str]]] = []

    def explainer(messages: list[dict[str, str]]) -> str:
        seen.append(messages)
        return "Made up explanation."

    reply = answer("2x + 3 = 7", lexicon, db_path, explainer)
    assert reply.kind == "solved"
    assert len(seen) == 1
    assert all(set(m) == {"role", "content"} for m in seen[0])
    answer_at = reply.text.index("Answer: x = 2.")
    words_at = reply.text.index("In words:")
    assert answer_at < words_at < reply.text.index("Made up explanation.")


@pytest.mark.parametrize("result", ["raise", "", "   "])
def test_bad_explainer_is_ignored(lexicon: Lexicon, db_path: Path, result: str) -> None:
    def explainer(messages: list[dict[str, str]]) -> str:
        if result == "raise":
            raise RuntimeError("made up model failure")
        return result

    reply = answer("2x + 3 = 7", lexicon, db_path, explainer)
    assert reply.kind == "solved"
    assert "In words:" not in reply.text
    assert "Answer: x = 2." in reply.text


def test_lesson_question_returns_notes_in_id_order(
    monkeypatch: pytest.MonkeyPatch, lexicon: Lexicon, db_path: Path
) -> None:
    _forbid_solver(monkeypatch)
    reply = answer("explain linear equations", lexicon, db_path)
    assert reply.kind == "lesson"
    assert reply.route_reason == "lesson_match"
    assert reply.interpreted is None
    first = reply.text.index(LESSON_CHUNKS[0].text)
    second = reply.text.index(LESSON_CHUNKS[1].text)
    assert first < second


def test_lesson_with_no_retrieved_chunk(tmp_path: Path) -> None:
    # Exercise chunks feed the lexicon but are excluded from search().
    chunk = Chunk(
        "9.1",
        "Made up linear equations",
        "9.1 Made up linear equations > Exercise 1",
        "exercise",
        1,
        1,
        "Solve these linear equations.",
    )
    path = _make_db(tmp_path / "exercise.db", [chunk])
    reply = answer("explain linear equations", build_lexicon(path), path)
    assert reply.kind == "lesson"
    assert "could not find" in reply.text.lower()
    assert chunk.text not in reply.text


def test_reply_is_frozen(lexicon: Lexicon, db_path: Path) -> None:
    reply = answer("what is the capital of France", lexicon, db_path)
    assert isinstance(reply, TutorReply)
    with pytest.raises(AttributeError):
        reply.text = "changed"  # type: ignore[misc]


def test_build_prompt_returns_role_content_dicts() -> None:
    chunks: list[tutor.Chunk] = [{"id": 1, "kind": "explanation", "text": "Made up."}]
    messages = tutor._build_prompt("made up question", None, chunks)
    assert messages
    assert all(set(m) == {"role", "content"} for m in messages)
    assert "Made up." in messages[-1]["content"]


def test_core_has_no_print_and_no_model_imports() -> None:
    tree = ast.parse(TUTOR_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "print"
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
            assert "llama_cpp" not in names and "ollama" not in names
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in ("llama_cpp", "ollama")
