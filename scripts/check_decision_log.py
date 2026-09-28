#!/usr/bin/env python3
"""Validate a decision-log.md and enforce that rows are never dropped.

Usage:
  check_decision_log.py <decision-log.md>            validate, compare with snapshot, update snapshot
  check_decision_log.py <decision-log.md> --summary  print status counts (no snapshot change)
  check_decision_log.py <decision-log.md> --next-id  print the next free DL-### id
  check_decision_log.py --hook                       PostToolUse mode: payload on stdin

Rules:
  - every row has 7 cells: ID | Name | Question/Issue | Raised in | Status | Resolution | Last updated
    (logs from before rows had a Name have 6 cells; dl.py adds the column on its next write)
  - IDs are unique and look like DL-###
  - Status is one of STATUSES
  - every ID in the snapshot still exists, and its Question/Issue text is unchanged
    (status and resolution may change; the issue itself may not be reworded away)
  - a row's Name, once set, is not changed either (an older row may get its first name)
The snapshot lives in <feature>/.state/decision-log.snapshot.json and only advances after a valid write.

Hook mode checks the file for Write/Edit on a decision-log.md, and for Bash it checks the active run's log
(a shell command can change the log without naming it, so every Bash call is followed by a check).
"""
import json
import os
import sys
from collections import Counter

from pipeline_common import STATUSES, active_run, parse_log, project_root  # noqa: F401  (STATUSES re-exported)


def snapshot_path(log_path):
    return os.path.join(os.path.dirname(os.path.abspath(log_path)), ".state", "decision-log.snapshot.json")


def check(log_path, update=True):
    rows, errors = parse_log(log_path)
    by_id = {r["id"]: r for r in rows}
    snap_file = snapshot_path(log_path)
    if os.path.exists(snap_file):
        with open(snap_file, encoding="utf-8") as f:
            snap = json.load(f)
        for rid, name in snap.get("_names", {}).items():
            if rid in by_id and by_id[rid]["name"] != name:
                errors.append(f"{rid} Name changed from '{name}' to '{by_id[rid]['name']}'. Names are stable; keep it.")
        for rid, issue in snap.items():
            if rid.startswith("_"):
                continue
            if rid not in by_id:
                errors.append(f"{rid} was deleted. Rows may change status but must never disappear. Restore it.")
            elif by_id[rid]["issue"] != issue:
                errors.append(f"{rid} Question/Issue text changed. Keep the original text; put updates in Resolution.\n"
                              f"    was: {issue}\n    now: {by_id[rid]['issue']}")
    if errors or not update:
        return errors
    os.makedirs(os.path.dirname(snap_file), exist_ok=True)
    with open(snap_file, "w", encoding="utf-8") as f:
        snap = {r["id"]: r["issue"] for r in rows}
        snap["_names"] = {r["id"]: r["name"] for r in rows if r["name"]}
        json.dump(snap, f, ensure_ascii=False, indent=1)
    return []


def summary(log_path):
    rows, _ = parse_log(log_path)
    c = Counter(r["status"] for r in rows)
    return (f"{len(rows)} rows: {c['Resolved']} Resolved, {c['Still Open']} Still Open, "
            f"{c['Still Open (BLOCKING)']} BLOCKING, {c['Tech team']} for tech team")


def next_id(log_path):
    rows, _ = parse_log(log_path)
    n = max((int(r["id"][3:]) for r in rows), default=0) + 1
    return f"DL-{n:03d}"


def hook_target(payload):
    tool = payload.get("tool_name", "")
    if tool in ("Write", "Edit"):
        path = (payload.get("tool_input") or {}).get("file_path", "")
        return path if os.path.basename(path) == "decision-log.md" else None
    if tool == "Bash":
        root = project_root(payload)
        run = active_run(root)
        if run:
            path = os.path.join(root, run["feature"], "decision-log.md")
            return path if os.path.exists(path) else None
    return None


def main():
    args = sys.argv[1:]
    if args[:1] == ["--hook"]:
        path = hook_target(json.load(sys.stdin))
        if not path:
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
