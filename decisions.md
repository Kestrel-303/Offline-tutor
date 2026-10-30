# offline-tutor: decisions and summary
 
Last updated: 2026-10-30. Items marked **(recommended)** were suggested by Claude and not yet explicitly confirmed by you. Items marked **(estimate)** are Claude's rough numbers, not measurements.
 
## 1. Goal
An offline AI tutoring app with an agent feature, built to increase educational accessibility for students in low-internet areas. A small language model runs on the device itself, so no internet is needed. The app is for the builder's college application portfolio: it needs to work and be demonstrable, not be production-ready.
 
## 2. About the builder and setup
- Solo developer, some coding experience, no mobile app experience.
- Can work up to 4 hours a day. Plan on about 15-20 productive hours a week, and budget about 100-140 hours total for this project before the application deadline (estimate).
- Windows laptop. Already installed: VS Code (with Claude extension), PostgreSQL, Docker, Android developer tools.
- Test phone: 6 GB Samsung M13.
- Uses Claude Code on the $20 plan for coding (usage limits apply). Uses this Claude Project ("offline-tutor") for consulting and explaining concepts.
- Uses a voice-to-text transcriber, so some words in messages may come out wrong.
- Wants honest evaluations of their understanding, including when it is bad.
## 3. Decisions made by the builder
- **Audience and subject:** Grade 9 students, math. First unit for development and testing: linear equations.
- **Purpose:** portfolio item for college applications (regular decision, this cycle, deadline about early January 2027). Only needs a working demo.
- **Offline means fully offline,** including the AI model running on the device.
- **Platforms:** Android phones and desktop (Windows).
- **Target device floor:** 4 GB RAM (not yet verified; only a 6 GB phone is available for testing).
- **Agent features wanted:** explain and chat, generate and grade quizzes, track weaknesses and adapt.
- **Chat stays tied to the lessons** (does not answer outside the lessons).
- **One student per device.**
- **Reply time:** 5-10 seconds was the original target (see risks about this).
- **Content source:** Ethiopian Grade 9 math textbooks, as text-based PDFs (not scanned).
- **Language:** English first. Amharic is out of scope for this cycle.
- **Distribution:** not needed for the demo. APK sharing by SD card or Bluetooth is a later idea.
## 4. Recommended approach (recommended, pending your confirmation)
- **No fine-tuning.** Use the textbooks as a lesson library with retrieval: split into sections, store in SQLite, find matching sections, and have the model explain only those.
- **Code grades math, never the model.** SymPy checks answers (including equivalent forms such as x=4, 4=x, 8/2). Each question stores a verified worked solution, and the model only explains it.
- **Quizzes from templates.** Parameterized templates (for example `ax + b = c` with controlled number ranges) with SymPy-verified solutions. The model never generates quiz answers.
- **Deterministic refusal.** If retrieval finds nothing above a score threshold, the app says "I can't help with that" without calling the model.
- **Grader cases stored as JSON** (input, expected result) from day one, so a Kotlin port can reuse them.
- **SQLite, not PostgreSQL,** because the app runs on a phone with no server. Docker and PostgreSQL are not needed for this project.
- **Search:** start with SQLite full-text search (FTS5). Add embeddings later only if search quality is poor.
- **No device-to-device sync.** One student per device makes it unnecessary.
- **No cloud AI inside the app for now.** Optionally use a cloud model only while building (to draft solutions, hints, and translations), always human-reviewed, then bundle the reviewed content.
- **Delivery in tiers:**
  - Tier A: Windows demo with retrieval, refusal, grader, quizzes, 50-question eval, demo video, and a one-page write-up. This is the commitment.
  - Tier B: Android version without the model (stored lessons, quizzes, grading, weak topics). Stretch. A Termux-based prototype (running the Python tutor on the phone) is a possible shortcut, still to be tested.
  - Tier C: model running on the phone. Only if phone measurements allow. Unlikely within the deadline.
- **Model shipped as a separate file** loaded from storage, not inside the APK, if the model is on the phone.
- **Mastery tracking:** simple per-skill counters first; spaced repetition later.
- **Wording of claims:** say the app is "designed for" low-internet students. Do not say it "helped students" unless students actually used it.
## 5. Tech stack
| Tool | Purpose |
|---|---|
| Python 3.12, uv | Prototype language and environment |
| Git + GitHub (repo kept private for now) | Version control |
| VS Code + Claude Code | Coding with Claude |
| Ollama | Quickly comparing small models |
| llama-cpp-python | Running the model from code (same engine family as the phone) |
| GGUF models: Qwen2.5 1.5B, Llama 3.2 1B, Gemma 3 1B; later Bonsai 1-bit and Gemma 4 | Tutor "brain", to be compared (the Bonsai and Gemma 4 claims come from a third-party article and are unverified) |
| SQLite (FTS5) | Lessons, questions, progress, search |
| PyMuPDF | Extracting textbook text (Tesseract OCR only if scanned) |
| SymPy | Checking math answers |
| pytest, Ruff, Pyright | Tests and code quality |
| Android Studio (NDK, CMake), Kotlin, or Termux | Android route (Tier B), to be decided after week 1 |
| Claude Code plugins (quick-gate-python, Code Review; later Android Emulator QA) | Optional helpers |
 
## 6. Timeline (estimate, regular decision, about 10 weeks)
Week 1 runs Oct 26 - Nov 1. If you start late, keep the Nov 29 checkpoint and Dec 20 freeze and cut scope instead of moving them.
 
| Week | Dates | Target (done when) |
|---|---|---|
| 1 | Oct 26 - Nov 1 | Done: repo, tooling, laptop timing of qwen2.5:1.5b, PDF recon. **Not done** (moved to week 2): phone measurements, Termux experiment, 10-equation spot-check. |
| 2 | Nov 2-8 | **First:** `docs/phone-test.md` has first-token time (~500-token prompt), tokens/sec, peak RAM, and a 15-minute sustained run on the M13, plus the exact phone chip. Termux experiment done. 10 Grade 9 equations spot-checked against the PDF. **Gate:** if no model gets a usable speed, the model becomes optional. Then: 3-model comparison on 10 questions with a scored table. Retrieval finds the right chunk for 20 in-scope questions and refuses all 10 off-topic questions without calling the model. |
| 3 | Nov 9-15 | SymPy grader passes 20+ JSON cases. Start the verified question bank (about 20 questions). Ask a teacher or 3-5 students for a session now. |
| 4 | Nov 16-22 | Terminal tutor wired together; Phase 1 criteria (CLAUDE.md) pass. |
| 5 | Nov 23-29 | 50-question eval run (30 in-scope, 10 off-topic, 10 adversarial); every error logged. **Checkpoint Nov 29.** |
| 6 | Nov 30 - Dec 6 | Tier A demo video and write-up draft. Buffer week. |
| 7-8 | Dec 7-20 | Tier B Android route (Termux polish, or Kotlin app with lessons, quiz, and grader checked against the JSON tests). **Feature freeze Dec 20.** |
| 9 | Dec 21-27 | Student or teacher session if arranged, final video, README, write-up. Holiday buffer. |
| 10 | Dec 28 - Jan 3 | No new features. Bug fixes only; submit with margin before the earliest deadline. |
 
**Nov 29 checkpoint rule:**
- If Tier A is done and the eval is clean, go for Tier B (or the Termux route).
- If Tier A is not done, drop Android entirely. Polish the desktop demo and report the phone measurements honestly.
**Cut order if you slip:** (1) Android, keeping the phone measurements; (2) student session, using one teacher's feedback instead; (3) quiz variety, weak-topic ranking, UI polish; (4) the model (a stored-explanations tutor is still a working tutor). Do not cut the eval, the grader tests, deterministic refusal, or the phone measurements.
 
Earlier estimates (prototype in 2-3 weeks, 4-5.5 and 7-9 months for a student-ready Android version) are superseded by the plan above.
 
## 7. Biggest hurdle and risks
- **Biggest hurdle:** getting a ~1B model to be accurate and fast enough on a phone. Only real device testing answers this.
- **Reply speed:** on a weak CPU the model may generate only a few tokens per second (guess, not measured). A full explanation could take much longer than 10 seconds. Design for short replies or streaming, and keep quizzes and grading model-free.
- **4 GB is untested.** The M13 has 6 GB. Do not claim 4 GB support until a real 4 GB phone is tested.
- Small models make arithmetic and reasoning errors, hence code-based grading.
- Math input and equation display on a phone are real UI work.
- Text-based PDFs may still have broken or split equations (cleanup needed).
- Textbook and model licensing must be checked before distributing anything.
- First-time Android development is the phase most likely to overrun.
- Applications, essays, school, and test prep compete for the same hours.
- Claude Code usage limits on the $20 plan: save it for Python weeks.
- Student or teacher access takes time to arrange, and consent and privacy for under-18s need a teacher or guardian involved.
- Claude Code cannot see the phone, judge answer quality, or watch students: those parts stay with the builder.
## 8. Reference: Ivy
An Ethiopian solo developer's tutoring project (AWS AIdeas finalist) with a cloud tutor, voice calls, proactive calling, and an offline Android layer. The builder's project matches only its offline layer. Ivy is not to be copied (code, name, branding), but it suggests the idea is feasible. Its claims, including its 10-student pilot, are self-reported.
 
## 9. Open questions
1. Which Grade 9 unit counts as "linear equations"? Does it span more than one unit?
2. Do the target schools accept a link or demo video, or only an essay mention?
3. Can you get a teacher or 3-5 students for a session by week 3?
4. Does Termux run the Python tutor on the M13?
5. What are the textbook licensing terms (for publishing anything beyond a short excerpt)?
6. Which small model performs best on linear equations on the real phone?
7. ~~Does the laptop have at least 8 GB RAM?~~ Answered: 8 GB total; Intel i7-8665U, 4 cores / 8 threads. About 3.7-3.8 GB free only with everything closed; 389-679 MB free with the usual apps open.
8. Can you borrow a real 4 GB phone for a day (needed only before claiming 4 GB support)?
9. Amharic and an optional online mode: out of scope for this cycle.
## 9a. Measurements so far (laptop only, no phone numbers yet)
- **qwen2.5:1.5b via Ollama, laptop, CPU only, warm run, one easy question:** 8.77 s total, 14.5 tokens/s, 126 tokens; 1.2 GB loaded at 4096 context. Single run, not a benchmark.
- **llama3.2:1b and gemma3:1b:** pulled, not yet timed.
- qwen gave LaTeX once when not told otherwise, so always send "plain text only" in the prompt.
- **llama-cpp-python 0.3.36:** imports, but has not generated text yet (`scripts/llama_smoke_test.py` written, not yet run).
 
## 9b. PDF findings (details in `docs/pdf_recon.md`)
- `G9-Mathematics-STB-2023-web.pdf`: 375 pages, text-based (only 4 near-empty pages), no OCR needed.
- Unit 3 "Solving Equations" is PDF pages 116-161. 3.1 (one-variable linear equations) is about 117-119; 3.2 (systems in two variables) about 120-133. Printed page + 11 = PDF page.
- Extraction defects: brackets extracted as Ethiopic letters (U+123A/U+123B); math-italic variable letters; Unicode minus; equations split across lines; repeated unit header and page-number footer; bullets on their own lines.
 
## 9c. Environment versions
Python 3.12.10, uv 0.13.1, git 2.55.0, ruff 0.17.1, pyright 1.1.414, pytest 9.1.1, llama-cpp-python 0.3.36, sympy 1.14.0.
 
## 10. Chats in this Project
- Concepts (explain new ideas), Setup and troubleshooting, Planning, Brainstorm and grill.
- Added: Content and curriculum, Model testing log, Weekly review.
- Later: Android and mobile (Tier B), Student testing and feedback.
- Tip: chats do not share context, so keep this file, README.md, and CLAUDE.md as the shared record. End important chats with a three-line summary to add here.
## 11. Next steps
1. Start of week 2 (Nov 2): phone measurements on the M13, the Termux experiment, and the 10-equation spot-check of the Grade 9 PDF (not done in week 1).
2. Repo already exists with .gitignore, README.md, CLAUDE.md. GitHub privacy (private) is not yet verified: check it on github.com.
3. Grade 9 PDF is in `data/` (not committed).
4. Pick the exact unit scope for linear equations: 3.1 only, or 3.1 + 3.2.
5. Run `scripts/llama_smoke_test.py` once with other apps closed; time llama3.2:1b and gemma3:1b.
6. Check whether your target schools accept a link or video.
 