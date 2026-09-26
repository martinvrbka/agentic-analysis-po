#!/usr/bin/env python3
"""Validate a decision-log.md and enforce that rows are never dropped.

Usage:
  check_decision_log.py <decision-log.md>            validate, compare with snapshot, update snapshot
  check_decision_log.py <decision-log.md> --summary  print status counts (no snapshot change)
  check_decision_log.py <decision-log.md> --next-id  print the next free DL-### id
  check_decision_log.py --hook                       PostToolUse mode: payload on stdin, acts only on decision-log.md

Rules:
  - every row has 6 cells: ID | Question/Issue | Raised in | Status | Resolution | Last updated
  - IDs are unique and look like DL-###
  - Status is one of STATUSES
  - every ID in the snapshot still exists, and its Question/Issue text is unchanged
    (status and resolution may change; the issue itself may not be reworded away)
The snapshot lives in <feature>/.state/decision-log.snapshot.json and only advances after a valid write.
"""
import json
import os
import re
import sys
from collections import Counter

STATUSES = ("Resolved", "Still Open", "Still Open (BLOCKING)")
ROW = re.compile(r"^\|\s*(DL-\d{3,})\s*\|")
CELL_SEP = re.compile(r"(?<!\\)\|")  # "|" not preceded by a backslash


def parse(path):
    rows, errors = {}, []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not ROW.match(line):
                continue
            cells = [c.strip() for c in CELL_SEP.split(line.strip())[1:-1]]
            if len(cells) != 6:
                errors.append(f"line {n}: expected 6 cells, got {len(cells)} (escape '|' inside cells as '\\|')")
                continue
            rid, issue, raised, status, resolution, updated = cells
            if rid in rows:
                errors.append(f"line {n}: duplicate id {rid}")
            if not issue:
                errors.append(f"line {n}: {rid} has an empty Question/Issue")
            if status not in STATUSES:
                errors.append(f"line {n}: {rid} status '{status}' not in {STATUSES}")
            rows[rid] = {"issue": issue, "status": status}
    return rows, errors


def snapshot_path(log_path):
    return os.path.join(os.path.dirname(os.path.abspath(log_path)), ".state", "decision-log.snapshot.json")


def check(log_path):
    rows, errors = parse(log_path)
    snap_file = snapshot_path(log_path)
    if os.path.exists(snap_file):
        with open(snap_file, encoding="utf-8") as f:
            snap = json.load(f)
        for rid, issue in snap.items():
            if rid not in rows:
                errors.append(f"{rid} was deleted. Rows may change status but must never disappear. Restore it.")
            elif rows[rid]["issue"] != issue:
                errors.append(f"{rid} Question/Issue text changed. Keep the original text; put updates in Resolution.\n"
                              f"    was: {issue}\n    now: {rows[rid]['issue']}")
    if errors:
        return errors
    os.makedirs(os.path.dirname(snap_file), exist_ok=True)
    with open(snap_file, "w", encoding="utf-8") as f:
        json.dump({rid: r["issue"] for rid, r in rows.items()}, f, ensure_ascii=False, indent=1)
    return []


def summary(log_path):
    rows, _ = parse(log_path)
    c = Counter(r["status"] for r in rows.values())
    return (f"{len(rows)} rows: {c['Resolved']} Resolved, {c['Still Open']} Still Open, "
            f"{c['Still Open (BLOCKING)']} BLOCKING")


def next_id(log_path):
    rows, _ = parse(log_path) if os.path.exists(log_path) else ({}, [])
    n = max((int(r[3:]) for r in rows), default=0) + 1
    return f"DL-{n:03d}"


def main():
    args = sys.argv[1:]
    if args[:1] == ["--hook"]:
        payload = json.load(sys.stdin)
        path = (payload.get("tool_input") or {}).get("file_path", "")
        if os.path.basename(path) != "decision-log.md":
            sys.exit(0)
        errors = check(path)
        if errors:
            print("[decision-log] write rejected:\n  " + "\n  ".join(errors), file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    if not args:
        print(__doc__)
        sys.exit(1)
    log = args[0]
    if "--summary" in args:
        print(summary(log))
    elif "--next-id" in args:
        print(next_id(log))
    else:
        errors = check(log)
        print("\n".join(errors) if errors else "OK — " + summary(log))
        sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
