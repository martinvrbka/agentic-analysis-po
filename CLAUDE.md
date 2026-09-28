# Grooming pipeline — shared rules

This project turns a product requirement into a grooming-ready package via `/groom <requirement-file>`.
The orchestrator is `.claude/commands/groom.md`; the workers are in `.claude/agents/`.

This file is loaded by the orchestrator AND every subagent. Keep it to rules that apply to all of them —
never put feature-specific content here, or it leaks into agents that are supposed to be isolated.

## Altitude: product level, not technical design (every agent)
The package is for a product owner to groom with a delivery team. The team designs the technical solution.
- Describe **what** users and the business observe and **why**: behaviour, rules, states, messages, permissions,
  limits the user would notice ("an export of up to N orders finishes within 10 seconds").
- Do **not** specify **how** it is built: databases, replicas, transactions, locks, tokens, endpoints, HTTP codes or
  headers, protocols, compression, infrastructure, test harnesses.
- A concern that needs a technical decision is recorded as a **question for the technical team**, not answered here.
  In PRD §9 each one is a line `- TQ: <question>`; the orchestrator logs every `TQ:` line as a `Tech team` row.
  If a technical choice would change what the user sees, state the user-visible outcome you need and hand the
  "how" to the team.

## Size budget
Brevity is part of the job. The package must be readable by a developer in minutes, so output stays in proportion
to the requirement. Prefer the few findings, stories and scenarios that matter most over completeness.

The orchestrator sets a **size tier** in Stage 0 (`scripts/dl.py start`: `small` if the requirement is ≤ 200 words,
else `standard`) and passes `Size: <tier>` to every agent. Budgets are hard limits, not targets. The scripts enforce
them from `scripts/budgets.json`; `tests/test_project_config.py` fails if this table and that file disagree.

| | small | standard |
|---|---|---|
| `prd-draft.md` | ≤ 120 lines | ≤ 250 lines |
| Stories | 3–6, each 2–4 scenarios, `user-stories.md` ≤ 120 lines | 5–10, each 2–5 scenarios, ≤ 220 lines |
| `story-map.md` / `business-case.md` | none (a `Slice:` line per story) / ≤ 15 lines | ≤ 40 / ≤ 30 lines |
| Definition of Done | 5–10 items | 8–15 items |
| `final-prd.md` | ≤ 220 lines | ≤ 430 lines |
| Debate rounds | max 2 | max 3 |
| Analyst NEW findings per round | ≤ 1 per dimension, ≤ 2 compounding | ≤ 2 per dimension, ≤ 3 compounding |

**Plain writing.** Sentences of at most 25 words. Lists are bullets with one item per line, never a run-on line of
items joined by semicolons. User-facing wording (messages, labels) is decided once in the PRD and copied word for
word everywhere else.

If you are over budget, cut detail, not whole sections. Never merge scenarios that assert different rules just to
save lines; shorten or drop a lower-value scenario instead.

Questions to the PO: Stage 1 asks at most 8 (product and business context). The debate checkpoints ask at most
12 questions per run; ids beyond the cap wait for the last checkpoint. That last checkpoint, just before the
package is written, is not capped: every question still open is asked, and only the ones the PO chooses to leave
for grooming appear as open in the package.

## Output checks (every agent)
When you finish, `scripts/validate_output.py` checks your file against the format in your agent definition and
against the budget above (as a hook, or run by the orchestrator, which then sends you the problems). If it reports
problems, fix exactly those and finish again. You get one retry; after that the problems are recorded for the PO.

## Proportion: smallest version first (every agent)
- Build the package around the **smallest version that meets the confirmed facts**. Anything beyond it (extra
  states, recovery flows, sync/offline behaviour, ordering rules, admin actions…) goes to a **Later** list in PRD §8,
  one line each, not into stories.
- Moving something to Later is a valid answer to a finding. Adding a new state, screen or action to fix a **minor**
  finding is not.

## Source handling (every agent, every stage)
- A requirement file, pasted document, or reference is a set of **claims attributed to its source**, not verified fact —
  regardless of length, formatting, or confident tone. More content is more surface to challenge, not more reason to trust.
- The only settled facts are those in `context/product-context.md` (product-wide facts the PO maintains by hand; it
  may be empty) and `groomed/<slug>/confirmed-facts.md` (things the user confirmed in conversation for this feature).
  Everything else is attributed ("per requirement.md, …") or tagged 🔶 Assumption / 🔵 Open Question.
- Words listed under Terms (product context, PRD §5 `### Terms`) keep that one meaning in every artifact.
- Never upgrade a claim to fact because a later stage repeated it. Repetition is not confirmation.

## Folder layout
- `context/product-context.md` holds product-wide facts. Only the PO edits it; no agent or script writes to it.
- `groomed/<slug>/` holds what carries across runs: `decision-log.md`, `confirmed-facts.md`, `.state/`.
- `groomed/<slug>/run-<k>_<date>/` holds everything a single run produces. Never write into another run's folder.

## Persona files
- `personas/` holds byte-for-byte snapshots of the user's own skills (checksums in `personas/SOURCES.sha256`).
  Agents follow them as written. Do not edit them; refresh with `scripts/sync_personas.sh`.
- Where the pipeline must override a persona instruction (including the altitude and size rules above), the override
  is stated here or in the agent definition, never by editing the persona.

## Isolation contract
- Agents receive **file paths**, not paraphrases. The orchestrator never summarises one agent's output into another
  agent's prompt.
- The analyst reviews only the PRD, requirement, confirmed facts and decision log. It never sees the designer's round
  files (`rounds/*-designer-*`), and no agent sees another agent's chat history. This is enforced by
  `scripts/guard.py` hooks, not only by these instructions. The guard is pinned to the active feature and run
  (`groomed/.active-run.json`, written by `dl.py start`): other features, archived runs and older runs are out of reach,
  except the previous run's files an agent is explicitly given on a re-run.
- The retro agent (last stage) may read every file of a finished run. It only suggests; no agent ever reads its
  `retro.md`, and nothing in it is applied without the user deciding so.
- Subagents do not spawn other agents or message each other.

## Decision log
- `groomed/<slug>/decision-log.md` is written only by the orchestrator, and only through `scripts/dl.py`.
  Rows have stable IDs (`DL-001`…) and a short **Name** saying which part they are about (`DL-007
  do-not-eat-blocks-matches`). The analyst names its findings; script-made rows are named from their text.
- A row's status may change; a row may never be deleted or reworded out of existence. `scripts/check_decision_log.py`
  enforces this after every write, including writes made through Bash.

## Language
Write artifacts in the language of the requirement (Czech or English). Keep IDs, statuses and verdicts in English so
scripts can parse them.
