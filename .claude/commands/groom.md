---
description: Run the requirement → PRD → isolated Designer/Analyst debate → stories → coverage → grooming-package → retro pipeline
argument-hint: <requirement-file.md>
disable-model-invocation: true
allowed-tools: Read, Agent, SendMessage, ToolSearch, AskUserQuestion, Bash(python3 scripts/dl.py *), Bash(python3 scripts/check_decision_log.py *), Bash(python3 scripts/run_metrics.py *), Bash(python3 scripts/validate_output.py *), Bash(ls *), Bash(diff *), Bash(wc *)
---

You are the **orchestrator** of the grooming pipeline. Requirement file: `$ARGUMENTS`

You coordinate; you do not author. **All bookkeeping goes through `python3 scripts/dl.py`** (run setup, run state,
confirmed facts, decision log). Never edit `decision-log.md`, `confirmed-facts.md`, `requirement.md` or
`.state/*` yourself, by any tool: `dl.py` validates every log write and rolls back invalid ones, and a hook re-checks
the log after every Bash call. Every other artifact is written by a subagent, except `run-metrics.md`
(`run_metrics.py`). If a `dl.py` command fails, report it to the user; do not work around it.

## Paths
`dl.py start` prints them: `D = groomed/<slug>` (shared across runs: log, facts, `.state/`), `W = D/run-<k>_<date>`
(this run), `P` = the previous run's folder (re-runs only; read-only). `start` also pins the run in
`groomed/.active-run.json`; the guard lets agents touch only that feature and run. `state complete` removes the pin.

## Isolation rules for you (the main way isolation could break is through you)
- Spawn every worker with the **Agent** tool using its `subagent_type` and the **exact prompt template** given below.
  Fill in only paths, round numbers, modes, the size tier and the language. **Every** agent prompt starts with the
  line `Size: <tier>. Language: <Czech | English>.` (the `language:` line of `dl.py start`). **Never** add summaries, quotes, opinions or hints drawn from another agent's output, and never
  tell an agent what a previous round "was worried about". Paths only.
- A **new** Agent call for every designer and analyst turn. Never resume or message a previous instance, except
  for the output check below.
- If a worker reports a guard block, do not work around it; report it to the user.

## Output check (after every agent, including parallel ones)
Some clients do not run the Stop hook in the agent files, so you run the same check yourself (with the
SubagentStop hook in `.claude/settings.json`, agents usually fix their output before you see it, and this is `OK`):
1. `python3 scripts/validate_output.py --after <role> <files it wrote, relative to W>` (e.g. `--after analyst
   rounds/r2-analyst.md`, `--after packager business-case.md`). `OK` → go on.
2. Otherwise send the printed problems, and nothing else, to **the same agent** with SendMessage (load it once with
   ToolSearch `select:SendMessage`): `Fix exactly these problems in <files>, then finish again:` + the lines as printed.
   This is the only time you message an earlier agent; the text is script output, never another agent's words.
3. When it finishes, run the command again with `--record`. Whatever it still prints goes to
   `D/.state/validation-warnings.log`; mention it in the stage summary. One fix round only.
Do this before any `dl.py` command that reads the agent's file.

## Per-stage summaries
`dl.py` prints decision-log ids with their names (`DL-007 do-not-eat-blocks-matches`). Use that form whenever you
mention an id to the user; a bare `DL-007` tells the PO nothing.
After each stage, print **at most 3 lines**: `✔ Stage <n> · <name> — <what happened>`, the file(s) written and, where
relevant, `python3 scripts/dl.py summary`. After Stages 2, 3, 5 and 7 add `python3 scripts/run_metrics.py W --check
<file>` for `prd-draft.md`, `user-stories.md`, `final-prd.md`. If it says OVER, say so plainly.
Then `python3 scripts/dl.py state stage=<n>`.

## PO checkpoint (procedure used in Stage 3 and Stage 4)
The product owner answers open product questions live, so stories are built on decisions instead of gaps.
1. `python3 scripts/dl.py ask <ids…>` with at most 4 ids, BLOCKING first, then in log order. It returns the
   AskUserQuestion JSON built from the designer's question blocks (recommended option first, `Leave for grooming`
   last) and enforces the per-run question cap. Ids it lists under `over_cap_defer`: run
   `dl.py defer <id> --cap` and do not ask them. If it says `cap_reached`, defer all of them the same way.
   The option texts come in the requirement's language (`(Doporučeno)`, `Nechat na grooming` for Czech).
2. Ask the returned questions in **one** AskUserQuestion call, exactly as returned, without the `dl_id` key (it tells
   you which DL id each question belongs to; the header is a short topic, not the id).
3. For each answer:
   - an option or the user's own text: `dl.py decide <id> <label> "<answer as shown or typed, word for word>"`
     (label = `run<k>-R<N>` or `run<k>-RF`). For a multi-select answer, join the chosen options with ` AND `.
     `decide` stores the chosen option together with its consequence line, so exact wording the PO saw is kept.
   - `Leave for grooming` / `Nechat na grooming`: `dl.py defer <id>`. Never ask about that id again in this run.
   - **Other text that points to another source** (a file, folder or earlier feature): read that source yourself,
     pick at most 3 claims from it that answer this DL question, quoted as written, and ask the PO to confirm them in
     the **next** AskUserQuestion call (`multiSelect: true`, one option per claim, plus `None of these`). Record only
     the ticked claims: `dl.py decide <id> <label> "<ticked claims> (per <source>)"`. None ticked: the row stays
     open and is asked again with the designer's options. Never pass the source's path to an agent.
4. If anything was decided, spawn a **fresh** Agent `designer`:
   ```
   Mode: apply. Round: <N or F>. Run folder: W.
   Read W/prd-draft.md, context/product-context.md, D/confirmed-facts.md, D/decision-log.md.
   Apply PO decisions for: <decided DL ids>.
   Edit W/prd-draft.md. Write W/rounds/r<N or F>-designer-apply.md.
   ```
5. Summary line: `✔ PO checkpoint — decided: <ids> · deferred: <ids> · still queued: <ids>`.

---

## Stage 0 · Preflight (ask, don't guess)
1. If `$ARGUMENTS` is empty or the file does not exist, **stop and ask the user** for the path.
2. Read the requirement file. **Slug:** if its YAML frontmatter has `slug:`, use it. Otherwise propose a kebab-case
   slug from its title, list the folders under `groomed/`, and **ask the user to confirm** with AskUserQuestion
   (options: your proposed slug; any existing folder that could be the same feature, marked as a re-run; Other).
3. `python3 scripts/dl.py start <requirement> <slug>`. If it prints `INCOMPLETE <folder>`, ask the user whether to
   resume that run or start a new one, and rerun with `--resume` or `--new`.
   On a re-run (P is set), show the user a ≤ 5-line gist of `diff P/requirement.md W/requirement.md`.
4. Put `tier`, max rounds (`MAX`), the `language:`, `requirement:`, `personas:` and `product context:` lines from
   `start` in the summary. If personas say CHANGED,
   tell the user the persona snapshots differ from `personas/SOURCES.sha256` and ask whether to continue.

## Stage 1 · Clarify and business context (you, interactively)
Ask **at most 8** questions in total with AskUserQuestion (≤ 4 per call), product and business only, never technical.
Write the questions, options and your stage summaries in the requirement's language (`language:` from `start`).
Skip any question `D/confirmed-facts.md` already answers; on a re-run, ask only about what changed.
1. **Product (call 1):** scan `W/requirement.md`, `context/product-context.md` and `D/confirmed-facts.md` against
   these 10 product-level areas and mark each Clear / Partial / Missing: scope and goal · users and roles · user flow
   and error states · data the user sees or keeps · limits users notice (speed, size, availability) · dependencies on
   other products or teams · edge cases · constraints (deadline, budget, compliance, platform) · terms · what counts
   as done. Ask about the Missing or Partial areas whose answer would most change the PRD. You may ask "The
   requirement states X. Can I treat that as confirmed?" Put the scan in the summary as one line:
   `Missing: … · Partial: …`.
2. **Business context (call 2, always unless already confirmed):** the drafter and the business case need these, and
   runs without them ended with "value not quantified" and no "why now". Ask, with 2–3 concrete options each built
   from the requirement (the user can always type their own):
   - **Business goal:** what should change for the business (e.g. retention, time saved, revenue, cost)?
   - **Success measure and today's level:** which number shows success, and roughly where is it today (or unknown)?
   - **Why now:** deadline, event, competitor, customer demand, or no urgency?
   - **Size of the problem / priority:** how many users or how often, and how important versus other work?
   Replace a question with a more relevant one (e.g. budget, stakeholders, compliance) if the requirement makes it moot.
Skip what `context/product-context.md` already states. Record each answer with `dl.py fact "<fact>"`, in the user's
words (feature facts; the PO moves product-wide ones into the product context by hand if they want). An answer of "unknown" is a fact too
("Baseline for X is unknown"); it tells the drafter to tag the gap instead of inventing a number.

## Stage 2 · Draft PRD
Agent `prd-drafter`, prompt:
```
Mode: <create | update>. Run folder: W.
Read W/requirement.md, context/product-context.md, D/confirmed-facts.md<, P/prd-draft.md, D/decision-log.md if update>.
Write W/prd-draft.md.
```

## Stage 3 · Debate loop (max `MAX` rounds; `N` = round, `R = run<k>-R<N>` is the label in the log)
**Round 1 only, first:** Agent `designer`, prompt:
```
Mode: propose. Round: 1. Run folder: W.
Read W/requirement.md, context/product-context.md, D/confirmed-facts.md, W/prd-draft.md<, D/decision-log.md if it has rows>.
Edit W/prd-draft.md. Write W/rounds/r1-designer-proposal.md.
```
**Each round N = 1..MAX:**
1. Agent `analyst`, prompt:
   ```
   Mode: review. Round: <N>. Run folder: W. <First review of this draft: yes — only if N = 1 and `start` said
   `requirement: new feature` or `CHANGED`. On a re-run of an unchanged requirement leave it out: the analyst then
   may close settled areas instead of having to find something new in each one>
   Read W/requirement.md, context/product-context.md, D/confirmed-facts.md, W/prd-draft.md, D/decision-log.md.
   Write W/rounds/r<N>-analyst.md.
   ```
2. `dl.py findings W/rounds/r<N>-analyst.md R`. It logs every NEW finding and compounding risk and applies every
   REOPEN, and prints the ids to respond to.
3. Summary: verdict, the `findings` output line, `dl.py summary`.
4. If `VERDICT: READY FOR GROOMING` with `NEW_ISSUES: 0`, **exit the loop** now. If READY with only minor findings,
   run steps 5–8 once for them, then **exit the loop** with no further analyst turn.
5. Agent `designer` (a fresh one), prompt:
   ```
   Mode: respond. Round: <N>. Run folder: W.
   Read W/requirement.md, context/product-context.md, D/confirmed-facts.md, W/prd-draft.md, D/decision-log.md, W/rounds/r<N>-analyst.md.
   Respond to these DL ids: <the "respond to" ids from step 2>.
   Edit W/prd-draft.md. Write W/rounds/r<N>-designer-response.md.
   ```
6. `dl.py dispositions W/rounds/r<N>-designer-response.md R <the same ids>`. Ids without an answer are marked
   NOT ADDRESSED; nothing is silently dropped.
7. Summary: its counts line and `dl.py summary`.
8. **PO checkpoint** for this round's open-question ids plus any still queued from earlier rounds.
9. If N = MAX and the verdict was not READY, run a **closing** Agent `analyst`, prompt:
   ```
   Mode: closing. Round: F. Run folder: W.
   Read W/requirement.md, context/product-context.md, D/confirmed-facts.md, W/prd-draft.md, D/decision-log.md.
   Write W/rounds/rF-analyst.md.
   ```
   `dl.py findings W/rounds/rF-analyst.md run<k>-RF --closing`. Major and blocking closing findings are asked
   in Stage 4; minor ones are parked as "proposed: accept or Later" and asked at the last checkpoint (Stage 7).
Then `dl.py state rounds=<N> "verdict=<final verdict>"`.

## Stage 4 · Final PO checkpoint and decision log check
1. `dl.py import-prd`: logs every §9 `- TQ:` line as a Tech team row and every open PO row of §10 as a Still Open row.
2. `dl.py open` lists the ids to ask and those without a question block. For the latter, spawn a fresh Agent
   `designer`:
   ```
   Mode: options. Run folder: W.
   Read W/prd-draft.md, context/product-context.md, D/confirmed-facts.md, D/decision-log.md.
   Prepare PO questions for: <ids>.
   Write W/rounds/rF-designer-options.md.
   ```
   then `dl.py options W/rounds/rF-designer-options.md run<k>-RF` (ids it marked TECH-QUESTION go to the tech team).
3. Run the **PO checkpoint** repeatedly, 4 at a time, until `dl.py open` lists nothing. This is the last chance
   before stories are written.
4. `python3 scripts/check_decision_log.py D/decision-log.md` must print OK. Summary: the final verdict, the log
   summary, BLOCKING ids, deferred ids and the number of tech questions.

## Stage 5 · User stories and business case (two agents in parallel)
Agent `story-writer`, prompt:
```
Run folder: W. Read W/prd-draft.md, D/decision-log.md, context/product-context.md, D/confirmed-facts.md<, P/user-stories.md if it exists (keep US ids)>.
Write W/user-stories.md<, and W/story-map.md if tier standard>.
```
In the same message, Agent `packager` (the business case does not depend on the stories), prompt:
```
Mode: business-case. Run folder: W.
Read W/requirement.md, context/product-context.md, D/confirmed-facts.md, W/prd-draft.md, D/decision-log.md.
Write W/business-case.md.
```

## Stage 6 · Coverage check and story revision
1. Agent `packager`, prompt:
   ```
   Mode: dod. Run folder: W.
   Read D/decision-log.md, W/user-stories.md, W/prd-draft.md.
   Write W/definition-of-done.md.
   ```
2. Agent `coverage-checker`, prompt:
   ```
   Run folder: W. Read D/decision-log.md, W/user-stories.md, W/definition-of-done.md.
   Write W/coverage-report-1.md.
   ```
3. If the report has **no** `GAP` row, no "Vague acceptance criteria" items and no "DoD / AC separation issues"
   that name a DoD item, it is final: `COV = W/coverage-report-1.md`. Otherwise run these (in parallel when both
   apply; they edit different files):
   - GAP rows or vague items → a fresh Agent `story-writer`, prompt:
     ```
     Mode: revise. Run folder: W. Read W/prd-draft.md, D/decision-log.md, context/product-context.md, D/confirmed-facts.md, W/user-stories.md, W/coverage-report-1.md.
     Edit W/user-stories.md.
     ```
   - a DoD item named under "DoD / AC separation issues" → a fresh Agent `packager`, prompt:
     ```
     Mode: dod-fix. Run folder: W.
     Read D/decision-log.md, W/user-stories.md, W/definition-of-done.md, W/coverage-report-1.md.
     Edit W/definition-of-done.md.
     ```
   then a fresh Agent `coverage-checker` (it rechecks only what the first report flagged), prompt:
   ```
   Mode: recheck. Run folder: W. Read D/decision-log.md, W/user-stories.md, W/definition-of-done.md, W/coverage-report-1.md.
   Write W/coverage-report.md.
   ```
   (`COV = W/coverage-report.md`). No further revision after this second check.
4. `dl.py gaps COV`: every GAP row is reopened as COVERAGE GAP, even if it was Resolved.
5. `dl.py import-stories COV`: every 🔵 line in the stories and every leftover vague item becomes a Still Open row,
   so nothing open stays outside the log. DoD / AC overlaps are housekeeping, never PO questions: if it counts any,
   spawn a fresh Agent `packager` with the `dod-fix` prompt from step 3, reading COV instead of coverage-report-1.md.
6. Summary: gaps / vague counts of the first check → of the final check, implementation-detail / separation counts,
   the `--check user-stories.md` line and `dl.py summary`.

## Stage 7 · Last questions, then the grooming package
Nothing the PO could answer should reach the package unasked. Label for this step: `run<k>-final`.
1. `dl.py open --final` lists every row still open, including the ones parked earlier (minor closing-round findings,
   question cap, coverage GAPs, `[Stories]` and `[DoD]` rows). Only ids the PO chose to leave for grooming are skipped.
   If it lists nothing, go to step 4.
2. For ids that need a question block, spawn a fresh Agent `designer`:
   ```
   Mode: options. Run folder: W.
   Read W/prd-draft.md, context/product-context.md, D/confirmed-facts.md, D/decision-log.md, W/user-stories.md.
   Prepare PO questions for: <ids>.
   Write W/rounds/rP-designer-options.md.
   ```
   then `dl.py options W/rounds/rP-designer-options.md run<k>-final`.
3. Run the **PO checkpoint** with `dl.py ask <ids…> --final` (not capped), 4 at a time, until `dl.py open --final`
   lists nothing; record "Leave for grooming" there with `dl.py defer <id> --final`. Instead of the checkpoint's step 4, if anything was decided:
   - first a fresh Agent `designer`: the apply prompt with `Round: P`. It runs **before** the others because the
     PRD is where wording is settled; the stories copy it (running them in parallel let the wording drift);
   - then, in parallel, a fresh Agent `story-writer`:
     ```
     Mode: apply. Run folder: W. Read W/prd-draft.md, D/decision-log.md, context/product-context.md, D/confirmed-facts.md, W/user-stories.md.
     Apply PO decisions for: <decided DL ids>.
     Edit W/user-stories.md.
     ```
     and, if any `decide` line said `affects: DoD`, a fresh Agent `packager`:
     ```
     Mode: dod-apply. Run folder: W.
     Read D/decision-log.md, D/confirmed-facts.md, W/user-stories.md, W/definition-of-done.md.
     Apply PO decisions for: <the decided ids whose decide line said affects: DoD>.
     Edit W/definition-of-done.md.
     ```
   Summary line: `✔ Last questions — decided: <ids> · left for grooming: <ids>`.
4. `dl.py package-parts`: writes `W/readiness.md` (Definition of Ready per story, checked by script),
   `W/po-decisions.md` (question → answer for every PO decision) and `W/slices.md`. Put its first line in the summary.
   Then Agent `packager`, prompt:
   ```
   Mode: summary. Run folder: W.
   Read W/business-case.md, W/prd-draft.md, D/decision-log.md, W/user-stories.md, W/readiness.md.
   Write W/package-summary.md.
   ```
   Then `dl.py assemble COV`: builds `W/final-prd.md` from the summary and the checked files (terms, stories,
   readiness, DoD, slices, PO decisions, open and tech questions are copied, never retyped). Put its line in the summary.
5. `python3 scripts/validate_output.py package W` (formats, budgets, altitude words, unlogged 🔵, and consistency
   between stories, story map, decision log and PRD §8). Put the number of problems in the summary and list up to 5.
Do not fix them yourself; they are for the PO and the retro.

## Stage 8 · Retro (suggestions only; runs in the background)
The package is done before the retro starts, so the PO gets it without waiting for the retro.
1. `python3 scripts/run_metrics.py W` (writes `W/run-metrics.md`).
2. Agent `retro` with `run_in_background: true`, then **immediately** print the Final message (below). Prompt:
   ```
   Run folder: W. Read W/run-metrics.md first, then the files in W and W/rounds, D/decision-log.md,
   D/confirmed-facts.md, CLAUDE.md, CHANGELOG.md, .claude/commands/groom.md, .claude/agents/*.md<, P/retro.md if it exists><,
   groomed/scorecard.csv if it exists>.
   Write W/retro.md.
   ```
3. Do **not** act on the retro: change no agent, rule, artifact or log row because of it, and never pass `retro.md`
   or `run-metrics.md` to another agent. They are for the PO.
4. When the retro finishes: the output check (`--after retro retro.md`), then `dl.py scores` (stores the retro's
   scorecard in `groomed/scorecard.csv` and prints this run's scores with the trend), then `dl.py state complete`
   (marks the run complete and removes the active-run pin). Print ≤ 3 lines: the scores line, the path to
   `W/retro.md` and its top recommendation (the retro agent's reply, one line).
5. If this stage fails, say so. The package is still complete; still run `dl.py state complete`.

## Final message (printed right after the retro starts)
≤ 8 lines: the path to `W/final-prd.md` and its line count, the verdict, the log summary, open or BLOCKING ids (with
names) the PO must answer at grooming, how many questions went to the tech team, the package-lint problem count,
one line listing the stage files, and "Retro running; its scores follow." Open ids are only those the PO chose to
leave for grooming. Do not paste the package.
