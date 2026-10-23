# CLAUDE.md

## Project
Offline AI math tutor for Ethiopian high school students. Solo developer. Current scope: linear equations only, English only, built from Ethiopian school textbooks (PDFs kept locally in `data/`, never committed).

## Hard constraints
- Must work fully offline. No network calls in app code.
- Target device: Android phone with 4 GB RAM, plus a Windows laptop. Model must be roughly 1-1.5B parameters, Q4 GGUF.
- Reply time target: 5-10 seconds.
- The tutor answers only from retrieved lesson text. If nothing relevant is found, it says it cannot help with that.
- Never use the language model to check math answers or do arithmetic. Use code (SymPy). The model only explains stored, verified solutions.
- Do not commit textbook PDFs, model files, or databases.

## Stack
Python 3.12, uv, SQLite (FTS5), llama-cpp-python, SymPy, PyMuPDF (Tesseract only if PDFs are scanned), pytest, Ruff, Pyright. Later: Kotlin + Android Studio (NDK, CMake).

## Working rules
- Make small changes, one task at a time. Ask before large restructuring.
- Every feature comes with tests. Grader tests must cover equivalent answers (for example `x=4`, `4=x`, `8/2`) and wrong answers.
- Run ruff, pyright, and pytest before saying a task is done.
- Do not claim something works unless it was run. Say what was and was not tested.
- Explain trade-offs briefly. Be honest about uncertainty.
- Keep dependencies minimal; they must be able to run on a phone later.

## Phase 1 is done when
1. A model answers a linear-equation question in the terminal.
2. It retrieves the right lesson chunk from SQLite and answers only from it.
3. It refuses off-topic questions.
4. SymPy correctly checks at least 20 sample answers.

## Decisions so far
- No fine-tuning. Use retrieval over textbook sections.
- SQLite instead of PostgreSQL (the app runs on a phone, no server).
- No cloud AI in the app for now. Cloud AI may be used only while building, to draft content that is then human-reviewed.
- Amharic, voice, math keyboard, and proactive calling are out of scope for v1. Local reminder notifications may come later.
- One student per device, no accounts.

## Open questions
- Which models perform best on linear equations (Qwen2.5 1.5B, Llama 3.2 1B, Gemma 3 1B, later Bonsai and Gemma 4)?
- Are the textbook PDFs text-based or scanned?
- What are the textbook licensing terms for distribution?
