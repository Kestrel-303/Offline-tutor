"""Smoke test: load a GGUF model with llama-cpp-python and time one answer.

Dev tool only. Runs fully offline.

Usage:
    python scripts/llama_smoke_test.py models/qwen2.5-1.5b-instruct-q4_k_m.gguf
"""

import sys
import time
from typing import Any, cast

from llama_cpp import Llama

N_THREADS = 4  # Physical cores on the dev laptop (i7-8665U).
PROMPT = "Solve 3x + 5 = 20. Show steps. Plain text only, no LaTeX."
MAX_TOKENS = 200


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/llama_smoke_test.py <model.gguf>", file=sys.stderr)
        return 1

    start = time.perf_counter()
    llm = Llama(model_path=sys.argv[1], n_ctx=2048, n_threads=N_THREADS, verbose=False)
    load_s = time.perf_counter() - start

    gen_start = time.perf_counter()
    first_token_s: float | None = None
    chunks = 0
    parts: list[str] = []
    stream = llm.create_chat_completion(
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=MAX_TOKENS,
        stream=True,
    )
    for chunk in cast(Any, stream):
        content = chunk["choices"][0]["delta"].get("content")
        if not content:
            continue
        if first_token_s is None:
            first_token_s = time.perf_counter() - gen_start
        chunks += 1
        parts.append(content)
        print(content, end="", flush=True)
    total_s = time.perf_counter() - gen_start

    answer = "".join(parts)
    tokens = len(llm.tokenize(answer.encode("utf-8"), add_bos=False)) or chunks
    print("\n")
    print(f"load time:           {load_s:.2f} s")
    ttft = "n/a" if first_token_s is None else f"{first_token_s:.2f} s"
    print(f"time to first token: {ttft}")
    print(f"total gen time:      {total_s:.2f} s")
    print(f"approx tokens/sec:   {tokens / total_s:.2f} ({tokens} tokens)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
