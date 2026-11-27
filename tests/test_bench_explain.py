"""Tests for scripts/bench_explain.py using a fake model only.

No real model is loaded. The temporary database uses the real schema with
made-up chunk texts.
"""

import json
import subprocess
import sys
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path

import pytest
from bench_explain import (
    QUESTION,
    BenchSettings,
    Message,
    main,
    quant_warning,
    select_chunks,
)

from offline_tutor.equations import solve_linear
from offline_tutor.explain_prompt import PromptChunk, build_explain_prompt
from offline_tutor.lesson_db import create_db

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
MARKER = "zzfakechunkmarker"
ANSWER_MARKER = "zzfakeanswermarker"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5)


class FakeModel:
    """Counts whitespace words as tokens; streams a fixed made-up answer."""

    def __init__(self, file_type: int | None = 15) -> None:
        self._file_type = file_type
        self.stream_calls = 0
        self.seeds: list[int] = []

    def count_prompt_tokens(self, messages: list[Message]) -> int:
        return sum(len(m["content"].split()) for m in messages)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def stream_chat(
        self, messages: list[Message], *, max_tokens: int, temperature: float, seed: int
    ) -> Iterator[str]:
        self.stream_calls += 1
        self.seeds.append(seed)
        yield from [f"{ANSWER_MARKER} ", "subtract ", "then ", "divide."]

    def file_type(self) -> int | None:
        return self._file_type


class Factory:
    def __init__(self, file_type: int | None = 15) -> None:
        self.file_type = file_type
        self.models: list[FakeModel] = []

    def __call__(self, path: str, settings: BenchSettings) -> FakeModel:
        model = FakeModel(self.file_type)
        self.models.append(model)
        return model


def base_tokens() -> int:
    """Fake-token count of the prompt with no lesson chunks."""
    messages = build_explain_prompt(QUESTION, solve_linear(QUESTION), [])
    return FakeModel().count_prompt_tokens(messages)


def fake_chunks(n: int, words: int) -> list[PromptChunk]:
    text = " ".join([MARKER] * words)
    return [{"id": i + 1, "kind": "explanation", "text": text} for i in range(n)]


def make_db(path: Path, words: int = 100) -> Path:
    conn = create_db(path)
    rows = [
        ("3.1", "explanation"),
        ("3.1", "exercise"),  # must be skipped
        ("3.2", "example"),  # wrong section, must be skipped
        ("3.1", "example"),
        ("3.1", "example"),
    ]
    text = " ".join([MARKER] * words)
    with conn:
        for section, kind in rows:
            conn.execute(
                "INSERT INTO chunks (section, section_title, heading, kind,"
                " page_start, page_end, text, char_count)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (section, "Fake title", "Fake heading", kind, 1, 1, text, len(text)),
            )
    conn.close()
    return path


def run_main(
    tmp_path: Path,
    factory: Factory,
    extra: Sequence[str] = (),
    now: datetime = FIXED_NOW,
    labels: Sequence[str] = ("fake-q4",),
) -> tuple[int, Path]:
    db = tmp_path / "lessons.db"
    if not db.exists():
        make_db(db)
    results = tmp_path / "results"
    argv = ["--db", str(db), "--threads", "2", "--runs", "3", *extra]
    for label in labels:
        argv += ["--model", f"{label}=models/fake.gguf"]
    code = main(argv, model_factory=factory, results_dir=results, now=lambda: now)
    return code, results / f"bench_explain_{now:%Y%m%d-%H%M%S}.json"


def test_import_does_not_import_llama_cpp() -> None:
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import bench_explain; "
        "sys.exit(1 if 'llama_cpp' in sys.modules else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(SCRIPTS)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_chunk_selection_stops_within_tolerance() -> None:
    base = base_tokens()
    sel = select_chunks(
        FakeModel(), build_explain_prompt, fake_chunks(6, 100), base + 300, 50
    )
    assert sel.target_reached
    assert sel.chunk_ids == [1, 2, 3]
    assert abs(sel.prompt_tokens - (base + 300)) <= 50


def test_unreachable_target_is_recorded_not_padded() -> None:
    base = base_tokens()
    chunks = fake_chunks(2, 100)
    sel = select_chunks(FakeModel(), build_explain_prompt, chunks, base + 1000, 50)
    assert not sel.target_reached
    assert sel.chunk_ids == [1, 2]
    # Exactly the real chunks, no filler.
    full = build_explain_prompt(QUESTION, solve_linear(QUESTION), chunks)
    assert sel.prompt_tokens == FakeModel().count_prompt_tokens(full)
    assert "not reachable" in sel.note


def test_overshooting_target_is_recorded() -> None:
    base = base_tokens()
    sel = select_chunks(
        FakeModel(), build_explain_prompt, fake_chunks(2, 500), base + 100, 50
    )
    assert not sel.target_reached
    assert sel.chunk_ids == [1]
    assert "not reachable" in sel.note


def test_db_selection_uses_only_section_kinds_in_id_order(tmp_path: Path) -> None:
    code, out = run_main(tmp_path, Factory(), ["--target-prompt-tokens", "100000"])
    assert code == 0
    record = json.loads(out.read_text(encoding="utf-8"))
    model = record["models"][0]
    assert model["chunk_ids"] == [1, 4, 5]
    assert model["target_reached"] is False


def test_warmup_run_is_not_counted(tmp_path: Path) -> None:
    factory = Factory()
    code, out = run_main(tmp_path, factory)
    assert code == 0
    assert factory.models[0].stream_calls == 3 + 1
    model = json.loads(out.read_text(encoding="utf-8"))["models"][0]
    assert model["counted_runs"] == 3
    assert len(model["runs"]) == 3
    assert model["warmup_runs"] == 1
    assert model["identical_outputs"] is True


def test_same_seed_gives_same_recorded_settings(tmp_path: Path) -> None:
    f1, f2 = Factory(), Factory()
    _, out1 = run_main(tmp_path, f1, ["--seed", "99"])
    _, out2 = run_main(
        tmp_path, f2, ["--seed", "99"], now=datetime(2026, 1, 2, 3, 4, 6)
    )
    s1 = json.loads(out1.read_text(encoding="utf-8"))["settings"]
    s2 = json.loads(out2.read_text(encoding="utf-8"))["settings"]
    assert s1 == s2
    assert s1["seed"] == 99
    assert set(f1.models[0].seeds) == {99}


def test_q4_warning_fires_for_q8_file_type() -> None:
    assert quant_warning("qwen-q4", 7) is not None
    assert quant_warning("Qwen-Q4_K_M", 7) is not None


def test_q4_warning_silent_for_q4_file_type() -> None:
    assert quant_warning("qwen-q4", 15) is None
    assert quant_warning("qwen-q4", 2) is None
    assert quant_warning("qwen-q8", 7) is None


def test_q4_warning_recorded_in_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out = run_main(tmp_path, Factory(file_type=7))
    model = json.loads(out.read_text(encoding="utf-8"))["models"][0]
    assert model["file_type"] == 7
    assert model["file_type_name"] == "Q8_0"
    assert model["quant_warning"]
    assert "WARNING" in capsys.readouterr().err


def test_json_contains_no_chunk_or_answer_text(tmp_path: Path) -> None:
    _, out = run_main(tmp_path, Factory())
    raw = out.read_text(encoding="utf-8")
    assert MARKER not in raw
    assert ANSWER_MARKER not in raw
    run = json.loads(raw)["models"][0]["runs"][0]
    assert set(run) >= {"answer_chars", "answer_sha256"}
    assert len(run["answer_sha256"]) == 64


def test_existing_output_file_is_never_overwritten(tmp_path: Path) -> None:
    out = tmp_path / "results" / f"bench_explain_{FIXED_NOW:%Y%m%d-%H%M%S}.json"
    out.parent.mkdir()
    out.write_text("old results", encoding="utf-8")
    factory = Factory()
    code, _ = run_main(tmp_path, factory)
    assert code == 1
    assert out.read_text(encoding="utf-8") == "old results"
    assert factory.models == []  # stopped before loading any model


def test_threads_is_required(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--model", "a=b.gguf"], model_factory=Factory(), results_dir=tmp_path)
    assert exc.value.code == 2
