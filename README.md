# offline-tutor
 
Offline AI math tutor for Ethiopian Grade 9 students, built as a working demo. A small on-device language model explains lessons from the national textbooks, code generates and checks quiz answers, and the app tracks weak topics. No internet required. Starting with linear equations.
 
> **Status:** early prototype (Tier A in progress). Not tested with students. Not ready for classroom use.
 
## Why this exists
 
Many students in rural areas have an Android phone but little or no reliable internet. This project explores whether a small tutor can run entirely on that phone. It is **designed for** that situation. It has not yet been used by students, and claims about impact should wait for real feedback.
 
## Goals
 
- Works fully offline. Test device: 6 GB Samsung M13. A 4 GB Android phone is the target but is **not yet verified**.
- Answers only from the lesson content, and says "I can't help with that" otherwise. If retrieval finds nothing above a score threshold, the app refuses without calling the model.
- Math answers are checked by code (SymPy), never by the language model.
- Quizzes come from templates with SymPy-verified solutions. The model never produces quiz answers.
- Reply speed: first-token target of about 10 seconds. Measured numbers go in `docs/phone-test.md`.
- First version: English, Grade 9 math, linear equations only.
## How it works
 
1. Textbook sections are stored in SQLite and found with full-text search (FTS5).
2. The agent picks a tool: explain a topic, make a quiz, or check an answer.
3. The small model explains the retrieved lesson text. Code does the calculating and grading.
4. Progress is tracked per skill to show weak topics.
## Setup (Windows)
 
```powershell
winget install Python.Python.3.12
winget install astral-sh.uv
winget install Git.Git
winget install Ollama.Ollama
 
git clone <your-repo-url>
cd offline-tutor
uv venv --python 3.12
.venv\Scripts\activate
uv pip install sympy pymupdf pytest ruff pyright
uv pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --index-strategy unsafe-best-match
```
 
Note: `llama-cpp-python` from plain PyPI compiles from source and can fail on Windows without a C++ compiler. The command above uses the prebuilt CPU wheel index instead. If that fails too, install the Visual Studio Build Tools, and record what worked in `docs/`.
 
Setup notes (Windows):
 
- Close and reopen PowerShell after `winget` installs so the new commands are on `PATH`.
- If `.venv\Scripts\activate` is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- On slow connections, set `$env:UV_HTTP_TIMEOUT = "300"` before `uv pip install`.
- A TLS timeout during `ollama pull` usually means: rerun the same command (it resumes).
- Set `$env:PYTHONUTF8 = "1"` to avoid console encoding errors when printing textbook text.
- Do not run plain `uv sync`: it removes `llama-cpp-python` and `pymupdf`, which are installed outside the runtime dependencies.
 
Download models for comparison (Ollama is only used to compare models quickly):
 
```powershell
ollama pull qwen2.5:1.5b
ollama pull llama3.2:1b
ollama pull gemma3:1b
```
 
## Folder layout (planned)
 
```
pyproject.toml  project config (ruff, pyright, pytest, dependency groups)
data/      textbook PDFs and extracted text (not committed; only .gitkeep in the repo)
models/    GGUF model files (not committed; only .gitkeep in the repo)
scripts/   dev tools: model comparison, PDF checks, llama-cpp smoke test
src/       tutor code: retrieval, agent, grader, progress (planned, not created yet)
tests/     pytest tests, including grader_cases.json (input and expected result)
eval/      50-question evaluation set and results (planned, not created yet)
docs/      notes and decisions: pdf_recon.md, later phone-test.md
android/   Android app (Tier B, if time allows)
```
 
## Content and licensing
 
Textbook PDFs and model files are intentionally not in this repository. No textbook content is published in the repo, and demo materials should show at most a short excerpt. Check the content terms of the source textbooks and each model's license before distributing anything.
 
## Roadmap (tiers)
 
- [ ] Tier A: Windows demo: retrieval, refusal, grader, quizzes, 50-question eval, demo video, write-up (target: early December)
- [ ] Tier B: Android version without the model (stored lessons, quizzes, grading, weak topics), or a Termux-based prototype on the phone (stretch; feature freeze Dec 20)
- [ ] Tier C: on-phone model explanations (only if phone measurements allow)
- [ ] Later, not this cycle: Amharic, student trials, Android distribution, 4 GB device verification