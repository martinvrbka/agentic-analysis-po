# Grooming pipeline

`/groom <requirement.md>` turns a requirement into a grooming package under `groomed/<slug>/`.
The Designer and Analyst are separate subagents, and the Analyst is blocked by a hook from reading Designer reasoning.

## Run
- Inside Claude Code (from this folder): `/groom requirements/example-csv-export.md`
- From a shell: `scripts/groom.sh requirements/example-csv-export.md` (needs the `claude` CLI on PATH)

The first time, accept the workspace-trust prompt. The isolation hooks in `.claude/agents/*.md` do not run without it.

## Stages → files in `groomed/<slug>/`
| Stage | Who | Output |
|---|---|---|
| 0 Preflight, 1 Clarify | orchestrator (asks you) | `requirement.md`, `confirmed-facts.md` |
| 2 Draft | `prd-drafter` | `prd-draft.md` |
| 3 Debate (≤3 rounds) | fresh `designer` / `analyst` per turn | `rounds/`, `designer-notes/` (analyst-blocked), updated `prd-draft.md` |
| 4 Decision log | orchestrator + `check_decision_log.py` hook | `decision-log.md` |
| 5 Stories | `story-writer` | `user-stories.md`, `story-map.md` |
| 6 Coverage | `packager` (prep), `coverage-checker` | `business-case.md`, `definition-of-done.md`, `coverage-report.md` |
| 7 Package | `packager` (assemble) | **`final-prd.md`** |

Re-running on an existing slug archives the previous run to `history/run-<n>/` and carries `decision-log.md` and
`confirmed-facts.md` forward.

## Guarantees enforced by code, not prompts
- `scripts/guard.py`: per-role read/write allowlist and Read/Write-only tools, wired as a PreToolUse hook in each agent.
- `scripts/check_decision_log.py`: PostToolUse hook that rejects any write to `decision-log.md` that drops a row,
  rewords an issue, or uses an unknown status.

## Personas
`personas/` holds unchanged snapshots of your skills (checksums in `personas/SOURCES.sha256`).
Refresh them with `scripts/sync_personas.sh`. Pipeline overrides are stated in each agent file, not edited into the personas.
