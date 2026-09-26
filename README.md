# Grooming pipeline

`/groom <requirement.md>` turns a requirement into a short, product-level grooming package under `groomed/<slug>/`.
Technical design is left to the delivery team: technical concerns are listed as questions for them, not answered.

Product questions are asked live: after each debate round, and once more before stories are written, you get up to
4 questions at a time with a recommended option. Pick one, type your own answer, or choose "Leave for grooming".
The Designer and Analyst are separate subagents, and a hook limits the Analyst to the written PRD and its inputs.

## Run
- Inside Claude Code (from this folder): `/groom requirements/example-csv-export.md`
- From a shell: `scripts/groom.sh requirements/example-csv-export.md` (needs the `claude` CLI on PATH)

The first time, accept the workspace-trust prompt. The isolation hooks in `.claude/agents/*.md` do not run without it.

## Stages → files in `groomed/<slug>/run-<n>_<date>/`
| Stage | Who | Output |
|---|---|---|
| 0 Preflight, 1 Clarify | orchestrator (asks you) | `requirement.md`, `../confirmed-facts.md` |
| 2 Draft | `prd-drafter` | `prd-draft.md` |
| 3 Debate (≤3 rounds) | fresh `designer` / `analyst` per turn | `rounds/` (designer files analyst-blocked), updated `prd-draft.md` |
| 4 Decision log | orchestrator + `check_decision_log.py` hook | `../decision-log.md` |
| 5 Stories | `story-writer` | `user-stories.md`, `story-map.md` |
| 6 Coverage | `packager` (prep), `coverage-checker` | `business-case.md`, `definition-of-done.md`, `coverage-report.md` |
| 7 Package | `packager` (assemble) | **`final-prd.md`** |

```
groomed/<slug>/
├── decision-log.md      shared by all runs of this feature
├── confirmed-facts.md   shared by all runs of this feature
├── run-1_2026-09-26/    everything run 1 produced (final-prd.md, stories, rounds/, …)
└── run-2_2026-09-28/
```
Running `/groom` again on the same feature creates a new run folder and never touches earlier ones.

## Guarantees enforced by code, not prompts
- `scripts/guard.py`: per-role read/write allowlist and Read/Write-only tools, wired as a PreToolUse hook in each agent.
- `scripts/check_decision_log.py`: PostToolUse hook that rejects any write to `decision-log.md` that drops a row,
  rewords an issue, or uses an unknown status.

## Personas
`personas/` holds unchanged snapshots of your skills (checksums in `personas/SOURCES.sha256`).
Refresh them with `scripts/sync_personas.sh`. Pipeline overrides are stated in each agent file, not edited into the personas.
