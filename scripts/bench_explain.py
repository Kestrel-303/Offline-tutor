"""Benchmark: time a real-shaped explain prompt on one or more GGUF models.

Dev tool only. Runs fully offline. NOT yet run with a real model: the
default settings below are proposed, not measured results.

For each model: load it, pick section 3.1 explanation/example chunks (id
order) until the prompt, measured with that model's own tokenizer, is within
--tolerance of --target-prompt-tokens, then do one warm-up run (not counted)
and --runs counted runs. Results hold chunk ids, token counts and answer
hashes only, never lesson or answer text.

llama_cpp is imported lazily inside llama_factory(), so importing this
module (for tests with a fake model) does not import llama_cpp.

Usage:
    python scripts/bench_explain.py --threads 4 \\
        --model qwen-q4=models/qwen2.5-1.5b-instruct-q4_k_m.gguf
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import sqlite3
import statistics
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from offline_tutor.equations import Solution, solve_linear  # noqa: E402
from offline_tutor.explain_prompt import (  # noqa: E402
    PromptChunk,
    build_explain_prompt,
)

Message = dict[str, str]
PromptBuilder = Callable[[str, Solution, list[PromptChunk]], list[Message]]

SECTION = "3.1"
CHUNK_KINDS = ("explanation", "example")
QUESTION = "Can you explain how to solve 4h + 6 = 0?"
# Made-up worked solution for the benchmark; not taken from the textbook.
WORKED_SOLUTION = (
    "Equation: 4h + 6 = 0\n"
    "Step 1: Subtract 6 from both sides: 4h = -6\n"
    "Step 2: Divide both sides by 4: h = -6/4\n"
    "Step 3: Simplify: h = -3/2"
)
SYSTEM_INSTRUCTION = (
    "You are a math tutor for Grade 9 students. Answer only from the lesson "
    "text given below. Explain the given solution steps in plain text only; "
    "do not use LaTeX. Do not do any arithmetic beyond the given steps."
)

# GGUF general.file_type values (llama.h LLAMA_FTYPE_*), common ones only.
FILE_TYPE_NAMES = {2: "Q4_0", 3: "Q4_1", 7: "Q8_0", 14: "Q4_K_S", 15: "Q4_K_M"}
Q4_FILE_TYPES = frozenset({2, 3, 14, 15})

CLOSE_APPS_REMINDER = (
    "REMINDER: close Chrome, Edge, VS Code and Claude Code before timing."
)


@dataclass(frozen=True)
class BenchSettings:
    db: str
    runs: int
    seed: int
    temperature: float
    max_tokens: int
    n_ctx: int
    threads: int
    target_prompt_tokens: int
    tolerance: int


class BenchModel(Protocol):
    def count_prompt_tokens(self, messages: list[Message]) -> int:
        """Prompt tokens for these chat messages, using the model's tokenizer."""
        ...

    def count_tokens(self, text: str) -> int:
        """Tokens in a piece of generated text."""
        ...

    def stream_chat(
        self, messages: list[Message], *, max_tokens: int, temperature: float, seed: int
    ) -> Iterator[str]:
        """Yield answer text pieces as they are generated (fresh prompt eval)."""
        ...

    def file_type(self) -> int | None:
        """GGUF general.file_type, or None if missing."""
        ...


ModelFactory = Callable[[str, BenchSettings], BenchModel]


def fallback_build_explain_prompt(
    question: str, solution: str, chunks: Sequence[str]
) -> list[Message]:
    """TEMPORARY STAND-IN for offline_tutor.explain_prompt.build_explain_prompt.

    Used only while that module does not exist. Same signature; replace by
    the real function once it is written.
    """
    lesson = "\n\n".join(chunks)
    user = (
        f"Lesson text:\n{lesson}\n\n"
        f"Worked solution:\n{solution}\n\n"
        f"Question: {question}"
    )
    return [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": user},
    ]


def resolve_prompt_builder() -> tuple[PromptBuilder, str]:
    """Return (builder, source name): always the real builder."""
    return build_explain_prompt, "offline_tutor.explain_prompt"


def load_section_chunks(db_path: str | Path) -> list[PromptChunk]:
    """Read id, kind, text of section 3.1 explanation/example chunks, read-only."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        placeholders = ", ".join("?" * len(CHUNK_KINDS))
        rows = conn.execute(
            "SELECT id, kind, text FROM chunks WHERE section = ?"
            f" AND kind IN ({placeholders}) ORDER BY id",
            (SECTION, *CHUNK_KINDS),
        ).fetchall()
    finally:
        conn.close()
    return [{"id": int(r[0]), "kind": str(r[1]), "text": str(r[2])} for r in rows]


@dataclass
class ChunkSelection:
    chunk_ids: list[int]
    messages: list[Message]
    prompt_tokens: int
    target_reached: bool
    note: str


def select_chunks(
    model: BenchModel,
    builder: PromptBuilder,
    chunks: Sequence[PromptChunk],
    target: int,
    tolerance: int,
) -> ChunkSelection:
    """Add chunks in order until prompt tokens are within tolerance of target.

    Never pads. If the target cannot be reached (all chunks still too short,
    or one more chunk overshoots), keeps the candidate closest to the target
    and records target_reached=False with the reason.
    """
    if not chunks:
        raise ValueError(f"no {'/'.join(CHUNK_KINDS)} chunks in section {SECTION}")
    solution = solve_linear(QUESTION)  # SymPy-verified; raises if unsolvable
    best: ChunkSelection | None = None
    for k in range(1, len(chunks) + 1):
        used = list(chunks[:k])
        messages = builder(QUESTION, solution, used)
        tokens = model.count_prompt_tokens(messages)
        candidate = ChunkSelection([c["id"] for c in used], messages, tokens, False, "")
        if best is None or abs(tokens - target) < abs(best.prompt_tokens - target):
            best = candidate
        if abs(tokens - target) <= tolerance:
            candidate.target_reached = True
            candidate.note = "within tolerance"
            return candidate
        if tokens > target + tolerance:
            best.note = (
                f"target not reachable: {k} chunk(s) give {tokens} tokens,"
                f" above {target}+{tolerance}; kept closest candidate"
            )
            return best
    assert best is not None
    best.note = (
        f"target not reachable: all {len(chunks)} chunk(s) give"
        f" {best.prompt_tokens} tokens, below {target}-{tolerance}; not padded"
    )
    return best


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_once(
    model: BenchModel, messages: list[Message], settings: BenchSettings
) -> dict[str, Any]:
    """One timed generation. Returns timings, token count and answer hash."""
    start = time.perf_counter()
    first: float | None = None
    parts: list[str] = []
    for piece in model.stream_chat(
        messages,
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
        seed=settings.seed,
    ):
        if first is None:
            first = time.perf_counter() - start
        parts.append(piece)
    total = time.perf_counter() - start
    answer = "".join(parts)
    completion_tokens = model.count_tokens(answer) if answer else 0
    # Generation time = total time minus time to first token.
    gen_time = None if first is None else total - first
    tps = completion_tokens / gen_time if gen_time else None
    return {
        "time_to_first_token_s": first,
        "total_s": total,
        "completion_tokens": completion_tokens,
        "tokens_per_second": tps,
        "answer_chars": len(answer),
        "answer_sha256": _sha256(answer),
    }


def summarize(values: Sequence[float | int | None]) -> dict[str, float] | None:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    return {"median": statistics.median(nums), "min": min(nums), "max": max(nums)}


def quant_warning(label: str, file_type: int | None) -> str | None:
    """Warning text if the label claims Q4 but the file is not a Q4 type."""
    if "q4" not in label.lower() or file_type in Q4_FILE_TYPES:
        return None
    name = (
        FILE_TYPE_NAMES.get(file_type, "unknown")
        if file_type is not None
        else "missing"
    )
    return (
        f"label {label!r} says q4 but GGUF general.file_type is"
        f" {file_type} ({name}), not a Q4 type"
    )


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def peak_memory_bytes() -> int | None:
    """Peak working set of this process since it started (Windows only)."""
    if sys.platform != "win32":
        return None
    try:
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        ok = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        )
    except OSError:
        return None
    return int(counters.PeakWorkingSetSize) if ok else None


def ram_bytes() -> tuple[int | None, int | None]:
    """(total, available) physical RAM in bytes (Windows only)."""
    if sys.platform != "win32":
        return None, None
    try:
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        ok = ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(status))
    except OSError:
        return None, None
    if not ok:
        return None, None
    return int(status.ullTotalPhys), int(status.ullAvailPhys)


def llama_cpp_version() -> str | None:
    """Installed llama-cpp-python version, read without importing llama_cpp."""
    try:
        return importlib.metadata.version("llama-cpp-python")
    except importlib.metadata.PackageNotFoundError:
        return None


class LlamaBenchModel:
    """BenchModel backed by llama_cpp.Llama. Not covered by tests."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    def count_prompt_tokens(self, messages: list[Message]) -> int:
        # Exact count through the model's own chat template: a 1-token
        # completion reports usage.prompt_tokens. Not timed.
        self._llm.reset()
        result = self._llm.create_chat_completion(
            messages=messages, max_tokens=1, temperature=0.0
        )
        return int(result["usage"]["prompt_tokens"])

    def count_tokens(self, text: str) -> int:
        return len(self._llm.tokenize(text.encode("utf-8"), add_bos=False))

    def stream_chat(
        self, messages: list[Message], *, max_tokens: int, temperature: float, seed: int
    ) -> Iterator[str]:
        # reset() drops the cached prompt prefix so every run evaluates the
        # whole prompt; otherwise later runs would get an unfairly fast TTFT.
        self._llm.reset()
        stream = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
            stream=True,
        )
        for chunk in stream:
            content = chunk["choices"][0]["delta"].get("content")
            if content:
                yield content

    def file_type(self) -> int | None:
        raw = self._llm.metadata.get("general.file_type")
        try:
            return int(raw) if raw is not None else None
        except ValueError:
            return None


def llama_factory(path: str, settings: BenchSettings) -> BenchModel:
    from llama_cpp import Llama

    llm = Llama(
        model_path=path,
        n_ctx=settings.n_ctx,
        n_threads=settings.threads,
        seed=settings.seed,
        verbose=False,
    )
    return LlamaBenchModel(llm)


def bench_model(
    label: str,
    path: str,
    factory: ModelFactory,
    settings: BenchSettings,
    chunks: Sequence[PromptChunk],
    builder: PromptBuilder,
) -> dict[str, Any]:
    _, available_before = ram_bytes()
    start = time.perf_counter()
    model = factory(path, settings)
    load_s = time.perf_counter() - start

    file_type = model.file_type()
    warning = quant_warning(label, file_type)
    if warning:
        print(f"\n!!!!! WARNING: {warning} !!!!!\n", file=sys.stderr)

    selection = select_chunks(
        model, builder, chunks, settings.target_prompt_tokens, settings.tolerance
    )
    run_once(model, selection.messages, settings)  # warm-up, not counted
    runs = [run_once(model, selection.messages, settings) for _ in range(settings.runs)]
    peak = peak_memory_bytes()
    del model
    gc.collect()

    hashes = {r["answer_sha256"] for r in runs}
    return {
        "label": label,
        "path": path,
        "file_type": file_type,
        "file_type_name": FILE_TYPE_NAMES.get(file_type)
        if file_type is not None
        else None,
        "quant_warning": warning,
        "available_ram_before_load_bytes": available_before,
        "load_s": load_s,
        "chunk_ids": selection.chunk_ids,
        "prompt_tokens": selection.prompt_tokens,
        "target_reached": selection.target_reached,
        "chunk_selection_note": selection.note,
        "warmup_runs": 1,
        "counted_runs": len(runs),
        "runs": runs,
        "summary": {
            key: summarize([r[key] for r in runs])
            for key in (
                "time_to_first_token_s",
                "total_s",
                "completion_tokens",
                "tokens_per_second",
            )
        },
        "peak_working_set_bytes": peak,
        "identical_outputs": len(hashes) == 1,
    }


def _fmt(stat: dict[str, float] | None, digits: int = 2) -> str:
    if stat is None:
        return "n/a"
    med, lo, hi = stat["median"], stat["min"], stat["max"]
    return f"{med:.{digits}f} ({lo:.{digits}f}-{hi:.{digits}f})"


def markdown_table(models: Sequence[dict[str, Any]]) -> str:
    lines = [
        "| model | file_type | prompt tok (target hit) | load s | TTFT s med (min-max)"
        " | total s med (min-max) | tok/s med (min-max) | completion tok med"
        " | peak MB | identical |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in models:
        s = m["summary"]
        ftype = f"{m['file_type']} ({m['file_type_name'] or 'unknown'})"
        peak = m["peak_working_set_bytes"]
        peak_mb = "n/a" if peak is None else f"{peak / 2**20:.0f}"
        comp = s["completion_tokens"]
        comp_med = "n/a" if comp is None else f"{comp['median']:.0f}"
        lines.append(
            f"| {m['label']} | {ftype} | {m['prompt_tokens']}"
            f" ({'yes' if m['target_reached'] else 'NO'}) | {m['load_s']:.2f}"
            f" | {_fmt(s['time_to_first_token_s'])} | {_fmt(s['total_s'])}"
            f" | {_fmt(s['tokens_per_second'])} | {comp_med} | {peak_mb}"
            f" | {'yes' if m['identical_outputs'] else 'no'} |"
        )
    return "\n".join(lines)


def parse_model_arg(value: str) -> tuple[str, str]:
    label, sep, path = value.partition("=")
    if not sep or not label or not path:
        raise argparse.ArgumentTypeError(f"expected LABEL=PATH, got {value!r}")
    return label, path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    p.add_argument(
        "--model",
        type=parse_model_arg,
        action="append",
        required=True,
        metavar="LABEL=PATH",
        help="model to benchmark (repeatable)",
    )
    p.add_argument("--db", default="data/lessons.db")
    p.add_argument("--runs", type=int, default=5, help="counted runs per model")
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=150)
    p.add_argument("--n-ctx", type=int, default=2048)
    p.add_argument("--threads", type=int, required=True)
    p.add_argument("--target-prompt-tokens", type=int, default=500)
    p.add_argument("--tolerance", type=int, default=50)
    return p


def main(
    argv: Sequence[str] | None = None,
    *,
    model_factory: ModelFactory = llama_factory,
    results_dir: str | Path = "results",
    now: Callable[[], datetime] = datetime.now,
) -> int:
    args = build_parser().parse_args(argv)
    settings = BenchSettings(
        db=args.db,
        runs=args.runs,
        seed=args.seed,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        n_ctx=args.n_ctx,
        threads=args.threads,
        target_prompt_tokens=args.target_prompt_tokens,
        tolerance=args.tolerance,
    )
    started = now()
    out_dir = Path(results_dir)
    out_path = out_dir / f"bench_explain_{started:%Y%m%d-%H%M%S}.json"
    if out_path.exists():  # fail before loading any model
        print(f"error: {out_path} already exists; not overwriting", file=sys.stderr)
        return 1

    print(CLOSE_APPS_REMINDER)
    builder, builder_source = resolve_prompt_builder()
    print(f"prompt builder: {builder_source}")
    chunks = load_section_chunks(settings.db)
    total_ram, available_ram = ram_bytes()

    models = [
        bench_model(label, path, model_factory, settings, chunks, builder)
        for label, path in args.model
    ]
    record = {
        "timestamp": started.isoformat(timespec="seconds"),
        "status": "proposed settings; not accuracy results",
        "settings": asdict(settings),
        "prompt_builder": builder_source,
        "machine": {
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "total_ram_bytes": total_ram,
            "available_ram_bytes": available_ram,
        },
        "llama_cpp_version": llama_cpp_version(),
        "notes": [
            "peak_working_set_bytes is the process peak since start; with several"
            " models in one invocation, later models include earlier peaks.",
            "tokens_per_second = completion_tokens"
            " / (total_s - time_to_first_token_s).",
            "completion_tokens = answer text re-tokenized without BOS.",
        ],
        "models": models,
    }
    print()
    print(markdown_table(models))
    for m in models:
        if m["quant_warning"]:
            print(f"WARNING: {m['quant_warning']}")
        if not m["target_reached"]:
            print(f"NOTE ({m['label']}): {m['chunk_selection_note']}")

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "x", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    print(f"\nwrote {out_path}")
    print(CLOSE_APPS_REMINDER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
