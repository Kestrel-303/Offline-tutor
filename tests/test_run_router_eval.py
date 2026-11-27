"""Tests for eval/run_router_eval.py. All questions and lesson strings are made up.

Every test uses a temporary git repo and temporary files; the real repo,
eval/dev_questions.json and eval/results/ are never touched.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest

from offline_tutor.chunk import Chunk
from offline_tutor.lesson_db import create_db, insert_chunks

RUNNER = Path(__file__).resolve().parents[1] / "eval" / "run_router_eval.py"
NOW = datetime(2026, 1, 2, 3, 4, 5)
STAMP = "20260102-030405"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_router_eval", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


rre = _load_runner()


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A clean temporary repo with src/ and results/ ignored, like the real one."""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    _git(root, "init", "--quiet")
    (root / ".gitignore").write_text("results/\n", encoding="utf-8")
    (root / "src" / "router.py").write_text("X = 1\n", encoding="utf-8")
    _commit_all(root, "freeze")
    return root


@pytest.fixture
def freeze(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "lessons.db"
    conn = create_db(path)
    insert_chunks(
        conn,
        [
            Chunk(
                "9.1",
                "Zorp",
                "Solving zorp equations",
                "text",
                1,
                1,
                "Solve the zorp equation by flarging both sides.",
            )
        ],
    )
    conn.close()
    return path


# Correct accept, false refusal, correct refuse, false accept.
FIXTURE = [
    {"id": "t1", "question": "How do I solve a zorp equation?", "label": "in_scope"},
    {"id": "t2", "question": "What is photosynthesis?", "label": "in_scope"},
    {"id": "t3", "question": "What is the capital of Mars?", "label": "refuse"},
    {
        "id": "t4",
        "question": "Solve the zorp equation",
        "label": "refuse",
        "section": "9.1",
        "note": "made up",
    },
]


def _questions(tmp_path: Path, name: str, items: list[dict[str, str]]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(items), encoding="utf-8")
    return path


def _results(repo: Path) -> list[str]:
    results = repo / "eval" / "results"
    return sorted(p.name for p in results.iterdir()) if results.exists() else []


def test_counts_on_tiny_fixture(
    tmp_path: Path, repo: Path, freeze: str, db: Path
) -> None:
    q = _questions(tmp_path, "tiny.json", FIXTURE)

    [(json_path, md_path)] = rre.run([q], freeze, db, repo=repo, now=NOW)

    assert json_path.name == f"router_tiny_{STAMP}.json"
    assert md_path.name == f"router_tiny_{STAMP}.md"
    record = json.loads(json_path.read_text(encoding="utf-8"))
    s = record["summary"]
    assert (s["total"], s["correct"]) == (4, 2)
    assert (s["false_refusals"], s["false_accepts"]) == (1, 1)
    assert s["reason_counts"] == {"lesson_match": 2, "no_anchor_term": 2}
    by_id = {r["id"]: r for r in record["results"]}
    assert [by_id[i]["correct"] for i in ("t1", "t2", "t3", "t4")] == [
        True,
        False,
        True,
        False,
    ]
    assert set(by_id["t1"]) == {
        "id",
        "question",
        "label",
        "route",
        "reason",
        "coverage",
        "matched",
        "unmatched",
        "banned_hits",
        "anchor_hits",
        "equation_label",
        "correct",
    }
    assert record["freeze_commit"] == freeze
    assert record["head_commit"] == freeze
    assert record["min_coverage"] == rre.MIN_COVERAGE
    assert record["min_anchor_length"] == rre.MIN_ANCHOR_LENGTH
    assert record["question_file_sha256"] == rre.file_sha256(q)
    assert record["run_at"] == "2026-01-02T03:04:05"
    md = md_path.read_text(encoding="utf-8")
    assert "False refusals (in_scope routed to refuse): 1" in md
    assert "t2: in_scope -> refuse (no_anchor_term)" in md
    assert "photosynthesis" not in md  # no question text in the summary


def test_two_files_give_two_pairs(
    tmp_path: Path, repo: Path, freeze: str, db: Path
) -> None:
    a = _questions(tmp_path, "a.json", FIXTURE[:2])
    b = _questions(tmp_path, "b.json", FIXTURE[2:])

    pairs = rre.run([a, b], freeze, db, repo=repo, now=NOW)

    assert len(pairs) == 2
    assert _results(repo) == [
        f"router_a_{STAMP}.json",
        f"router_a_{STAMP}.md",
        f"router_b_{STAMP}.json",
        f"router_b_{STAMP}.md",
    ]
    totals = [
        json.loads(p.read_text(encoding="utf-8"))["summary"]["total"] for p, _ in pairs
    ]
    assert totals == [2, 2]


def test_dirty_tree_aborts(tmp_path: Path, repo: Path, freeze: str, db: Path) -> None:
    (repo / "stray.txt").write_text("x", encoding="utf-8")
    q = _questions(tmp_path, "q.json", FIXTURE)

    with pytest.raises(rre.EvalAbort, match="not clean"):
        rre.run([q], freeze, db, repo=repo, now=NOW)
    assert _results(repo) == []


def test_missing_freeze_commit_aborts(tmp_path: Path, repo: Path, db: Path) -> None:
    q = _questions(tmp_path, "q.json", FIXTURE)

    with pytest.raises(rre.EvalAbort, match="freeze commit not found"):
        rre.run([q], "0" * 40, db, repo=repo, now=NOW)
    assert _results(repo) == []


def test_src_change_since_freeze_aborts(
    tmp_path: Path, repo: Path, freeze: str, db: Path
) -> None:
    (repo / "src" / "router.py").write_text("X = 2\n", encoding="utf-8")
    _commit_all(repo, "change router after freeze")
    q = _questions(tmp_path, "q.json", FIXTURE)

    with pytest.raises(rre.EvalAbort, match="src/ changed"):
        rre.run([q], freeze, db, repo=repo, now=NOW)
    assert _results(repo) == []


def test_change_outside_src_is_allowed(
    tmp_path: Path, repo: Path, freeze: str, db: Path
) -> None:
    (repo / "notes.md").write_text("x", encoding="utf-8")
    head = _commit_all(repo, "docs only")
    q = _questions(tmp_path, "q.json", FIXTURE)

    [(json_path, _)] = rre.run([q], freeze, db, repo=repo, now=NOW)

    assert json.loads(json_path.read_text(encoding="utf-8"))["head_commit"] == head


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "u1", "question": "Solve zorp", "label": "maybe"},
        {
            "id": "u1",
            "question": "Solve zorp",
            "label": "refuse",
            "previous_label": "x",
        },
    ],
)
def test_unknown_label_aborts(
    tmp_path: Path, repo: Path, freeze: str, db: Path, bad: dict[str, str]
) -> None:
    good = _questions(tmp_path, "good.json", FIXTURE)
    q = _questions(tmp_path, "q.json", [*FIXTURE[:2], bad])

    with pytest.raises(rre.EvalAbort, match="unknown"):
        rre.run([good, q], freeze, db, repo=repo, now=NOW)
    assert _results(repo) == []  # nothing written, not even for the good file


def test_unknown_field_aborts(
    tmp_path: Path, repo: Path, freeze: str, db: Path
) -> None:
    bad = {"id": "u1", "question": "Solve zorp", "label": "refuse", "answer": "4"}
    q = _questions(tmp_path, "q.json", [bad])

    with pytest.raises(rre.EvalAbort, match="unknown fields"):
        rre.run([q], freeze, db, repo=repo, now=NOW)


def test_existing_results_file_is_not_overwritten(
    tmp_path: Path, repo: Path, freeze: str, db: Path
) -> None:
    results = repo / "eval" / "results"
    results.mkdir(parents=True)
    existing = results / f"router_q_{STAMP}.json"
    existing.write_text("keep", encoding="utf-8")
    q = _questions(tmp_path, "q.json", FIXTURE)

    with pytest.raises(rre.EvalAbort, match="already exists"):
        rre.run([q], freeze, db, repo=repo, now=NOW)

    assert existing.read_text(encoding="utf-8") == "keep"
    assert _results(repo) == [existing.name]


def test_second_run_with_same_stamp_aborts(
    tmp_path: Path, repo: Path, freeze: str, db: Path
) -> None:
    q = _questions(tmp_path, "q.json", FIXTURE)
    [(json_path, _)] = rre.run([q], freeze, db, repo=repo, now=NOW)
    before = json_path.read_bytes()

    with pytest.raises(rre.EvalAbort, match="already exists"):
        rre.run([q], freeze, db, repo=repo, now=NOW)
    assert json_path.read_bytes() == before


def test_no_model_modules_imported() -> None:
    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('r', {str(RUNNER)!r})\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "sys.modules['r'] = m\n"
        "spec.loader.exec_module(m)\n"
        "print('llama_cpp' in sys.modules, 'ollama' in sys.modules)\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False False"
