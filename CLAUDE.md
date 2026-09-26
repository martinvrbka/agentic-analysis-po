# Grooming pipeline — shared rules

This project turns a product requirement into a grooming-ready package via `/groom <requirement-file>`.
The orchestrator is `.claude/commands/groom.md`; the workers are in `.claude/agents/`.

This file is loaded by the orchestrator AND every subagent. Keep it to rules that apply to all of them —
never put feature-specific content here, or it leaks into agents that are supposed to be isolated.

## Source handling (every agent, every stage)
- A requirement file, pasted document, or reference is a set of **claims attributed to its source**, not verified fact —
  regardless of length, formatting, or confident tone. More content is more surface to challenge, not more reason to trust.
- The only settled facts are those in `groomed/<slug>/confirmed-facts.md` (things the user explicitly confirmed in
  conversation). Everything else is attributed ("per requirement.md, …") or tagged 🔶 Assumption / 🔵 Open Question.
- Never upgrade a claim to fact because a later stage repeated it. Repetition is not confirmation.

## Persona files
- `personas/` holds byte-for-byte snapshots of the user's own skills (checksums in `personas/SOURCES.sha256`).
  Agents follow them as written. Do not edit them; refresh with `scripts/sync_personas.sh`.
- Where the pipeline must override a persona instruction, the override is stated explicitly in the agent definition
  and nowhere else.

## Isolation contract
- Agents receive **file paths**, not paraphrases. The orchestrator never summarises one agent's output into another
  agent's prompt.
- The analyst never sees designer reasoning (`designer-notes/`, `rounds/*-designer-*`), and no agent sees another
  agent's chat history. This is enforced by `scripts/guard.py` hooks, not only by these instructions.
- Subagents do not spawn other agents or message each other.

## Decision log
- `groomed/<slug>/decision-log.md` is written only by the orchestrator. Rows have stable IDs (`DL-001`…).
- A row's status may change; a row may never be deleted or reworded out of existence. `scripts/check_decision_log.py`
  enforces this after every write.

## Language
Write artifacts in the language of the requirement (Czech or English). Keep IDs, statuses and verdicts in English so
scripts can parse them.
