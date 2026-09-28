#!/usr/bin/env python3
"""Regression check for one finished /groom run: code-graded pass/fail criteria (see evals/README.md).

Usage: eval_check.py <run folder>      e.g. groomed/order-export/run-1_2026-10-01
Exit code 0 if every criterion passes, 1 otherwise. Complements, never replaces, reading the package and transcripts.
"""
import json
import os
import sys

import validate_output as vo
from pipeline_common import budgets, parse_log, read_lines


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        sys.exit(__doc__)
    W = sys.argv[1].rstrip("/")
    D = os.path.dirname(W)
    tier = vo.tier_for(W)
    with open(os.path.join(D, ".state", "run-state.json"), encoding="utf-8") as f:
        run = next((r for r in json.load(f)["runs"] if r["folder"].rstrip("/").endswith(W.split("groomed/")[-1])), {})
    rows, log_errors = parse_log(os.path.join(D, "decision-log.md"))
    lint = vo.package_lint(W, tier)
    warnings = [l for l in read_lines(os.path.join(D, ".state", "validation-warnings.log")) or []
                if W.split("groomed/")[-1] in l]
    checks = [
        ("run completed (stages 0–8)", run.get("complete") is True and len(run.get("stages", {})) >= 9),
        ("decision log valid", not log_errors),
        ("no BLOCKING rows left", not any(r["status"] == "Still Open (BLOCKING)" for r in rows)),
        ("no NOT ADDRESSED rows", not any("NOT ADDRESSED" in r["resolution"] for r in rows)),
        ("every open row was asked (only PO deferrals left open)",
         not any(r["status"].startswith("Still Open") and "deferred to grooming by PO" not in r["resolution"]
                 for r in rows)),
        ("retro scorecard stored", os.path.exists(os.path.join(os.path.dirname(D), "scorecard.csv"))),
        ("PO questions within cap", run.get("po_questions", 0) <= budgets()["max_po_questions"]),
        ("package lint clean (formats, budgets, altitude, unlogged 🔵)", not lint),
        ("no output problems left after the retry cap", not warnings),
    ]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for p in lint[:10]:
        print(f"      {p}")
    sys.exit(0 if all(ok for _, ok in checks) else 1)


if __name__ == "__main__":
    main()
