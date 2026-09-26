---
name: design-analysis-debate
description: Runs a structured Designer vs Analyst (Blue/Red team) debate on a spec or feature design to stress-test it before grooming. Use after a PRD/spec draft exists, when the user wants critical review, not more requirements gathering.
---

# Design vs Analysis Debate

Use this skill AFTER a requirement/spec already exists (e.g. produced by `write-spec` or `prd-development`). Do not use this to gather new requirements from scratch — use the discovery/PRD skills for that. This skill's job is to **stress-test what's already on the table** before it goes to grooming.

## When to trigger
User says things like: "rozporuj to", "pusť na to Designer vs Analyst", "critique this spec", "red team this feature", "je to ready na grooming?".

## Roles
Run these as sequential rounds inside the same response — do not skip rounds, do not merge them into one paragraph, label each round clearly.

### Round 1 — Designer (Blue Team, propose)
- Restate the feature/requirement in your own words in 2-3 sentences.
- Propose the concrete solution: user flow, screens/states, or system interaction as relevant.
- State explicitly what is IN scope and OUT of scope.
- Do not hedge here — commit to a real proposal, not a menu of options.

### Round 2 — Analyst (Red Team, attack)
Must find **at least one real issue in each of these five dimensions** (skip a dimension only if truly not applicable, and say why):
1. **Purpose** — does the solution actually solve the stated problem? Any mismatch between what was asked and what was designed?
2. **Data** — what data is created/moved/stored, who owns it, what happens to it on failure (partial writes, duplicates, conflicting versions)?
3. **Behavior / edge cases** — what happens on: network loss mid-action, concurrent use, retries, empty/invalid input, the "off-path" user journeys nobody drew?
4. **Constraints & NFRs** — security/authorization, performance/timeout, connectivity assumptions (e.g. offline device), auditability, GDPR/compliance where relevant.
5. **Testability** — can each acceptance criterion actually be tested/verified as written, or is it vague?

Hard rule: **no "LGTM"**. If the spec is genuinely solid on a dimension, say so briefly and move on — but at least one dimension must surface a real, specific, non-generic issue tied to this exact feature, not a generic checklist item.

**Source-authority bias check:** a claim's length, formatting, or confident tone is not evidence it's correct. A detailed multi-page business requirement document deserves exactly the same scrutiny as a three-sentence note — more content is more surface area to challenge, not more reason to trust it. When reviewing input drawn from an external document, explicitly ask "is this independently confirmed, or just asserted by this source?" before treating it as settled.

### Round 3 — Designer (Blue Team, respond)
For each issue raised in Round 2: either (a) revise the proposal to address it, (b) explicitly accept the risk and say why it's acceptable for this scope, or (c) mark it as an open question for grooming. No issue may be silently dropped.

### Round 4 — Analyst (Compounding Risk Check)
Individually-accepted resolutions can still combine into a new problem — a decision that's fine on its own can undercut a different decision made elsewhere in the same spec. Take the full list of resolutions from Round 3 (fixes AND accepted risks) and check them **pairwise** against each other, specifically asking: "does accepting A weaken or defeat the point of B?" Concrete pattern to watch for: a broad/permissive decision (no cap, fail-open, wide access) combined with a control that assumes the opposite (a scan, an audit step, a narrow permission) — the permissive decision can quietly make the control ineffective in the common case rather than the exception. Surface every compounding risk found, even if none of the individual pieces looked wrong in isolation. If genuinely none exist, say so explicitly — don't skip this round silently.

### Round 5 — Synthesis, Decision Log & verdict
Maintain a **Decision Log** that is cumulative across the whole session/document history — never reset it, never drop a row between debate runs or document versions:
- Columns: Question/Issue | Raised in (round/date) | Status (Resolved / Still Open) | Resolution or reason still open.
- Every issue ever raised by any round (including Round 4 compounding risks) gets a row. A row's status may change from Open to Resolved, but a row must never simply disappear from the log in a later version — if something looks resolved, show what resolved it; if it's still unresolved, keep it visible.
- When revising an existing document, first reconcile the new debate's findings against the *previous* Decision Log: carry forward every prior row unchanged unless this round explicitly resolves or updates it — do not regenerate the log from scratch each time.
- End with a verdict: **READY FOR GROOMING** (all rows Resolved) / **NEEDS ANOTHER ROUND** / **BLOCKED** (name the blocking row explicitly). A BLOCKED verdict on a prior round must stay visible as BLOCKED in the log until explicitly resolved — never let a blocking issue quietly drop off between versions.

### Round 6 — Story Coverage Check (run only once user stories/acceptance criteria exist)
This checks a different failure mode than Rounds 1-5: a decision can be correctly made and logged as Resolved, and still never make it into anything a developer actually builds or tests against. Once user stories with Given/When/Then acceptance criteria exist, run this pass:
- For every **Resolved** row in the Decision Log, check: is there a specific acceptance criterion (in some story) that a developer could point to as "this is where that decision is implemented/tested"? If not, flag it — the decision exists on paper but has no story enforcing it.
- For every accepted risk/mitigation in the spec (e.g. from Round 3 or 4), same check: does a story's acceptance criteria actually verify the mitigation, or does the mitigation only exist as a sentence in the PRD with nothing testing it?
- Flag any acceptance criterion that is vague enough that two different developers could reasonably implement it differently (this overlaps with Round 2's testability check, but re-run it here because criteria phrasing often changes during story-writing, after the original debate).
- Output: a short coverage table — Decision/Risk → Covered by (story #) or **GAP — no story covers this**. Any GAP goes back into the Decision Log as Still Open, even if it was previously marked Resolved at the PRD-decision level — a decision without a story enforcing it is not actually done.
- This round does not re-litigate Rounds 1-4 from scratch; it only checks the handoff from "decided" to "testable."

## Style
- Analyst tone is genuinely skeptical, not performative — specific to this feature, not boilerplate concerns.
- Keep each round tight; this is a working debate, not an essay.
- Czech or English, matching the user's language in the request.
