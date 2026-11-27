"""Run the frozen router over labelled question files and record the results.

For each --questions file this writes a new pair under eval/results/:
router_<stem>_<YYYYMMDD-HHMMSS>.json (per-question detail) and .md (summary).
Existing results files are never overwritten.

Before anything is routed it aborts unless: the working tree is clean, the
freeze commit exists, nothing under src/ changed between the freeze commit
and HEAD, and every question file uses only the fields and labels of
eval/dev_questions.json.

Only the router runs. No retrieval and no language model; llama_cpp and
ollama are never imported. Prints counts and file paths only, never
question text.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from offline_tutor.router import (  # noqa: E402
    MIN_ANCHOR_LENGTH,
    MIN_COVERAGE,
    Lexicon,
    build_lexicon,
    route,
)

DEFAULT_DB = ROOT / "data" / "lessons.db"
RESULTS_DIRNAME = Path("eval") / "results"

# Taken from eval/dev_questions.json (38 questions, sha256 9f75c3f5...) before
# any run. Anything else aborts.
REQUIRED_FIELDS = frozenset(("id", "question", "label"))
ALLOWED_FIELDS = REQUIRED_FIELDS | {"section", "source", "note", "previous_label"}
LABEL_FIELDS = ("label", "previous_label")
ALLOWED_LABELS = frozenset(("in_scope", "refuse"))
ACCEPT_ROUTES = frozenset(("solve_equation", "explain_lesson"))

GitFn = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class EvalAbort(Exception):
    """A precondition failed; nothing was routed or written."""


def make_git(repo: Path) -> GitFn:
    def git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=False
        )

    return git


def check_git(git: GitFn, freeze_commit: str) -> tuple[str, str]:
    """Return (freeze hash, HEAD hash) or raise EvalAbort."""
    status = git(["status", "--short"])
    if status.returncode != 0:
        raise EvalAbort(f"git status failed: {status.stderr.strip()}")
    if status.stdout.strip():
        raise EvalAbort("working tree is not clean (git status --short not empty)")

    if not freeze_commit or freeze_commit.startswith("-"):
        raise EvalAbort(f"invalid freeze commit: {freeze_commit!r}")
    freeze = git(["rev-parse", "--verify", "--quiet", f"{freeze_commit}^{{commit}}"])
    if freeze.returncode != 0:
        raise EvalAbort(f"freeze commit not found: {freeze_commit}")
    head = git(["rev-parse", "--verify", "HEAD"])
    if head.returncode != 0:
        raise EvalAbort("HEAD not found")
    freeze_hash, head_hash = freeze.stdout.strip(), head.stdout.strip()

    diff = git(["diff", "--quiet", freeze_hash, head_hash, "--", "src/"])
    if diff.returncode == 1:
        raise EvalAbort(f"src/ changed since freeze commit {freeze_hash}")
    if diff.returncode != 0:
        raise EvalAbort(f"git diff failed: {diff.stderr.strip()}")
    return freeze_hash, head_hash


@dataclass(frozen=True)
class QuestionFile:
    path: Path
    sha256: str
    questions: list[dict[str, str]]


def load_questions(path: Path) -> QuestionFile:
    """Read and validate one question file, or raise EvalAbort."""
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise EvalAbort(f"{path}: cannot read ({e.strerror})") from None
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise EvalAbort(f"{path}: not valid JSON ({e})") from None
    if not isinstance(data, list) or not data:
        raise EvalAbort(f"{path}: top level must be a non-empty list")

    ids: set[str] = set()
    for i, q in enumerate(data):
        where = f"{path}: item {i}"
        if not isinstance(q, dict):
            raise EvalAbort(f"{where}: not an object")
        missing = REQUIRED_FIELDS - q.keys()
        if missing:
            raise EvalAbort(f"{where}: missing fields {sorted(missing)}")
        unknown = q.keys() - ALLOWED_FIELDS
        if unknown:
            raise EvalAbort(f"{where}: unknown fields {sorted(unknown)}")
        for key, value in q.items():
            if not isinstance(value, str):
                raise EvalAbort(f"{where}: field {key!r} is not a string")
        for key in LABEL_FIELDS:
            if key in q and q[key] not in ALLOWED_LABELS:
                raise EvalAbort(f"{where}: unknown {key} {q[key]!r}")
        if q["id"] in ids:
            raise EvalAbort(f"{where}: duplicate id {q['id']!r}")
        ids.add(q["id"])
    return QuestionFile(path, hashlib.sha256(raw).hexdigest(), data)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(questions: list[dict[str, str]], lexicon: Lexicon) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for q in questions:
        d = route(q["question"], lexicon)
        accepted = d.route in ACCEPT_ROUTES
        correct = accepted if q["label"] == "in_scope" else d.route == "refuse"
        rows.append(
            {
                "id": q["id"],
                "question": q["question"],
                "label": q["label"],
                "route": d.route,
                "reason": d.reason,
                "coverage": d.coverage,
                "matched": list(d.matched),
                "unmatched": list(d.unmatched),
                "banned_hits": list(d.banned_hits),
                "anchor_hits": list(d.anchor_hits),
                "equation_label": d.equation_label,
                "correct": correct,
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = Counter(r["label"] for r in rows)
    return {
        "total": len(rows),
        "correct": sum(r["correct"] for r in rows),
        "in_scope": labels["in_scope"],
        "refuse": labels["refuse"],
        # in_scope question refused / refuse question accepted
        "false_refusals": sum(
            r["label"] == "in_scope" and r["route"] == "refuse" for r in rows
        ),
        "false_accepts": sum(
            r["label"] == "refuse" and r["route"] != "refuse" for r in rows
        ),
        "reason_counts": dict(sorted(Counter(r["reason"] for r in rows).items())),
        "reason_counts_by_label": {
            label: dict(
                sorted(
                    Counter(r["reason"] for r in rows if r["label"] == label).items()
                )
            )
            for label in sorted(labels)
        },
    }


def render_md(record: dict[str, Any]) -> str:
    """Short summary. Lists wrong ids, never question text."""
    s = record["summary"]
    lines = [
        f"# Router eval: {record['question_file']}",
        "",
        f"- Run at: {record['run_at']}",
        f"- Freeze commit: {record['freeze_commit']}",
        f"- HEAD: {record['head_commit']}",
        f"- Question file sha256: {record['question_file_sha256']}",
        f"- Lessons DB sha256: {record['db_sha256']}",
        f"- MIN_COVERAGE: {record['min_coverage']}, "
        f"MIN_ANCHOR_LENGTH: {record['min_anchor_length']}",
        "",
        f"Correct: {s['correct']} / {s['total']} "
        f"({s['in_scope']} in_scope, {s['refuse']} refuse)",
        "",
        f"- False refusals (in_scope routed to refuse): {s['false_refusals']}",
        f"- False accepts (refuse routed to an answer): {s['false_accepts']}",
        "",
        "| Reason | Count |",
        "|---|---|",
        *(f"| {k} | {v} |" for k, v in s["reason_counts"].items()),
        "",
        "Wrong (id, label, route, reason):",
        "",
    ]
    wrong = [r for r in record["results"] if not r["correct"]]
    lines += [
        f"- {r['id']}: {r['label']} -> {r['route']} ({r['reason']})" for r in wrong
    ] or ["- none"]
    return "\n".join(lines) + "\n"


def output_paths(results_dir: Path, path: Path, stamp: str) -> tuple[Path, Path]:
    base = f"router_{path.stem}_{stamp}"
    return results_dir / f"{base}.json", results_dir / f"{base}.md"


def run(
    question_paths: Sequence[Path],
    freeze_commit: str,
    db_path: Path = DEFAULT_DB,
    *,
    repo: Path = ROOT,
    git: GitFn | None = None,
    now: datetime | None = None,
) -> list[tuple[Path, Path]]:
    """Check, route and write one results pair per file. Returns the pairs."""
    if not question_paths:
        raise EvalAbort("no question files given")
    freeze_hash, head_hash = check_git(git or make_git(repo), freeze_commit)
    files = [load_questions(p) for p in question_paths]

    stems = [f.path.stem for f in files]
    if len(set(stems)) != len(stems):
        raise EvalAbort("two question files share a file stem")
    moment = now or datetime.now()
    stamp = moment.strftime("%Y%m%d-%H%M%S")
    results_dir = repo / RESULTS_DIRNAME
    pairs = [output_paths(results_dir, f.path, stamp) for f in files]
    for pair in pairs:
        for out in pair:
            if out.exists():
                raise EvalAbort(f"results file already exists: {out}")
    if not db_path.is_file():
        raise EvalAbort(f"lessons DB not found: {db_path}")

    db_sha = file_sha256(db_path)
    lexicon = build_lexicon(db_path)  # read-only, once for all files
    results_dir.mkdir(parents=True, exist_ok=True)

    for f, (json_path, md_path) in zip(files, pairs, strict=True):
        rows = evaluate(f.questions, lexicon)
        record = {
            "question_file": f.path.name,
            "question_file_sha256": f.sha256,
            "run_at": moment.isoformat(timespec="seconds"),
            "freeze_commit": freeze_hash,
            "head_commit": head_hash,
            "db_sha256": db_sha,
            "min_coverage": MIN_COVERAGE,
            "min_anchor_length": MIN_ANCHOR_LENGTH,
            "summary": summarize(rows),
            "results": rows,
        }
        # "x": exclusive create, never overwrite an existing results file.
        with json_path.open("x", encoding="utf-8") as out:
            json.dump(record, out, indent=2, ensure_ascii=True)
            out.write("\n")
        with md_path.open("x", encoding="utf-8") as out:
            out.write(render_md(record))
    return pairs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the frozen router over labelled question files."
    )
    parser.add_argument(
        "--questions", type=Path, action="append", required=True, metavar="PATH"
    )
    parser.add_argument("--freeze-commit", required=True, metavar="HASH")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, metavar="PATH")
    args = parser.parse_args(argv)
    try:
        pairs = run(args.questions, args.freeze_commit, args.db)
    except EvalAbort as e:
        print(f"ABORT: {e}", file=sys.stderr)
        return 2
    for json_path, md_path in pairs:
        summary = json.loads(json_path.read_text(encoding="utf-8"))["summary"]
        print(
            f"{json_path.name}: {summary['correct']}/{summary['total']} correct, "
            f"{summary['false_refusals']} false refusals, "
            f"{summary['false_accepts']} false accepts"
        )
        print(f"  {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
