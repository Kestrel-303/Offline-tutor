# Model benchmark: explain prompt

Status: harness built and tested with a fake model only. No real model has
been run yet. No numbers below are measured until Ezana fills them in.

## Purpose

Measure how fast each candidate model (about 1-1.5B parameters, Q4 GGUF)
answers a realistic tutor prompt: a system instruction, section 3.1 lesson
chunks, a stored worked solution, and a student question. This is a speed
and memory benchmark, not an accuracy benchmark.

## Method

Script: `scripts/bench_explain.py`. Results are written to
`results/bench_explain_<YYYYMMDD-HHMMSS>.json` (gitignored, never overwritten).

Example:

```
python scripts/bench_explain.py --threads 4 --model qwen-q4=models/<file>.gguf
```

Settings (proposed by Ezana and Claude chat, not yet validated):

| setting | proposed value |
|---|---|
| counted runs per model | 5 (plus 1 warm-up, not counted) |
| seed | 1234 (same for every run) |
| temperature | 0.0 |
| max tokens | 150 |
| n_ctx | 2048 |
| threads | required, set by hand (no default) |
| target prompt tokens | 500 |
| tolerance | 50 |

- Prompt: built with `build_explain_prompt(question, solution, chunks)`. Until
  `src/offline_tutor/explain_prompt.py` exists, the script uses a temporary
  stand-in with the same signature. The JSON records which one was used.
- Chunks: section 3.1, kinds explanation and example, in id order, added until
  the prompt (counted with each model's own tokenizer through its chat
  template) is within tolerance of the target. If the target can't be
  reached, the JSON says so. Filler text is never added.
- Each run re-evaluates the full prompt (the prompt cache is reset), so time
  to first token includes prompt processing.
- Recorded per model: load time, prompt tokens, completion tokens, time to
  first token, total time, tokens/second (completion tokens / (total - TTFT)),
  peak process working set, available RAM before load, GGUF file type, and
  whether all counted runs gave identical output (by sha256).
- The results don't store any lesson text or answer text. They hold only
  chunk ids, token counts, answer lengths and hashes.

## Machine (fill in by hand)

| field | value |
|---|---|
| CPU model | |
| RAM | |
| available RAM at start | |
| date | |
| Chrome, Edge, VS Code, Claude Code closed (yes/no) | |
| llama-cpp-python version | |
| threads used | |

## Results

| model | file_type | prompt tokens (target hit) | load s | TTFT s median (min-max) | total s median (min-max) | tok/s median (min-max) | completion tokens | peak MB | identical outputs |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |

## Caveats

- Few runs (5 counted) on one machine. The spread is shown as min-max, which is
  not a confidence interval.
- One laptop only. These numbers don't predict phone speed; the phone numbers
  go in `docs/phone-test.md`.
- Check the quantization. The file name and label can be wrong, so confirm
  that the recorded GGUF `general.file_type` is a Q4 type. The script warns
  when a label says q4 but the file isn't Q4.
- Peak memory is the peak for the whole process. If several models run in one
  invocation, later models include earlier peaks. Run one model per
  invocation for clean memory numbers.
- Prompt token counts can differ between models because each model has its
  own tokenizer and chat template, so the chunk ids used can differ too.
- These are not accuracy results. Speed says nothing about whether an
  explanation is correct or faithful to the lesson.
