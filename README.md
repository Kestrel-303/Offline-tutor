# offline-tutor

Offline AI math tutor for Ethiopian high school students. A small on-device language model explains lessons from the national textbooks, generates quizzes, checks answers with code, and tracks weak topics. No internet required. Starting with linear equations.

> **Status:** early prototype (phase 1). Not ready for students.

## Goals

- Works fully offline on a 4 GB RAM Android phone and on a Windows laptop
- Answers only from the lesson content, and says "I can't help with that" otherwise
- Math answers are checked by code (SymPy), never by the language model
- Reply time of about 5-10 seconds
- First version: English, high school math, linear equations only

## How it works

1. Textbook sections are stored in SQLite and found with full-text search.
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
uv venv
.venv\Scripts\activate
uv pip install sympy pytest ruff pyright
```

Download models for comparison:

```powershell
ollama pull qwen2.5:1.5b
ollama pull llama3.2:1b
ollama pull gemma3:1b
```

## Folder layout (planned)

```
data/      textbook PDFs and extracted text (not committed)
models/    GGUF model files (not committed)
src/       tutor code: retrieval, agent, grader, progress
tests/     pytest tests
docs/      notes and decisions
android/   Android app (later phase)
```

## Content and licensing

Textbook PDFs and model files are intentionally not in this repository. Check the content terms of the source textbooks and each model's license before distributing anything.

## Roadmap

- [ ] Phase 1: desktop prototype (model, retrieval, grader)
- [ ] Phase 2: content pipeline and question bank
- [ ] Phase 3: agent logic and progress tracking
- [ ] Phase 4: Android app
- [ ] Phase 5: speed and memory tuning on a real 4 GB phone
- [ ] Phase 6: testing with students
