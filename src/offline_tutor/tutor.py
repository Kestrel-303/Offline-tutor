"""Tutor core: turn one student question into one reply. No user interface.

Safety rule: every question is routed first. solve_linear is called only on
the solve_equation route, and a refusal never reaches the explainer. All
math in a reply comes from the equation engine; an optional explainer (a
language model, later) only adds words after the verified steps.

No language model is imported here. The explainer is passed in by the caller.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

from offline_tutor.equations import Solution, solve_linear
from offline_tutor.lesson_db import SearchResult, search
from offline_tutor.router import REFUSAL_MESSAGE, Lexicon, route

ReplyKind = Literal["refusal", "solved", "lesson", "unreadable"]
Message = dict[str, str]
Explainer = Callable[[list[Message]], str]

UNREADABLE_MESSAGE = (
    "Sorry, I could not read that equation. "
    "Please type just the equation, for example: 2x + 3 = 7"
)
NOT_FOUND_MESSAGE = "I could not find that in the lesson."
EXPLAINER_HEADING = "In words:"


@dataclass(frozen=True)
class TutorReply:
    kind: ReplyKind
    text: str
    route_reason: str
    interpreted: str | None


# Stand-in until Ezana's explain_prompt.py is merged: Chunk and _build_prompt
# are then replaced by an import from offline_tutor.explain_prompt.
class Chunk(TypedDict):
    id: int
    kind: str
    text: str


def _build_prompt(
    question: str, solution: Solution | None, chunks: list[Chunk]
) -> list[Message]:
    parts = [f"Question: {question}"]
    if solution is not None:
        parts.append(f"Equation: {solution.interpreted}")
        parts.append("Verified steps:\n" + "\n".join(solution.steps))
    if chunks:
        parts.append("Lesson notes:\n" + "\n\n".join(c["text"] for c in chunks))
    return [
        {
            "role": "system",
            "content": (
                "You are a Grade 9 math tutor. Explain in simple English using "
                "only the verified steps and lesson notes given. Do not do new "
                "arithmetic and do not change any answer."
            ),
        },
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def _explain(explainer: Explainer | None, messages: list[Message]) -> str | None:
    """Return the explainer's text, or None if absent, failing or empty."""
    if explainer is None:
        return None
    try:
        text = explainer(messages)
    except Exception:
        return None
    if not isinstance(text, str) or not text.strip():
        return None
    return text.strip()


def _answer_line(solution: Solution) -> str | None:
    if solution.outcome == "no_solution":
        return "Answer: no solution."
    if solution.outcome == "identity":
        return "Answer: every number is a solution."
    return None


def _format_solution(solution: Solution) -> str | None:
    """Interpretation, numbered steps, then the answer line; None if unusable."""
    if not solution.steps:
        return None
    if solution.outcome == "unique":
        answers = [s for s in solution.steps if s.startswith("Answer:")]
        if solution.answer is None or len(answers) != 1:
            return None
        answer = answers[0]
    else:
        answer = _answer_line(solution)
        if answer is None:
            return None
    steps = [s for s in solution.steps if s != answer]
    lines = [f"I read your equation as: {solution.interpreted}", ""]
    lines += [f"{n}. {step}" for n, step in enumerate(steps, start=1)]
    lines += ["", answer]
    return "\n".join(lines)


def _retrieve(question: str, db_path: Path) -> list[SearchResult]:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        results = search(conn, question)
    finally:
        conn.close()
    return sorted(results, key=lambda r: r.chunk_id)


def _with_words(text: str, words: str | None) -> str:
    return text if words is None else f"{text}\n\n{EXPLAINER_HEADING}\n{words}"


def answer(
    question: str,
    lexicon: Lexicon,
    db_path: Path,
    explainer: Explainer | None = None,
) -> TutorReply:
    """Route the question, then refuse, solve or show lesson notes."""
    decision = route(question, lexicon)
    reason = decision.reason

    if decision.route == "solve_equation":
        try:
            solution = solve_linear(question)
        except Exception:
            return TutorReply("unreadable", UNREADABLE_MESSAGE, reason, None)
        text = _format_solution(solution)
        if text is None:
            return TutorReply("unreadable", UNREADABLE_MESSAGE, reason, None)
        words = _explain(explainer, _build_prompt(question, solution, []))
        return TutorReply(
            "solved", _with_words(text, words), reason, solution.interpreted
        )

    if decision.route == "explain_lesson":
        results = _retrieve(question, db_path)
        if not results:
            return TutorReply("lesson", NOT_FOUND_MESSAGE, reason, None)
        notes = "\n\n".join(f"{r.heading}\n{r.text}" for r in results)
        chunks: list[Chunk] = [
            {"id": r.chunk_id, "kind": r.kind, "text": r.text} for r in results
        ]
        words = _explain(explainer, _build_prompt(question, None, chunks))
        return TutorReply("lesson", _with_words(notes, words), reason, None)

    return TutorReply("refusal", REFUSAL_MESSAGE, reason, None)
