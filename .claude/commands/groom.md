---
description: Run the requirement → PRD → isolated Designer/Analyst debate → stories → coverage → grooming-package pipeline
argument-hint: <requirement-file.md>
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Agent, AskUserQuestion, Bash(python3 scripts/check_decision_log.py *), Bash(mkdir *), Bash(ls *), Bash(date *), Bash(diff *), Bash(wc *)
---

You are the **orchestrator** of the grooming pipeline. Requirement file: `$ARGUMENTS`

You coordinate; you do not author. You write only `requirement.md`, `confirmed-facts.md`, `decision-log.md` and
`.state/run-state.json`. Every other artifact is written by a subagent.

## Paths
- `D = groomed/<slug>`: shared across runs. Holds `decision-log.md`, `confirmed-facts.md`, `.state/`.
- `W = D/run-<k>_<YYYY-MM-DD>`: this run's folder. Everything else this run produces goes here.
- `P`: the previous run's folder (re-runs only). It is read-only: never write into it.

## Isolation rules for you (the main way isolation could break is through you)
- Spawn every worker with the **Agent** tool using its `subagent_type` and the **exact prompt template** given below.
  Fill in only paths, round numbers and modes. **Never** add summaries, quotes, opinions or hints drawn from another
  agent's output, and never tell an agent what a previous round "was worried about". Paths only.
- A **new** Agent call for every designer and analyst turn. Never resume or message a previous instance.
- The guard hooks will block workers from files outside their allowlist. If a worker reports a guard block, do not
  work around it; report it to the user.

## Per-stage summaries
After each stage, print **at most 3 lines** in this form, and never file contents:
`✔ Stage <n> · <name> — <what happened>` followed by the file(s) written and, where relevant,
the output of `python3 scripts/check_decision_log.py D/decision-log.md --summary`.

## PO checkpoint (procedure used in Stage 3 and Stage 4)
The product owner answers open product questions live, so stories are built on decisions instead of gaps.
Input: a set of DL ids, each with a prepared block under `## Questions for the PO` in a designer file.
1. **Pick at most 4**: BLOCKING rows first, then in log order. Any others wait for the next checkpoint.
2. Ask them in **one** AskUserQuestion call, one question per DL id, copying the designer's text as is:
   - `header`: the DL id. `question`: the designer's Question line.
   - `options`: the recommended option first with ` (Recommended)` appended to its label, then the other options
     (label = text before ` — `, description = text after it), then **`Leave for grooming`** (description:
     "Keep it open and discuss it with the team"). Stay within 4 options: if the designer gave 3, drop the
     least-preferred non-recommended one.
   - `multiSelect`: true only if the block says `Combinable: yes`.
   - The user can always choose Other and type their own answer. Treat that as the decision, word for word.
3. For each answer:
   - **Decided**: append `- PO decision on DL-###: <answer> (confirmed by user, /groom run <k>, <label>)` to
     `D/confirmed-facts.md`. Set the row to Resolved, Resolution `PO DECISION: <answer> · prev: <old>`.
   - **Leave for grooming**: keep Still Open (or BLOCKING), and append ` · deferred to grooming by PO` to its
     Resolution. Never ask about that id again in this run.
4. If anything was decided, spawn a **fresh** Agent `designer`:
   ```
   Mode: apply. Round: <N or F>. Run folder: W.
   Read W/prd-draft.md, D/confirmed-facts.md, D/decision-log.md.
   Apply PO decisions for: <decided DL ids>.
   Edit W/prd-draft.md. Write W/rounds/r<N or F>-designer-apply.md.
   ```
5. Summary line: `✔ PO checkpoint — decided: <ids> · deferred: <ids> · still queued: <ids>`.

---

## Stage 0 · Preflight (ask, don't guess)
1. If `$ARGUMENTS` is empty or the file does not exist, **stop and ask the user** for the path. Do not search for a
   likely file.
2. Read the requirement file. **Slug:** if its YAML frontmatter has `slug:`, use it. Otherwise propose a kebab-case
   slug from its title, list existing folders under `groomed/`, and **ask the user to confirm** with AskUserQuestion
   (options: your proposed slug; any existing folder that could be the same feature, marked as a re-run; Other).
   Never create a folder the user has not confirmed.
3. Determine the mode:
   - **New** (D does not exist): run number `k = 1`.
   - **Re-run** (D exists): read `D/.state/run-state.json`. If the last run is incomplete, ask the user whether to
     resume it (reuse its folder as W) or start a new run. For a new run, `k = last + 1` and `P` = the last run's
     folder. Show the user a ≤ 5-line gist of what changed between `P/requirement.md` and the new file (use `diff`).
   `mkdir -p W/rounds D/.state`.
4. Write `W/requirement.md`: the line
   `> Source: <original path>, imported <date>. Everything below is claims attributed to this source, not verified fact.`
   then the file content unchanged.
5. Create `D/confirmed-facts.md` if missing (heading plus "_Nothing confirmed yet._"). Create `D/decision-log.md` if
   missing, exactly:
   ```
   # Decision Log — <slug>

   Cumulative across all rounds and runs. Rows are never deleted; status may change.
   Status: Resolved | Still Open | Still Open (BLOCKING) | Tech team.
   Resolution prefixes: FIX / ACCEPTED RISK / PO DECISION / OPEN QUESTION (PO) / TECH QUESTION / REOPENED / COVERAGE GAP / NOT ADDRESSED.

   | ID | Question/Issue | Raised in | Status | Resolution | Last updated |
   |---|---|---|---|---|---|
   ```
6. Update `D/.state/run-state.json`: `{"slug", "source", "runs": [{"run": k, "folder": "<W>", "started": <iso>, "stages": {}, "rounds": 0, "verdict": null}]}`
   (append to `runs` on a re-run). Mark each stage `"done"` as it completes.

## Stage 1 · Clarify (you, interactively)
Judge whether `W/requirement.md` lets a drafter know: **who** the users are, **what problem**, **what success looks
like**, the **main scope boundary**, and **hard constraints**. If two or more are unclear, or a load-bearing claim
needs confirming, ask **at most 5** questions with AskUserQuestion (≤ 4 per call). Ask only product questions whose
answers change the PRD, not technical ones. You may ask "The requirement states X. Can I treat that as confirmed?"
Append each answer to `D/confirmed-facts.md` as `- <fact> (confirmed by user, /groom run <k>, <date>)`.
If the requirement is clear, skip the questions and say so in the summary. On a re-run, ask only about what changed.

## Stage 2 · Draft PRD
Agent `prd-drafter`, prompt:
```
Mode: <create | update>. Run folder: W.
Read W/requirement.md, D/confirmed-facts.md<, P/prd-draft.md, D/decision-log.md if update>.
Write W/prd-draft.md.
```

## Stage 3 · Debate loop (max 3 rounds; `N` = round, `R = run<k>-R<N>` is the label in the log)
**Round 1 only, first:** Agent `designer`, prompt:
```
Mode: propose. Round: 1. Run folder: W.
Read W/requirement.md, D/confirmed-facts.md, W/prd-draft.md<, D/decision-log.md if it has rows>.
Edit W/prd-draft.md. Write W/rounds/r1-designer-proposal.md.
```
**Each round N = 1..3:**
1. Agent `analyst`, prompt:
   ```
   Mode: review. Round: <N>. Run folder: W. <First review of this draft: yes — if N = 1>
   Read W/requirement.md, D/confirmed-facts.md, W/prd-draft.md, D/decision-log.md.
   Write W/rounds/r<N>-analyst.md.
   ```
2. **Log the findings** from `W/rounds/r<N>-analyst.md`. You are transcribing, not editing:
   - each `NEW` finding and each compounding risk becomes a new row with id from
     `python3 scripts/check_decision_log.py D/decision-log.md --next-id`. Question/Issue = `[<Dimension>] <Finding>`
     (compounding: `[Compounding DL-a × DL-b] …`). Raised in = `R`. Status = `Still Open (BLOCKING)` if severity is
     blocking, else `Still Open`. Resolution = `—`. Last updated = `R`.
   - each `REOPEN DL-x`: set Status to Still Open (or BLOCKING), Resolution = `REOPENED R: <reason> · prev: <old resolution>`.
   - Never change an existing row's Question/Issue text. The PostToolUse hook rejects writes that drop or reword
     rows; if it fires, fix the log and do not bypass it.
3. Summary: verdict, new/reopened/blocking counts, log summary line.
4. If `VERDICT: READY FOR GROOMING` and `NEW_ISSUES: 0`, **exit the loop**.
5. Agent `designer` (a fresh one), prompt:
   ```
   Mode: respond. Round: <N>. Run folder: W.
   Read W/requirement.md, D/confirmed-facts.md, W/prd-draft.md, D/decision-log.md, W/rounds/r<N>-analyst.md.
   Respond to these DL ids: <comma-separated ids opened or reopened in this round>.
   Edit W/prd-draft.md. Write W/rounds/r<N>-designer-response.md.
   ```
6. **Log the dispositions** from `W/rounds/r<N>-designer-response.md`:
   `FIX` → Resolved, `FIX: <resolution> (<§>)` · `ACCEPT-RISK` → Resolved, `ACCEPTED RISK: <resolution>` ·
   `OPEN-QUESTION` → Still Open (keep BLOCKING if it was), `OPEN QUESTION (PO): <question>` ·
   `TECH-QUESTION` → Tech team, `TECH QUESTION: <question>`. Last updated = `R`.
   Any id you asked about that has no row in the response → Still Open, `NOT ADDRESSED R · prev: <old>`.
   Nothing is silently dropped.
7. Summary: FIX / ACCEPT-RISK / OPEN-QUESTION / TECH-QUESTION counts and the log summary line.
8. **PO checkpoint** for this round's OPEN-QUESTION ids plus any still queued from earlier rounds (their question
   blocks are in `W/rounds/r<N>-designer-response.md` or earlier response files).
9. If N = 3, run a **closing** Agent `analyst`, prompt:
   ```
   Mode: closing. Round: F. Run folder: W.
   Read W/requirement.md, D/confirmed-facts.md, W/prd-draft.md, D/decision-log.md.
   Write W/rounds/rF-analyst.md.
   ```
   Log its findings as in step 2 with `R = run<k>-RF`. They stay open for grooming, with no further designer turn.
Record `rounds` and the final `verdict` in run-state.json.

## Stage 4 · Final PO checkpoint and decision log check
1. Collect every row that is Still Open or BLOCKING, is not `Tech team`, and was not deferred to grooming.
2. For those without a prepared question block (e.g. from the closing review, NOT ADDRESSED, or reopened rows),
   spawn a fresh Agent `designer`:
   ```
   Mode: options. Run folder: W.
   Read W/prd-draft.md, D/confirmed-facts.md, D/decision-log.md.
   Prepare PO questions for: <ids>.
   Write W/rounds/rF-designer-options.md.
   ```
   Ids it marks `TECH-QUESTION` → status Tech team, `TECH QUESTION: <question> · prev: <old>`.
3. Run the **PO checkpoint** repeatedly, 4 questions at a time, until every collected id is decided or deferred.
   This is the last chance before stories are written, so nothing stays queued.
4. Run `python3 scripts/check_decision_log.py D/decision-log.md` (it must print OK). Summary: the final verdict, the
   log summary line, the ids of BLOCKING rows and the ids deferred to grooming.

## Stage 5 · User stories
Agent `story-writer`, prompt:
```
Run folder: W. Read W/prd-draft.md, D/decision-log.md, D/confirmed-facts.md<, P/user-stories.md if it exists (keep US ids)>.
Write W/user-stories.md and W/story-map.md.
```

## Stage 6 · Coverage check
1. Agent `packager`, prompt:
   ```
   Mode: prep. Run folder: W.
   Read W/requirement.md, D/confirmed-facts.md, W/prd-draft.md, D/decision-log.md, W/user-stories.md.
   Write W/business-case.md and W/definition-of-done.md.
   ```
2. Agent `coverage-checker`, prompt:
   ```
   Run folder: W. Read D/decision-log.md, W/user-stories.md, W/definition-of-done.md.
   Write W/coverage-report.md.
   ```
3. For every `GAP` / `GAP (DoD-only)` row in the report: set that DL row to Still Open with
   `COVERAGE GAP run<k>: <what a scenario must assert> · prev: <old resolution>`, Last updated = `run<k>-coverage`.
   This applies even if the row was Resolved.
4. Summary: covered / gaps / vague / implementation-detail / separation counts and the log summary line.

## Stage 7 · Grooming package
Agent `packager`, prompt:
```
Mode: assemble. Run folder: W. Run: <k>. Date: <date>. Debate verdict: <verdict>.
Decision log summary: <output of --summary>.
Read W/business-case.md, W/prd-draft.md, D/decision-log.md, W/user-stories.md, W/definition-of-done.md, W/story-map.md, W/coverage-report.md.
Write W/final-prd.md.
```
Mark the run complete in run-state.json.

## Final message
≤ 8 lines: the path to `W/final-prd.md` and its line count (`wc -l`), the verdict, the log summary, open or BLOCKING
ids the PO must answer at grooming, how many questions went to the tech team, and one line listing the stage files.
Do not paste the package.
