"""Tests for build_explain_prompt. All questions and lesson texts are made up."""

import copy

from offline_tutor.equations import Solution, solve_linear
from offline_tutor.explain_prompt import Chunk, build_explain_prompt

QUESTION = "How do I solve 2x + 3 = 7?"

CHUNKS: list[Chunk] = [
    {
        "id": 11,
        "kind": "explanation",
        "text": "A made-up note about balancing both sides.",
    },
    {"id": 42, "kind": "example", "text": "A made-up example that subtracts first."},
]


def _solution() -> Solution:
    return solve_linear("2x + 3 = 7")


def _user(messages: list[dict[str, str]]) -> str:
    return messages[1]["content"]


def test_two_messages_system_then_user() -> None:
    messages = build_explain_prompt(QUESTION, _solution(), CHUNKS)
    assert len(messages) == 2
    assert [m["role"] for m in messages] == ["system", "user"]


def test_output_is_list_of_str_dicts() -> None:
    messages = build_explain_prompt(QUESTION, _solution(), CHUNKS)
    assert isinstance(messages, list)
    for m in messages:
        assert isinstance(m, dict)
        assert set(m) == {"role", "content"}
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in m.items())


def test_system_message_sets_the_rules() -> None:
    system = build_explain_prompt(QUESTION, _solution(), CHUNKS)[0]["content"]
    lowered = system.lower()
    assert "grade 9" in lowered
    assert "only" in lowered
    assert "never change the answer" in lowered
    assert "cannot help" in lowered
    assert "#" not in system


def test_user_message_contains_question_equation_steps_answer_in_order() -> None:
    solution = _solution()
    user = _user(build_explain_prompt(QUESTION, solution, CHUNKS))
    positions = [user.index(QUESTION), user.index(solution.interpreted)]
    start = positions[-1]
    for step in solution.steps:
        pos = user.index(step, start)
        positions.append(pos)
        start = pos
    answer_line = f"{solution.variable} = {solution.answer}"
    positions.append(user.index(answer_line, start))
    positions.append(user.index(CHUNKS[0]["text"]))
    assert positions == sorted(positions)


def test_steps_are_numbered() -> None:
    solution = _solution()
    user = _user(build_explain_prompt(QUESTION, solution, CHUNKS))
    for i, step in enumerate(solution.steps, start=1):
        assert f"{i}. {step}" in user


def test_answer_outcome_in_words() -> None:
    user = _user(build_explain_prompt(QUESTION, _solution(), CHUNKS))
    assert "exactly one solution" in user


def test_no_solution_and_identity_outcomes_in_words() -> None:
    none = _user(build_explain_prompt("q", solve_linear("x + 1 = x + 2"), []))
    assert "no solution" in none
    every = _user(build_explain_prompt("q", solve_linear("x + 1 = x + 1"), []))
    assert "every number" in every


def test_chunk_ids_kinds_and_texts_appear() -> None:
    user = _user(build_explain_prompt(QUESTION, _solution(), CHUNKS))
    for chunk in CHUNKS:
        assert f"[chunk {chunk['id']}, {chunk['kind']}]" in user
        assert chunk["text"] in user
    assert user.index(CHUNKS[0]["text"]) < user.index(CHUNKS[1]["text"])


def test_empty_chunks_leaves_out_notes_section() -> None:
    user = _user(build_explain_prompt(QUESTION, _solution(), []))
    assert "Lesson notes" not in user
    assert "[chunk" not in user
    with_notes = _user(build_explain_prompt(QUESTION, _solution(), CHUNKS))
    assert "Lesson notes" in with_notes


def test_deterministic() -> None:
    solution = _solution()
    first = build_explain_prompt(QUESTION, solution, CHUNKS)
    second = build_explain_prompt(QUESTION, solution, CHUNKS)
    assert first == second


def test_inputs_not_changed() -> None:
    solution = _solution()
    chunks = copy.deepcopy(CHUNKS)
    before_chunks = copy.deepcopy(chunks)
    before_solution = copy.deepcopy(solution)
    build_explain_prompt(QUESTION, solution, chunks)
    assert chunks == before_chunks
    assert solution == before_solution
