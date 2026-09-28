# Pipeline changelog

One entry per change to the pipeline (rules, agents, scripts), with the reason. The retro agent reads this file to
judge whether earlier changes helped. Newest first.

## 2026-09-28 · Fixes from the ux-simplification run 1 retro
- Definition of Ready checks "Estimable" (INVEST `E ✓`); a story with `E ✗` is "Not yet", with its reason. Reason:
  US-04 waited for the PO's list of today's functions, yet the package said "5 of 5 ready".
- `dl.py import-prd` logs every 🔵 line in the PRD, not only open §10 rows, so it is asked in Stage 4 or 7. The
  package lint also checks `final-prd.md` for unlogged 🔵. Reason: "profil: 🔵" in the Terms reached the package
  while §9 said no questions were open.
- `validate_output.py --after` checks `coverage-report-1.md` as a coverage report. Reason: it was checked as a
  designer file and printed 16 false problems.
- Coverage check: a Still Open row is `N/A — still open`. Reason: without that value the checker marked rows the PO
  had not answered yet as "accepted by PO".
- Stage 6: a DoD / AC overlap that asks to change a story scenario goes to the story-writer (`revise`), one about a
  DoD item to the packager. Reason: the US-04 × DoD-02 overlap went to the packager twice, which may not edit stories.
- Designer `apply`: a §10 row the PO answered in part is split at once. Reason: a half-decided row stayed open until
  the closing review and cost an extra PO question (DL-011).

## 2026-09-28 · Czech output, smaller small packages, fewer forced findings and PO questions
- Language: `dl.py start` detects Czech (diacritics) or takes `--lang cs|en`; every prompt says
  `Language: …`; all content is written in that language while ids, field labels, script-read headings and Gherkin
  keywords stay English. Script-written text (question options, package headings, readiness, PO decisions, slices)
  is translated. Reason: the PO's company requirements are in Czech.
- Small tier: `final-prd.md` 220 → 180 lines, `user-stories.md` 120 → 90, `package-summary.md` 40 → 30. When every
  story is ready, the package states it in one line instead of the ✓ table. Reason: an 88-word requirement gave a
  220-line package. 160 was the PO's first target, but run 2's package measured ~183 lines even with 90-line
  stories, because terms, DoD, PO decisions and questions are copied verbatim.
- Re-runs: `dl.py start` says whether the requirement changed; "at least one NEW finding per dimension" applies only
  to a new or changed requirement. Reason: run 2 (unchanged requirement) had to raise 7 new findings on a PRD
  already debated, adding 17 log rows and 7 PO questions.
- DoD / AC overlaps left after the coverage recheck are fixed by the packager (`dod-fix`), never asked as PO
  questions. Reason: run 2's last three PO questions were DoD duplicates.
- `validate_output.py --hook --auto` for a project-level SubagentStop hook (role from `agent_type`), so agents fix
  their own output inside the same turn; the orchestrator's `--after` check stays as the fallback.

## 2026-09-28 · Fixes from the advanced-filters test runs (retros of run 1 and run 2, timing review)
- Output check run by the orchestrator after every agent (`validate_output.py --after <role> <files>`, one fix round
  by message to the same agent, then `--record`). Reason: the Stop hooks in the agent files never ran in the VS Code
  extension (no `output-retries.json`, empty warnings log), so files went over budget unnoticed in both runs.
  The read/write guard now also runs from a project-level PreToolUse hook in `.claude/settings.json`
  (`guard.py --auto`, role taken from the payload's `agent_type`); verified in VS Code with a test agent.
- Decision-log rows get a Name (`DL-007 do-not-eat-blocks-matches`): the analyst names its findings, script-made rows
  are named from their text, older logs gain the column on the next write, and names cannot change afterwards.
  Question chips show a ≤ 12-character topic (`Header:` in each question block) instead of the id. Reason: the PO
  asked for names that say which part a row is about.
- Wording the PO chooses survives: `dl.py decide` stores the chosen option with its consequence line; the lint checks
  that quoted PO wording is in the PRD and that stories quote messages exactly as the PRD does; in Stage 7 the
  designer applies decisions before the story-writer. Reason: the empty-deck message (run 1) and the failure
  message (run 2) were reworded differently in the PRD and the stories.
- Stage 7 has a `dod-apply` step for decisions about the DoD. Reason: run 2's DoD decisions had no step to apply them.
- Coverage: PO decisions that accept something or move it to Later are `N/A — accepted by PO`, not gaps (run 2 asked
  DL-030 twice); the second coverage pass is a `recheck` of what the first flagged (run 2's full second pass found
  3 new "issues" in an unchanged DoD file).
- Package lint: "looks like a Later item" needs 3 shared words that are not everyday ones (US-03 was flagged in both
  runs for sharing "hide recipes").
- Speed (each run was ~27 min of agent time and ~13–28 min waiting for PO answers): the business case is written
  in parallel with the stories; `dl.py assemble` builds `final-prd.md` and the packager writes only
  `package-summary.md` (§0–2), since everything else is copied verbatim (packager assemble took 2–5 min); the
  retro runs in the background after the package is shown (4–5 min). Stage 7's designer-then-stories order adds
  ~40 s back.
- Readability: sentences ≤ 25 words and one item per list line (CLAUDE.md); the summary and business case are
  checked for sentences over 30 words. `run-metrics.md` now counts each line as ending a sentence: Given/When/Then
  lines had been joined into 35–37-word "sentences"; counted properly both packages average 14–15 words, and the
  real problem is a few run-on scope lists.
- `run_metrics.py`: DoD items counted without bold (always 0 before), "package written" time instead of an always
  empty "completed", "left for grooming by the PO" counts only rows the PO left open.

## 2026-09-28 · Ideas from public tools (Spec Kit, OpenSpec, BMAD, pm-skills)
- `context/product-context.md`: product-wide facts kept by the PO by hand (like Spec Kit's constitution / BMAD's
  project context). Starts empty; every agent reads it as confirmed fact; no agent can write it.
- Definition of Ready per story in the package, computed by `dl.py package-parts` (value, testable, nothing open,
  dependencies named, small). Reason: grooming is about readiness; only a DoD existed.
- Stage 1 scans 10 product-level areas (Clear / Partial / Missing, after Spec Kit's clarify taxonomy) before asking.
- Package gains Terms (PRD §5 `### Terms`, ≤ 8) and PO decisions (question → answer). Reason: analysts repeatedly
  flagged undefined words; decisions were only visible as `(PO)` tags. Final-prd budget 200 → 220 / 400 → 430.
- Package lint checks consistency: stories vs story map, Covers ids vs the log, stories that look like Later items.
- Small features no longer get `story-map.md`; every story carries a `Slice:` line and `slices.md` is generated.

## 2026-09-28 · Business context, last questions, scorecard
- Stage 1 asks up to 8 questions and always covers business context (goal, success measure and baseline, why now,
  size/priority). Reason: business cases ended with "value not quantified" and no "why now".
- Stage 7 starts with an uncapped last PO checkpoint: every row still open (including parked minor findings, cap
  overflow, coverage gaps, story and DoD questions) is asked before `final-prd.md` is written; decisions are applied
  to the PRD (designer) and the stories (story-writer `apply` mode). Only PO "Leave for grooming" rows stay open.
- Retro adds a 1–5 scorecard (Understandability, Clarity, Completeness, Testability, Proportion, Product focus) with
  a trend line, and its pipeline section became "Recommendations for the analysis app", each tied to the score it
  should raise. `dl.py scores` keeps the history in `groomed/scorecard.csv`; `run-metrics.md` adds readability numbers.
- Designer may read `user-stories.md` (options mode needs the story text for story questions).

## 2026-09-28 · Enforcement and tests (from the best-practice review)
- Guard pinned to the active feature and run (`groomed/.active-run.json`); `*` no longer crosses folders.
  Reason: agents could read other features, archived runs and older runs.
- `scripts/dl.py` does all orchestrator bookkeeping; every log write is validated and rolled back if invalid. The
  decision-log hook also runs after Bash. Reason: the orchestrator had edited the log by shell, bypassing the check.
- `scripts/validate_output.py` as a Stop hook on every agent: format contracts and size budgets, one retry, then a
  warning log. Package lint at Stage 7. Reason: budgets were reported, not enforced (stories at 141/120 lines).
- Caps: 12 PO checkpoint questions per run; minor closing-round findings go to the package as "accept or Later"
  instead of being asked live; one output retry per agent.
- Budgets live in `scripts/budgets.json` only; a test checks CLAUDE.md states the same numbers.
- Models set per agent: analyst, designer, prd-drafter, story-writer on `opus`; packager, coverage-checker, retro
  on `sonnet` (cheaper; watch package quality in the next retros).
- `tests/` (unittest) and `evals/README.md` with `scripts/eval_check.py`.
- Persona checksums verified at Stage 0; run state records `completed` and `po_questions`.
- Scenarios asserting different rules may not be merged to save lines.

## 2026-09-28 · Retro of advanced-recipe-filters (first run)
- Designer `apply` follows a decision through to related messages and definitions.
- Open PRD §10 questions, story 🔵 questions and leftover vague criteria become decision-log rows.
- Leftover DoD separation issues get one packager `Only: definition-of-done.md` pass.
- Metric-only rows may be covered by a DoD item (`COVERED (DoD)`).
- "Other" answers that point to another source are confirmed claim by claim.
