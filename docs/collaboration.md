# Collaboration: who does what

Project: offline-tutor, an offline AI math tutor for Ethiopian Grade 9 students, built as a college-application portfolio demo. Two builders share the repo:
- Tomas (repo owner, GitHub: Kestrel-303)
- Ezana (GitHub: ezanaaregawisudo81)

Each of us must be able to say honestly what he built. The ownership below exists to make that possible and to prevent edit conflicts. This file was committed once directly on main with both of us agreeing; after that, nobody pushes straight to main.

## Ownership (the only source of truth)

Tomas owns:
- Router and refusal rule, and the first eval run on the dev set (src/offline_tutor/router.py, the eval runner, eval/results/)
- Terminal tutor (src/offline_tutor/tutor.py, scripts/tutor.py)
- Existing pipeline: normalizer, layout extraction, chunker, lesson database, equation engine, grader
- Phone work and docs/phone-test.md (only Tomas has the Samsung M13)
- Arranging the teacher or student session
- The 50-question eval run and the error log

Ezana owns:
- Model testing: scripts/compare_models.py, scripts/bench_explain.py (Q4 llama, fixed seed, token counts, a real-prompt benchmark of about 500 tokens), results in docs/model_benchmark.md
- Explanation prompt builder and checker: src/offline_tutor/explain_prompt.py and explain_check.py
- Adversarial questions: eval/adversarial_questions.json (10 questions, committed before the router is evaluated)
- Quiz templates for section 3.1, SymPy-verified: src/offline_tutor/quiz.py
- Progress tracking: src/offline_tutor/progress.py

Both (needs both of us to agree before it merges): docs/collaboration.md, README, decisions.md, CLAUDE.md, requirements-lock.txt, pyproject.toml, the demo video, the write-up (each writes his own section; Tomas records the demo).

If a task crosses ownership, it is labelled CROSS-OWNER, names both people, and goes ahead only after the owner agrees. A reviewer may comment but may not edit the owner's files.

## Fixed interfaces (agree before anyone codes against them)
- Tomas's tutor calls Ezana's build_explain_prompt(question, solution, chunks), which returns chat messages.
- Tomas's tutor calls Ezana's quiz module, which returns a question, the expected answer and verified steps; the existing grader grades it.
- Tomas's tutor calls Ezana's progress module with one record call per graded answer.
Changing a signature needs a written proposal and the other person's agreement.

## Branches and merging
- Branches are named tomas/<topic> and ezana/<topic>. Nobody pushes straight to main. The owner merges after the other person reviews.
- Before any merge: ruff check, ruff format --check, pyright and pytest are all clean.
- Each commit uses its author's own GitHub noreply email.
- Edits to CLAUDE.md, README.md, decisions.md, requirements-lock.txt and pyproject.toml need both of us to agree.
- Environment: pins are in requirements-lock.txt and setup is in docs/environment.md. Never run uv sync, uv run or uv lock; they remove llama-cpp-python.

## Working with Claude Code
- One task per prompt. Every prompt starts with an owner header (OWNER, BRANCH, REVIEWER, MAY TOUCH, MUST NOT TOUCH, MACHINE), and its first step checks the branch and email and stops if the branch prefix does not match the owner.
- Every prompt forbids: uv sync, uv run, uv lock; ollama or model runs inside Claude Code; installs; pushing (the person pushes after checking); edits to protected files; staging with add-all (stage files by name); printing or quoting textbook text. Non-ASCII characters are written as \u escapes. On any failure, stop and say what ran and what was seen.
- Every prompt ends with a "WALKTHROUGH FOR CLAUDE CHAT (by <owner>)": commands and key output, what failed, files changed, what was not tested, what was uncertain.
- Timing and model runs are done by hand by the owner on his own machine with other apps closed, and the report includes that machine's CPU, RAM and available RAM.

## Evaluation integrity
- eval/dev_questions.json is locked. Never edit it. New questions go in new files with new ids.
- Never change an expected label to rescue a result. Each run writes a new results file under eval/results/; an old results file is never overwritten.
- "Router evaluated" means any run of the router or the eval runner against any question file with expected labels, including eval/dev_questions.json. Building the router and running its unit tests on made-up data is not an evaluation.
- Order:
  1. Ezana commits eval/adversarial_questions.json without reading router code or results.
  2. Tomas commits the router and records that commit ID as the freeze.
  3. Tomas runs the dev set and the adversarial set in the same session on the frozen commit; each result goes to a new file under eval/results/.
  4. Tomas does not open the adversarial file before step 3.
  5. Router changes after step 3 are judged on new questions, not on the old sets.

## Honesty
- Claims are tagged CONFIRMED (a builder ran it and saw the output), REPORTED (Claude Code said so) or ESTIMATE.
- Code written with Claude Code is described as such in the README. Each of us describes only his own parts in his applications.
- The app is described as designed for students with little internet. We do not say it helped students unless students actually used it.

## Schedule (targets as of 2026-11-19; Nov 29 and Dec 20 do not move)
- Nov 19: Tomas router and refusal built and dev run recorded; Ezana adversarial set committed and prompt builder done.
- Nov 22: Tomas terminal tutor running; Ezana model benchmark results and Q4 llama.
- Nov 26: Tomas 50-question eval runner, all errors logged; Ezana quiz templates and progress tracking merged.
- Nov 29: checkpoint (is Tier A done and the eval clean? If not, drop Android).
- Dec 20: feature freeze. Early January: submissions.

## Contributions log
Add one row after each finished task. Leave "Reviewed by" blank until the reviewer has checked it. Work done with Claude Code is marked "with Claude Code". This log starts with the first task after the split was agreed; earlier work is in the git history.

| Date | What | Written by | Reviewed by | Commit |
|---|---|---|---|---|
