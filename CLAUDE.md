# CLAUDE.md

## Project
Offline AI math tutor for Ethiopian Grade 9 students. Solo developer. Current scope: linear equations only, English only, built from Ethiopian Grade 9 math textbooks (text-based PDFs kept locally in `data/`, never committed).
 
Goal: a working demo for a college application (regular decision, deadline about early January 2027), not a production app. Do not build accounts, sync, or distribution tooling.
 
## Hard constraints
- Must work fully offline. No network calls in app code.
- Test device: Samsung M13 with 6 GB RAM. 4 GB Android is the target but is unverified; never claim 4 GB support until it is tested on a real 4 GB phone. Also a Windows laptop. Model must be roughly 1-1.5B parameters, Q4 GGUF.
- Reply time target: first token under 10 seconds and a full short answer (about 100 tokens) under about 15 seconds on the phone (proposed, not yet confirmed by the builder). Record measured numbers in `docs/phone-test.md`.
- The tutor answers only from retrieved lesson text. If retrieval finds nothing above the score threshold, refuse with "I can't help with that" without calling the model.
- Never use the language model to check math answers or do arithmetic. Use code (SymPy). The model only explains stored, verified solutions.
- Quizzes come from templates with SymPy-verified solutions. The model never generates quiz answers.
- Do not commit textbook PDFs, model files, or databases.
## Stack
Python 3.12, uv, SQLite (FTS5), llama-cpp-python, SymPy, PyMuPDF (Tesseract only if PDFs are scanned), pytest, Ruff, Pyright. Later: Kotlin + Android Studio (NDK, CMake), or Termux if the experiment works.
 
## Working rules
- Make small changes, one task at a time. Ask before large restructuring.
- Every feature comes with tests. Grader tests must cover equivalent answers (for example `x=4`, `4=x`, `8/2`, `x = 4.0`) and wrong answers.
- Store grader test cases as JSON (input, expected result) in `tests/grader_cases.json` so a Kotlin port can reuse them.
- Never change an eval question or its expected answer to make it pass.
- Run ruff, pyright, and pytest before saying a task is done.
- Do not claim something works unless it was run. Say what was and was not tested.
- Explain trade-offs briefly. Be honest about uncertainty.
- Keep dependencies minimal; they must be able to run on a phone later.
- Environment is Windows with PowerShell.
- Never run `ollama pull`, `ollama run` or other large downloads. Stop on network errors and report; no retry loops.
- Never run `uv sync` without asking (it removes llama-cpp-python and pymupdf).
- Do not run benchmarks or timing tests; the builder runs them with other apps closed.
- Write non-ASCII characters in code as `\u` escapes.
- `scripts/` is for dev tools. The no-network-calls rule applies to `src/` (app code); `scripts/compare_models.py` calling localhost Ollama is a dev-time exception.
- Do not edit CLAUDE.md, README.md or decisions.md unless asked.
## Phase 1 is done when
1. A model answers a linear-equation question in the terminal.
2. It retrieves the right lesson chunk from SQLite and answers only from it.
3. It refuses off-topic questions.
4. SymPy correctly checks at least 20 sample answers.
5. The 50-question eval has been run (30 in-scope, 10 off-topic, 10 adversarial) and every error is logged.
6. Phone measurements for the M13 are in `docs/phone-test.md`.
## Decisions so far
- No fine-tuning. Use retrieval over textbook sections.
- SQLite instead of PostgreSQL (the app runs on a phone, no server).
- No cloud AI in the app for now. Cloud AI may be used only while building, to draft content that is then human-reviewed.
- Amharic, voice, math keyboard, proactive calling, and device-to-device sync are out of scope. Local reminder notifications may come later.
- One student per device, no accounts.
- Delivery in tiers: A is a Windows demo, B is Android without the model, C is the model on the phone. A is the commitment; B and C are stretch.
## Open questions
- Which models perform best on linear equations (Qwen2.5 1.5B, Llama 3.2 1B, Gemma 3 1B, later Bonsai and Gemma 4)?
- Which Grade 9 unit counts as "linear equations"? Does it span more than one unit?
- Does Termux run the Python tutor on the M13 (Android route without a Kotlin rewrite)?
- What are the textbook licensing terms for distribution?
