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
  If a technical choice would change what the user sees, state the user-visible outcome you need and hand the
  "how" to the team.

## Size budget
Brevity is part of the job. Prefer the few findings, stories and scenarios that matter most over completeness.
- PRD draft: about 150–250 lines. Stories: about 5–10, each with 2–5 scenarios.
- `final-prd.md`: about 250–400 lines. If you are over budget, cut detail, not whole sections.

## Source handling (every agent, every stage)
- A requirement file, pasted document, or reference is a set of **claims attributed to its source**, not verified fact —
  regardless of length, formatting, or confident tone. More content is more surface to challenge, not more reason to trust.
- The only settled facts are those in `groomed/<slug>/confirmed-facts.md` (things the user explicitly confirmed in
  conversation). Everything else is attributed ("per requirement.md, …") or tagged 🔶 Assumption / 🔵 Open Question.
- Never upgrade a claim to fact because a later stage repeated it. Repetition is not confirmation.

## Folder layout
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
  `scripts/guard.py` hooks, not only by these instructions.
- Subagents do not spawn other agents or message each other.

## Decision log
- `groomed/<slug>/decision-log.md` is written only by the orchestrator. Rows have stable IDs (`DL-001`…).
- A row's status may change; a row may never be deleted or reworded out of existence. `scripts/check_decision_log.py`
  enforces this after every write.

## Language
Write artifacts in the language of the requirement (Czech or English). Keep IDs, statuses and verdicts in English so
scripts can parse them.
