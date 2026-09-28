# Grooming pipeline

`/groom <requirement.md>` turns a requirement into a short, product-level grooming package under `groomed/<slug>/`.
Technical design is left to the delivery team: technical concerns are listed as questions for them, not answered.

Product questions are asked live: after each debate round, and once more before stories are written, you get up to
4 questions at a time with a recommended option (at most 12 per run). Pick one, type your own answer, or choose
"Leave for grooming". The Designer and Analyst are separate subagents, and a hook limits each agent to its own inputs.

## Run
- Inside Claude Code (from this folder): `/groom requirements/example-csv-export.md`
- From a shell: `scripts/groom.sh requirements/example-csv-export.md` (needs the `claude` CLI on PATH)

The first time, accept the workspace-trust prompt. The hooks in `.claude/agents/*.md` do not run without it, and
some clients (the VS Code extension in September 2026) do not run them at all. The orchestrator therefore also runs
the output check itself after every agent, and the read/write guard also runs from `.claude/settings.json`.

## Stages → files in `groomed/<slug>/run-<n>_<date>/`
| Stage | Who | Output |
|---|---|---|
| 0 Preflight, 1 Clarify | orchestrator + `dl.py start` (asks you) | `requirement.md`, `../confirmed-facts.md` |
| 2 Draft | `prd-drafter` | `prd-draft.md` |
| 3 Debate (max 2 rounds small, 3 standard, + closing review) | fresh `designer` / `analyst` per turn | `rounds/`, updated `prd-draft.md` |
| 4 Final PO checkpoint | orchestrator + `dl.py` | `../decision-log.md` |
| 5 Stories, business case | `story-writer` and `packager` (business-case) in parallel | `user-stories.md` (+ `story-map.md` for standard-size features), `business-case.md` |
| 6 Coverage | `packager` (dod), `coverage-checker`, one revision and a recheck | `definition-of-done.md`, `coverage-report*.md` |
| 7 Last questions, package | orchestrator, `dl.py package-parts`, `packager` (summary), `dl.py assemble`, package lint | `package-summary.md`, **`final-prd.md`** |
| 8 Retro (in the background, after the package is shown) | `run_metrics.py`, `retro` | `run-metrics.md`, `retro.md` (suggestions only) |

```
groomed/<slug>/
├── decision-log.md      shared by all runs of this feature
├── confirmed-facts.md   shared by all runs of this feature
├── .state/              run state, log snapshot, output-check warnings
├── run-1_2026-09-26/    everything run 1 produced (final-prd.md, stories, rounds/, …)
└── run-2_2026-09-28/
```
Running `/groom` again on the same feature creates a new run folder and never touches earlier ones.
Decision-log rows have an id and a short name (`DL-007 do-not-eat-blocks-matches`); the name is what you see in
questions, summaries and the package.

## Guarantees enforced by code, not prompts
- `scripts/guard.py`: per-role read/write allowlist, pinned to the active feature and run, Read/Write/Edit only.
- `scripts/dl.py`: the only way the orchestrator writes the log, facts and run state; invalid log writes roll back.
- `scripts/check_decision_log.py`: hook after every Write, Edit and Bash call; rejects dropped or reworded rows.
- `scripts/validate_output.py`: format and size budget of every agent's output (Stop hook, and `--after` run by the
  orchestrator; one fix round) and the Stage 7 lint, which also checks that wording the PO chose reaches the PRD
  and that the stories quote messages exactly as the PRD does.
- `scripts/dl.py assemble`: builds `final-prd.md`; everything that must be verbatim is copied by the script.
- `scripts/budgets.json`: the one place the size budgets and caps live.

## Product context
`context/product-context.md` holds facts that are true for the whole product (what it is, users, business goals,
constraints, agreed terms). It starts empty; fill in any section whenever you like, one line per fact. Every agent
reads it and treats it as confirmed, so Stage 1 asks fewer questions. No agent or script ever writes to it.

## What the package contains
`final-prd.md`: in one minute · business case · scope · terms · stories with acceptance criteria · Definition of
Ready (per story, checked by script) · Definition of Done · proposed slices · PO decisions (question → answer) ·
questions left for grooming · questions for the tech team · links to working files.

## Tests and evals
- `python3 -m unittest discover -s tests`: script and configuration tests, no model calls.
- `evals/README.md`: regression runs on the requirement files, checked with `scripts/eval_check.py`.
- `CHANGELOG.md`: every pipeline change and why; the retro reads it.

## Personas
`personas/` holds unchanged snapshots of your skills (checksums in `personas/SOURCES.sha256`, verified at Stage 0 and
by the tests). Refresh them with `scripts/sync_personas.sh`. Pipeline overrides are stated in each agent file, not
edited into the personas.
