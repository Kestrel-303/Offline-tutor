# Router error log: Rule 7 freeze run, 2026-11-27 18:54

Offline linear-equations tutor, designed for Grade 9 students with low internet
access. It is a demo; it has never been used by or helped real students.

- Run: 2026-11-27 18:54:23, one session, router design B.
- Freeze commit: 4648109 (46481090a7a3bef3310b8875e04ff099e2f97290).
- head_commit recorded in the results files: bc20622944190e621e8d097646122064400e751e.
- Router settings recorded in the results files: min_coverage 0.6, min_anchor_length 3.
- Source: local, gitignored results files
  `eval/results/router_dev_questions_20261127-185423.json` and
  `eval/results/router_eval_50_questions_20261127-185423.json`.
  No other question file was read for this log.

Tag key:

- CONFIRMED: read directly from the results files listed above.
- REPORTED: stated by the builder, not checked against a file for this log.
- ESTIMATE: analysis or a guess at the cause; not proven by a test.

## Totals (CONFIRMED)

| Set | Correct | False refusals | False accepts |
|---|---|---|---|
| dev (dev_questions.json) | 37/38 | 1 (b05) | 0 |
| eval_50 (eval_50_questions.json) | 42/50 | 7 | 1 (n40) |

eval_50 detail:

- In-scope questions accepted: 25/32.
- Refuse-labelled questions correctly refused: 17/18.

## Wrong answers

Route and reason are what the router returned (CONFIRMED). Question text is copied
from the results files (CONFIRMED). Causes are analysis (ESTIMATE), except b05,
whose cause is the reason recorded in the results file.

| id | label | route / reason got | coverage | question | cause | status |
|---|---|---|---|---|---|---|
| b05 (dev) | in_scope | refuse / low_coverage | 0.4 | explain the substitution method to me like I am a 10 year old? | low_coverage: coverage 0.4 is below min_coverage 0.6 (CONFIRMED, from results file) | fix targeted by 8d9f22f, NOT verified on a clean set |
| n11 | in_scope | refuse / no_anchor_term | 1.0 | x + y = 10, x - y = 4 find x and y | Typed system with no anchor word; rule gap (ESTIMATE) | fix targeted by 8d9f22f, NOT verified on a clean set |
| n13 | in_scope | refuse / no_content_words | null | 2x + 3y = 13, y = x + 1 what are x and y? | Typed system with no anchor word; rule gap (ESTIMATE) | fix targeted by 8d9f22f, NOT verified on a clean set |
| n22 | in_scope | refuse / low_coverage | 0.5 | I solved 4x - 5 = 11 and got x = 3. I did 4x = 6 then divided. Is that right? | Several equations plus chatty words; low_coverage, threshold effect (ESTIMATE) | fix targeted by 8d9f22f, NOT verified on a clean set |
| n23 | in_scope | refuse / no_anchor_term | 0.6 | Why do we change the sign when we move a number to the other side? | Concept question with no anchor; vocabulary gap (ESTIMATE). OPEN: label must be checked by hand against section 3.1 | fix targeted by 8d9f22f, NOT verified on a clean set |
| n25 | in_scope | refuse / no_anchor_term | 0.4 | I got x = 5 for 3x - 4 = 11 but my friend wrote x = 15/3. Are we both right? | Several equations in one message; rule gap (ESTIMATE) | fix targeted by 8d9f22f, NOT verified on a clean set |
| n26 | in_scope | refuse / no_anchor_term | 0.667 | how do u do eqations with x on both sides | Typo hides the anchor; rule gap (ESTIMATE) | fix targeted by 8d9f22f, NOT verified on a clean set |
| n27 | in_scope | refuse / no_anchor_term | 0.143 | can u explain eliminashun in a simple way, im in grade 9 and totaly lost | Typo hides the anchor; rule gap (ESTIMATE) | fix targeted by 8d9f22f, NOT verified on a clean set |
| n40 | refuse | explain_lesson / lesson_match | 1.0 | Solve 3x - 2 < 10 | Inequality sign not detected; false accept; rule gap (ESTIMATE) | fix targeted by 8d9f22f, NOT verified on a clean set |

## Burned for tuning

These ids have been looked at while designing fixes, so they no longer count as
unseen test questions:

- eval_50: n11, n13, n22, n23, n25, n26, n27, n40
- a04, a05, a06 (REPORTED)
- dev: b05

The dev set and eval_50 are re-run only to check for regressions. The router fix
8d9f22f (merged as ea90354) is judged only on a new question set, not on these
two sets.

## Known limits not fixed

- "Solve the equation(s) 2x + 3 = 7" is wrongly refused. (REPORTED)
- "log in and solve 2x + 3 = 7" is refused. This is an untested risk. (REPORTED)
- The solve_linear guard covers only the listed function names. (REPORTED)
