#!/usr/bin/env python3
"""Measure one /groom run and write <run folder>/run-metrics.md for the retro agent.

Usage:
  run_metrics.py <run folder>                 write run-metrics.md, e.g. groomed/<slug>/run-2_2026-09-27
  run_metrics.py <run folder> --tier          print the size tier (small | standard) from requirement.md
  run_metrics.py <run folder> --check <file>  print one file's size against its budget (for stage summaries)

Counts only; no judgement. The retro agent interprets the numbers. Budgets come from scripts/budgets.json;
tests/test_budgets.py checks that CLAUDE.md states the same numbers.
"""
import datetime
import glob
import json
import os
import re
import sys
from collections import Counter

from pipeline_common import budgets as _budgets
from pipeline_common import parse_log

_B = _budgets()
SMALL_MAX_WORDS = _B["small_max_words"]  # requirement word count at or below which a run is tier "small"

# Per tier: (file, low, high) in lines; None = no stated bound. Built from scripts/budgets.json (single source).
BUDGETS = {
    tier: {
        "lines": [(name, None, hi) for name, hi in b["lines"].items() if name != "retro.md"]
                 + [("definition-of-done.md", None, None), ("coverage-report.md", None, None)],
        "stories": tuple(b["stories"]), "scenarios": tuple(b["scenarios"]), "dod": tuple(b["dod"]),
        "rounds": b["rounds"],
    }
    for tier, b in _B["tiers"].items()
}

ROW = re.compile(r"^\|\s*(DL-\d{3,})\s*\|")
CELL_SEP = re.compile(r"(?<!\\)\|")


def lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return None


def flag(n, lo, hi):
    if n is None:
        return "missing"
    if hi is not None and n > hi:
        return f"OVER (max {hi})"
    if lo is not None and n < lo:
        return f"under (min {lo})"
    return "ok" if (lo, hi) != (None, None) else "no budget"


def req_words(W):
    req = lines(os.path.join(W, "requirement.md")) or []
    return sum(len(l.split()) for l in req if not l.startswith("> Source:"))


def tier_of(W):
    """The tier recorded in run-state.json for this run, else computed from the requirement."""
    D = os.path.dirname(W.rstrip("/"))
    try:
        with open(os.path.join(D, ".state", "run-state.json"), encoding="utf-8") as f:
            for r in json.load(f).get("runs", []):
                if r.get("folder", "").rstrip("/") == W.rstrip("/") and r.get("size"):
                    return r["size"]
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return "small" if req_words(W) <= SMALL_MAX_WORDS else "standard"


def readability(ls):
    """Plain-text numbers a PO can read: length, reading time, sentence length, tags left open."""
    if ls is None:
        return ["- final-prd.md missing"]
    prose = [re.sub(r"[*_`>]", "", l).strip().lstrip("- ").strip()
             for l in ls if l.strip() and not l.startswith(("|", "#", "```"))]
    words = len(re.findall(r"\w+", " ".join(prose)))
    # Each line ends a sentence: Given/When/Then lines and bullets have no full stop, and joining them across lines
    # used to report 35–37-word "sentences" that were really several short lines.
    sentences = [x for l in prose for x in re.split(r"(?<=[.!?])\s+", l) if len(x.split()) >= 3]
    lens = [len(x.split()) for x in sentences] or [0]
    long_share = sum(1 for n in lens if n > 25) / len(lens)
    all_text = "\n".join(ls)
    total = len(re.findall(r"\w+", all_text))
    return [f"- Words: {total} · reading time ≈ {max(1, round(total / 200))} min (200 words/min)",
            f"- Prose sentences: {len(sentences)} · average {sum(lens) / len(lens):.0f} words · "
            f"over 25 words: {long_share:.0%}",
            f"- Tags left in the package: 🔶 {all_text.count('🔶')} · 🔵 {all_text.count('🔵')}",
            f"- Prose words (excluding tables/headings): {words}"]


def package_time(W):
    """When final-prd.md was written (metrics run before the run is marked complete, so 'completed' is always empty)."""
    f = os.path.join(W, "final-prd.md")
    if not os.path.exists(f):
        return "—"
    return datetime.datetime.fromtimestamp(os.path.getmtime(f)).isoformat(timespec="seconds")


def log_rows(path):
    return parse_log(path)[0]


def main():
    if len(sys.argv) < 2 or not os.path.isdir(sys.argv[1]):
        sys.exit("usage: run_metrics.py <run folder> [--tier | --check <file>]")
    W = sys.argv[1].rstrip("/")
    if sys.argv[2:3] == ["--tier"]:
        print("small" if req_words(W) <= SMALL_MAX_WORDS else "standard")
        return
    tier = tier_of(W)
    B = BUDGETS[tier]
    LINE_BUDGETS, STORIES, SCENARIOS_PER_STORY, DOD_ITEMS, MAX_ROUNDS = (
        B["lines"], B["stories"], B["scenarios"], B["dod"], B["rounds"])
    if sys.argv[2:3] == ["--check"] and len(sys.argv) == 4:
        name = os.path.basename(sys.argv[3])
        lo, hi = next(((l, h) for n, l, h in LINE_BUDGETS if n == name), (None, None))
        ls = lines(os.path.join(W, name))
        n = None if ls is None else len(ls)
        print(f"{name}: {'missing' if n is None else f'{n} lines'} · budget ({tier}): "
              f"{'≤ ' + str(hi) if hi else 'none'} · {flag(n, lo, hi)}")
        return
    D = os.path.dirname(W)
    m = re.match(r"run-(\d+)_", os.path.basename(W))
    if not m:
        sys.exit(f"not a run folder: {W}")
    k = m.group(1)
    tag = f"run{k}-"
    out = [f"# Run metrics — {os.path.basename(D)} run {k} (size tier: {tier})", "",
           "_Generated by scripts/run_metrics.py. Counts only; interpretation is the retro's job._", ""]

    # Size
    req = lines(os.path.join(W, "requirement.md")) or []
    req_n = max(len([l for l in req if l.strip() and not l.startswith("> Source:")]), 1)
    out += ["## Size", "| File | Lines | Budget |", "|---|---|---|",
            f"| requirement.md (non-empty, excl. source line) | {req_n} ({req_words(W)} words) | — |"]
    total = 0
    for name, lo, hi in LINE_BUDGETS:
        ls = lines(os.path.join(W, name))
        n = None if ls is None else len(ls)
        total += n or 0
        out.append(f"| {name} | {'—' if n is None else n} | {flag(n, lo, hi)} |")
    rounds_lines = sum(len(lines(p) or []) for p in glob.glob(os.path.join(W, "rounds", "*.md")))
    out += [f"| rounds/*.md (all) | {rounds_lines} | — |", "",
            f"Growth: {total} lines of deliverables from {req_n} requirement lines (×{total / req_n:.0f}).", ""]

    # Readability of the package (inputs for the retro's Understandability / Clarity scores)
    out += ["## Package readability (final-prd.md)"] + readability(lines(os.path.join(W, "final-prd.md"))) + [""]

    # Stories
    us = lines(os.path.join(W, "user-stories.md")) or []
    per_story, current = Counter(), None
    for l in us:
        h = re.match(r"^#{2,4}\s*(US-\d+)", l)
        if h:
            current = h.group(1)
        elif re.match(r"^#{1,2}\s", l):
            current = None
        if current and re.search(r"(Scenario( Outline)?|Scénář|Náčrt scénáře):", l):
            per_story[current] += 1
    stories = sorted({re.match(r"^#{2,4}\s*(US-\d+)", l).group(1) for l in us if re.match(r"^#{2,4}\s*US-\d+", l)})
    out += ["## Stories", f"- Stories: {len(stories)} · {flag(len(stories), *STORIES)}",
            f"- Scenarios: {sum(per_story.values())}"]
    bad = [f"{s}={per_story[s]}" for s in stories if flag(per_story[s], *SCENARIOS_PER_STORY) != "ok"]
    out.append(f"- Stories outside {SCENARIOS_PER_STORY[0]}–{SCENARIOS_PER_STORY[1]} scenarios: "
               f"{', '.join(bad) or 'none'}")
    dod = lines(os.path.join(W, "definition-of-done.md")) or []
    dod_ids = {x for l in dod for x in re.findall(r"\bDoD-\d+\b", l)}
    out += [f"- Definition of Done items: {len(dod_ids)} · {flag(len(dod_ids), *DOD_ITEMS)}", ""]

    # Debate
    out += ["## Debate", "| Round | Verdict | NEW_ISSUES | BLOCKING |", "|---|---|---|---|"]
    for p in sorted(glob.glob(os.path.join(W, "rounds", "r*-analyst.md"))):
        text = "\n".join(lines(p) or [])
        get = lambda key: (re.search(rf"^{key}:\s*(.+)$", text, re.M) or [None, "—"])[1].strip()
        rnd = re.match(r"r(\w+)-analyst", os.path.basename(p)).group(1)
        out.append(f"| {rnd} | {get('VERDICT')} | {get('NEW_ISSUES')} | {get('BLOCKING')} |")
    out.append("")

    # Decision log
    rows = log_rows(os.path.join(D, "decision-log.md"))
    mine = [r for r in rows if r["raised"].startswith(tag)]
    by_round = Counter(r["raised"][len(tag):] for r in mine)
    touched = [r for r in rows if tag in r["resolution"] or r["updated"].startswith(tag)]
    count = lambda s: sum(1 for r in touched if s in r["resolution"])
    out += ["## Decision log",
            f"- Rows in log: {len(rows)} · raised this run: {len(mine)} "
            f"({', '.join(f'{k2}: {v}' for k2, v in sorted(by_round.items()))})",
            f"- Status now: {', '.join(f'{s}: {n}' for s, n in Counter(r['status'] for r in rows).most_common())}",
            f"- Resolved as — FIX: {count('FIX:')} · ACCEPTED RISK: {count('ACCEPTED RISK')} · "
            f"PO DECISION: {count('PO DECISION')} · TECH QUESTION: {count('TECH QUESTION')}",
            f"- REOPENED: {count('REOPENED')} · NOT ADDRESSED: {count('NOT ADDRESSED')} · "
            f"COVERAGE GAP: {count('COVERAGE GAP')} · left for grooming by the PO: "
            f"{sum(1 for r in rows if r['status'].startswith('Still Open') and 'deferred to grooming by PO' in r['resolution'])}",
            ""]

    # PO interaction
    facts = lines(os.path.join(D, "confirmed-facts.md")) or []
    this_run = [l for l in facts if f"/groom run {k}," in l]
    out += ["## Product owner",
            f"- Facts confirmed this run: {len(this_run)} "
            f"(PO decisions on DL rows: {sum(1 for l in this_run if 'PO decision on DL-' in l)})", ""]

    # Run state
    try:
        with open(os.path.join(D, ".state", "run-state.json"), encoding="utf-8") as f:
            run = next((r for r in json.load(f).get("runs", []) if str(r.get("run")) == k), {})
    except (FileNotFoundError, json.JSONDecodeError):
        run = {}
    out += ["## Run", f"- Rounds: {run.get('rounds', '—')} of {MAX_ROUNDS} · final verdict: {run.get('verdict', '—')}",
            f"- Started: {run.get('started', '—')} · package written: {package_time(W)}",
            f"- PO checkpoint questions asked: {run.get('po_questions', '—')} (cap {_B['max_po_questions']}) · "
            f"at the last checkpoint before the package: {run.get('po_questions_final', 0)}"]
    warn = lines(os.path.join(D, ".state", "validation-warnings.log")) or []
    warn = [w for w in warn if f" {W} " in f" {w} " or W.split("groomed/")[-1] in w]
    out += [f"- Output-contract problems left after the retry cap: {len(warn)}", ""]

    dest = os.path.join(W, "run-metrics.md")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
