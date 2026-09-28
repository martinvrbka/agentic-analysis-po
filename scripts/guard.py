#!/usr/bin/env python3
"""PreToolUse guard for pipeline subagents.

Wired from each agent's frontmatter as `guard.py <role>`. Reads the hook payload on stdin and
blocks (exit 2) any tool call outside that role's allowlist. This is what makes the analyst's
isolation a property of the harness rather than a promise in a prompt.

Paths are matched relative to the project root with fnmatch; deny patterns win over allow patterns.
"""
import fnmatch
import json
import os
import sys

S = "groomed/*/"        # shared across runs: decision-log.md, confirmed-facts.md
R = "groomed/*/run-*/"  # one run's working folder

COMMON_READ = ["CLAUDE.md"]

ROLES = {
    "prd-drafter": {
        # Also reads the previous run's prd-draft.md in update mode (same pattern).
        "read": ["personas/prd-development/*", R + "requirement.md", S + "confirmed-facts.md",
                 R + "prd-draft.md", S + "decision-log.md"],
        "write": [R + "prd-draft.md"],
    },
    "designer": {
        "read": ["personas/design-analysis-debate/SKILL.md", R + "requirement.md", S + "confirmed-facts.md",
                 R + "prd-draft.md", S + "decision-log.md", R + "rounds/r*-analyst.md"],
        "write": [R + "prd-draft.md", R + "rounds/r*-designer-*.md"],
    },
    "analyst": {
        "read": ["personas/design-analysis-debate/SKILL.md", R + "requirement.md", S + "confirmed-facts.md",
                 R + "prd-draft.md", S + "decision-log.md"],
        "deny_read": [S + "rounds/*designer*"],
        "write": [R + "rounds/r*-analyst.md"],
    },
    "story-writer": {
        "read": ["personas/user-story/*", "personas/user-story-mapping/*", S + "confirmed-facts.md",
                 R + "prd-draft.md", S + "decision-log.md", R + "user-stories.md", R + "story-map.md",
                 R + "coverage-report*.md"],  # coverage report: revise mode only
        "write": [R + "user-stories.md", R + "story-map.md"],
    },
    "coverage-checker": {
        # Deliberately no PRD: it checks decisions against stories, not stories against intent.
        "read": ["personas/design-analysis-debate/SKILL.md", S + "decision-log.md", R + "user-stories.md",
                 R + "definition-of-done.md"],
        "write": [R + "coverage-report*.md"],  # coverage-report-1.md (first pass), coverage-report.md (final)
    },
    "packager": {
        "read": [R + "requirement.md", S + "confirmed-facts.md", R + "prd-draft.md", S + "decision-log.md",
                 R + "user-stories.md", R + "story-map.md", R + "business-case.md",
                 R + "definition-of-done.md", R + "coverage-report*.md"],
        "write": [R + "business-case.md", R + "definition-of-done.md", R + "final-prd.md"],
    },
    "retro": {
        # Runs after the package is built and sees everything, including designer rounds. Safe because no
        # other role may read retro.md, so nothing it saw flows back into the debate.
        "read": [R + "*.md", R + "rounds/*.md", S + "decision-log.md", S + "confirmed-facts.md",
                 ".claude/commands/groom.md", ".claude/agents/*.md", "personas/*"],
        "write": [R + "retro.md"],
    },
}

FILE_TOOLS = {"Read": "read", "Write": "write", "Edit": "write"}


def block(msg):
    print(f"[guard] {msg}", file=sys.stderr)
    sys.exit(2)


def rel(path, root):
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
    r = os.path.relpath(full, root)
    return None if r.startswith("..") else r.replace(os.sep, "/")


def matches(path, patterns):
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    if role not in ROLES:
        block(f"unknown role '{role}'")
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    root = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())

    mode = FILE_TOOLS.get(tool)
    if mode is None:
        block(f"{role} may only use Read/Write; '{tool}' is not permitted in this pipeline stage.")

    raw = (payload.get("tool_input") or {}).get("file_path", "")
    path = rel(raw, root)
    if path is None:
        block(f"{role} may not access paths outside the project: {raw}")

    rules = ROLES[role]
    if mode == "read":
        if matches(path, rules.get("deny_read", [])):
            block(f"{role} is isolated from '{path}'. Work only from the artifacts you were given.")
        if not matches(path, rules["read"] + COMMON_READ):
            block(f"{role} has no read access to '{path}'.")
    else:
        if not matches(path, rules["write"]):
            block(f"{role} has no write access to '{path}'. Allowed: {', '.join(rules['write'])}")
    sys.exit(0)


if __name__ == "__main__":
    main()
