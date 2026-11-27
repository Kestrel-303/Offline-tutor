"""Build chat messages that ask a small local model to explain a verified solution.

Fixed interface (docs/collaboration.md): build_explain_prompt(question, solution,
chunks). The model only explains steps SymPy already verified; it never does math.
Pure: no I/O, no model, no randomness, inputs are not mutated.
"""

from typing import TypedDict

from offline_tutor.equations import Solution


class PromptChunk(TypedDict):
    id: int
    kind: str
    text: str


SYSTEM_PROMPT = (
    "You are a patient Grade 9 maths tutor. "
    "Explain in simple English. "
    "Use ONLY the verified steps and the lesson notes given to you. "
    "Never change the answer and never do your own calculation. "
    "If something is not in the notes or the steps, say you cannot help with it. "
    "Keep it short. Do not use markdown headings."
)


def _answer_in_words(solution: Solution) -> str:
    if solution.outcome == "unique":
        return (
            f"{solution.variable} = {solution.answer} "
            "(the equation has exactly one solution)"
        )
    if solution.outcome == "no_solution":
        return "The equation has no solution."
    return "The equation is true for every number, so every number is a solution."


def build_explain_prompt(
    question: str, solution: Solution, chunks: list[PromptChunk]
) -> list[dict[str, str]]:
    lines = [
        f"Student's question: {question}",
        "",
        f"Equation as interpreted: {solution.interpreted}",
        "",
        "Verified steps:",
    ]
    lines.extend(f"{i}. {step}" for i, step in enumerate(solution.steps, start=1))
    lines.extend(["", f"Verified answer: {_answer_in_words(solution)}"])
    if chunks:
        lines.extend(["", "Lesson notes:"])
        for chunk in chunks:
            lines.append(f"[chunk {chunk['id']}, {chunk['kind']}]")
            lines.append(chunk["text"])
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]
