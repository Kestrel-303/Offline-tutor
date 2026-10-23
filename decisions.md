# offline-tutor: decisions and summary

Last updated: 2026-10-20. Items marked **(recommended)** were suggested by Claude and not yet explicitly confirmed by you. Items marked **(estimate)** are Claude's rough numbers, not measurements.

## 1. Goal
An offline AI tutoring app with an agent feature, built to help real students in the builder's community. A small language model runs on the device itself, so no internet is needed.

## 2. About the builder and setup
- Solo developer, full focus, some coding experience, no mobile app experience.
- Windows laptop. Already installed: VS Code (with Claude extension), PostgreSQL, Docker, Android developer tools.
- Uses Claude Code on the $20 plan for coding (usage limits apply). Uses this Claude Project ("offline-tutor") for consulting and explaining concepts.
- Uses a voice-to-text transcriber, so some words in messages may come out wrong.
- Wants honest evaluations of their understanding, including when it is bad.

## 3. Decisions made by the builder
- **Audience and subject:** school students. First subject is maths (changed from biology). Started as "high school math + science".
- **First unit for development and testing:** linear equations.
- **Offline means fully offline,** including the AI model running on the device.
- **Platforms:** Android phones and desktop (Windows/Mac/Linux).
- **Weakest target device:** 4 GB RAM.
- **Agent features wanted:** explain and chat, generate and grade quizzes, track weaknesses and adapt.
- **Chat stays tied to the lessons** (does not answer outside the lessons).
- **One student per device.**
- **Reply time:** 5-10 seconds is acceptable.
- **Content source:** Ethiopian school textbooks, which the builder has as PDF files (changed from open/OER sources).
- **Languages:** originally English and Amharic.
- **Distribution:** APK shared by SD card or Bluetooth.

## 4. Recommended approach (recommended, pending your confirmation)
- **No fine-tuning.** Use the textbooks as a lesson library with retrieval: split into sections, store in SQLite, find matching sections, and have the model explain only those.
- **Code grades math, never the model.** SymPy checks answers (including equivalent forms such as x=4, 4=x, 8/2). Each question stores a verified worked solution, and the model only explains it.
- **SQLite, not PostgreSQL,** because the app runs on a phone with no server. Docker and PostgreSQL are not needed for this project.
- **Search:** start with SQLite full-text search (FTS5). Add embeddings later only if search quality is poor.
- **Version 1 scope:** English only, linear equations first. Amharic, voice, math keyboard, accounts, and polish come later.
- **No cloud AI inside the app for now.** Optionally use a cloud model only while building (to draft solutions, hints, and translations), always human-reviewed, then bundle the reviewed content.
- **Local reminders later:** phone notifications about due practice, scheduled on-device, instead of Ivy-style proactive voice calls.
- **Model shipped as a separate file** loaded from storage, not inside the APK.
- **Mastery tracking:** simple per-skill counters first; spaced repetition (SM-2 or FSRS) later.

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
| PyMuPDF (Tesseract OCR if scanned) | Extracting textbook text |
| SymPy | Checking math answers |
| pytest, Ruff, Pyright | Tests and code quality |
| Android Studio (NDK, CMake), Kotlin | Later: phone test and Android app |
| Claude Code plugins (quick-gate-python, Code Review; later Android Emulator QA) | Optional helpers |

## 6. Timeline (estimate)
- **Working prototype in 2-3 weeks:** Windows version with a local interface for linear equations, plus a test of the model on a real 4 GB phone. Not ready for students.
  - Week 1: model comparison, lesson chunks in SQLite, answers-only-from-lessons behavior, SymPy grader.
  - Week 2: question templates with worked solutions, agent loop, progress tracking, simple local web interface.
  - Week 3: model on the phone, 50-question test run, trial with 2-3 students.
- **Student-ready offline Android version:** about 7-9 months solo, about 4-5.5 months with Claude Code. Claude Code speeds up coding, not phone testing, content checking, or student trials.
- Using cloud AI only while building might save 1-2 weeks of content work. Adding cloud AI inside the app would add about 4-6 weeks.

## 7. Biggest hurdle and risks
- **Biggest hurdle:** getting a ~1B model to be accurate and fast enough on a 4 GB phone. Only real device testing answers this.
- Small models make arithmetic and reasoning errors, hence code-based grading.
- Math input and equation display on a phone are real UI work.
- Textbook PDFs may be scanned or have broken equations (extra cleanup).
- Textbook and model licensing must be checked before distributing to many students.
- The phone step could take a whole week if new to Android.
- Claude Code cannot see the phone, judge answer quality, or watch students: those parts stay with the builder.

## 8. Reference: Ivy
An Ethiopian solo developer's tutoring project (AWS AIdeas finalist) with a cloud tutor, voice calls, proactive calling, and an offline Android layer. The builder's project matches only its offline layer. Ivy is not to be copied (code, name, branding), but it suggests the idea is feasible. Its claims, including its 10-student pilot, are self-reported.

## 9. Open questions
1. Which grade and book contain linear equations, and are the books in English?
2. Are the PDFs text-based or scanned? How bad are the broken equations?
3. What are the textbook licensing terms for distribution?
4. Which small model performs best on linear equations on the real phone?
5. Does the laptop have at least 8 GB RAM? Which phone model will be used for testing?
6. Which target: 2-3 week prototype, or the full student-ready version?
7. When to bring in Amharic, and how to handle Amharic textbooks?
8. Is an optional online mode worth adding after the offline version works?

## 10. Chats in this Project
- Concepts (explain new ideas), Setup and troubleshooting, Planning, Brainstorm and grill.
- Added: Content and curriculum, Model testing log, Weekly review.
- Later: Android and mobile (phase 4), Student testing and feedback (phase 6).
- Tip: chats do not share context, so keep this file, README.md, and CLAUDE.md as the shared record. End important chats with a three-line summary to add here.

## 11. Next steps
1. Create the GitHub repo (private) and add .gitignore, README.md, CLAUDE.md.
2. Put textbook PDFs in `data/` (not committed).
3. Install the tools and compare the three models on 10 linear-equation questions.
4. Send the linear equations chapter to test PDF extraction.
