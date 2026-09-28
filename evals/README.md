# Regression evals

Run these after any change to `CLAUDE.md`, `.claude/commands/groom.md`, `.claude/agents/*.md` or `scripts/budgets.json`,
before trusting the pipeline on a real feature.

## 1. Script tests (seconds, no model calls)
```
python3 -m unittest discover -s tests
```
Covers the guard (isolation), the decision-log rules, `dl.py` bookkeeping, the output checks and the consistency of
budgets, agent wiring and persona checksums. Must pass before anything else.

## 2. Pipeline runs (minutes, model calls)
For each case, run `/groom <file>` with a throwaway slug (e.g. `eval-csv-export`), answer the PO questions with the
recommended option unless the case says otherwise, then:
```
python3 scripts/eval_check.py groomed/<slug>/run-1_<date>
```

| Case | Requirement | What it exercises |
|---|---|---|
| csv-export | `requirements/example-csv-export.md` | standard tier, permissions, failure handling |
| foodie-match | `requirements/foodie-match-app.md` | couple / shared data, many PO decisions |
| filters | `requirements/filters.md` | small tier, vague requirement, Stage 1 questions |

`eval_check.py` is code-graded: run completed, log valid, no BLOCKING or NOT ADDRESSED rows, every open row asked,
PO questions within the cap, package lint clean, no output problems left after the retry cap, scorecard stored.
The retro's scorecard (`groomed/scorecard.csv`) shows whether a pipeline change moved quality up or down. A FAIL tells you where to look, not what to fix.

## 3. Read the transcripts
Code checks cannot tell whether a finding was real or whether a story is useful. For each case, read `final-prd.md`
and one round of `rounds/` end to end, and compare with the previous run of the same case (`retro.md` helps).
Afterwards move the eval folders to `groomed/_archive/`.

Add a case whenever a real run shows a failure the cases above would not have caught.
