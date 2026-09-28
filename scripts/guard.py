#!/usr/bin/env python3
"""PreToolUse guard for pipeline subagents.

Wired from each agent's frontmatter as `guard.py <role>`. Reads the hook payload on stdin and
blocks (exit 2) any tool call outside that role's allowlist. This is what makes the analyst's
isolation a property of the harness rather than a promise in a prompt.

Patterns are pinned to the run the orchestrator started with `dl.py start` (groomed/.active-run.json):
{D} = that feature's folder, {W} = that run's folder, {P} = the previous run's folder (re-runs only).
Other features, archived runs and older runs are therefore out of reach. `*` never crosses a `/`.
Deny patterns win over allow patterns. Without an active run, agents may read only personas and CLAUDE.md.

`guard.py --auto` is the same guard for a project-level PreToolUse hook in .claude/settings.json: it takes the role
from the hook payload's `agent_type` and allows everything that is not one of the pipeline agents (the main
session, other agents). Some clients do not run hooks declared in an agent's frontmatter; this one they do run.
"""
import json
import os
import sys

from pipeline_common import active_run, path_match, project_root

COMMON_READ = ["CLAUDE.md", "context/product-context.md"]  # product-wide facts the PO maintains by hand

ROLES = {
    "prd-drafter": {
        "read": ["personas/prd-development/*", "personas/prd-development/*/*", "{W}/requirement.md",
                 "{D}/confirmed-facts.md", "{W}/prd-draft.md", "{D}/decision-log.md", "{P}/prd-draft.md"],
        "write": ["{W}/prd-draft.md"],
    },
    "designer": {
        "read": ["personas/design-analysis-debate/SKILL.md", "{W}/requirement.md", "{D}/confirmed-facts.md",
                 "{W}/prd-draft.md", "{D}/decision-log.md", "{W}/rounds/r*-analyst.md",
                 "{W}/user-stories.md"],  # final checkpoint: questions about stories need the story text
        "write": ["{W}/prd-draft.md", "{W}/rounds/r*-designer-*.md"],
    },
    "analyst": {
        "read": ["personas/design-analysis-debate/SKILL.md", "{W}/requirement.md", "{D}/confirmed-facts.md",
                 "{W}/prd-draft.md", "{D}/decision-log.md"],
        "deny_read": ["{W}/rounds/*designer*"],
        "write": ["{W}/rounds/r*-analyst.md"],
    },
    "story-writer": {
        "read": ["personas/user-story/*", "personas/user-story/*/*", "personas/user-story-mapping/*",
                 "personas/user-story-mapping/*/*", "{D}/confirmed-facts.md", "{W}/prd-draft.md",
                 "{D}/decision-log.md", "{W}/user-stories.md", "{W}/story-map.md",
                 "{W}/coverage-report*.md",  # revise mode only
                 "{P}/user-stories.md"],
        "write": ["{W}/user-stories.md", "{W}/story-map.md"],
    },
    "coverage-checker": {
        # Deliberately no PRD: it checks decisions against stories, not stories against intent.
        "read": ["personas/design-analysis-debate/SKILL.md", "{D}/decision-log.md", "{W}/user-stories.md",
                 "{W}/definition-of-done.md",
                 "{W}/coverage-report-1.md"],  # recheck mode: its own first report
        "write": ["{W}/coverage-report*.md"],  # coverage-report-1.md (first pass), coverage-report.md (final)
    },
    "packager": {
        "read": ["{W}/requirement.md", "{D}/confirmed-facts.md", "{W}/prd-draft.md", "{D}/decision-log.md",
                 "{W}/user-stories.md", "{W}/story-map.md", "{W}/business-case.md",
                 "{W}/definition-of-done.md", "{W}/coverage-report*.md",
                 "{W}/readiness.md", "{W}/po-decisions.md", "{W}/slices.md",  # written by dl.py package-parts
                 "{W}/package-summary.md"],
        # final-prd.md is assembled by `dl.py assemble`; the packager writes only its summary sections
        "write": ["{W}/business-case.md", "{W}/definition-of-done.md", "{W}/package-summary.md"],
    },
    "retro": {
        # Runs after the package is built and sees everything of this run, including designer rounds. Safe because
        # no other role may read retro.md, so nothing it saw flows back into the debate.
        "read": ["{W}/*.md", "{W}/rounds/*.md", "{D}/decision-log.md", "{D}/confirmed-facts.md", "{P}/retro.md",
                 ".claude/commands/groom.md", ".claude/agents/*.md", "CHANGELOG.md", "groomed/scorecard.csv",
                 "personas/*", "personas/*/*", "personas/*/*/*"],
        "write": ["{W}/retro.md"],
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


def expand(patterns, run):
    """Fill {D}/{W}/{P} from the active run; drop patterns whose placeholder is unset."""
    subs = {"{D}": (run or {}).get("feature"), "{W}": (run or {}).get("run"), "{P}": (run or {}).get("prev")}
    out = []
    for p in patterns:
        for key, val in subs.items():
            if key in p:
                p = p.replace(key, val.rstrip("/")) if val else None
                if p is None:
                    break
        if p:
            out.append(p)
    return out


def decide(role, tool, file_path, root):
    """Return None if allowed, else the reason it is blocked. Pure, so tests can call it directly."""
    if role not in ROLES:
        return f"unknown role '{role}'"
    mode = FILE_TOOLS.get(tool)
    if mode is None:
        return f"{role} may only use Read/Write/Edit; '{tool}' is not permitted in this pipeline stage."
    path = rel(file_path, root)
    if path is None:
        return f"{role} may not access paths outside the project: {file_path}"
    run = active_run(root)
    rules = ROLES[role]
    if mode == "read":
        if any(path_match(path, p) for p in expand(rules.get("deny_read", []), run)):
            return f"{role} is isolated from '{path}'. Work only from the artifacts you were given."
        if not any(path_match(path, p) for p in expand(rules["read"], run) + COMMON_READ):
            hint = "" if run else " (no active run: the orchestrator must run `dl.py start` first)"
            return f"{role} has no read access to '{path}'{hint}."
    else:
        allowed = expand(rules["write"], run)
        if not any(path_match(path, p) for p in allowed):
            return f"{role} has no write access to '{path}'. Allowed: {', '.join(allowed) or 'nothing (no active run)'}"
    return None


def main():
    role = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = json.load(sys.stdin)
    if role == "--auto":
        role = payload.get("agent_type") or ""
        if role not in ROLES:
            sys.exit(0)
    root = project_root(payload)
    reason = decide(role, payload.get("tool_name", ""), (payload.get("tool_input") or {}).get("file_path", ""), root)
    if reason:
        block(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
