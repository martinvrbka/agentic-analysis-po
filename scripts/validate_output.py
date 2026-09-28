#!/usr/bin/env python3
"""Deterministic checks on what the agents write: format contracts, size budgets, altitude lint.

Usage:
  validate_output.py --after <role> [<file> ...] [--record]
                                        The same check, run by the orchestrator after every agent (the frontmatter
                                        hook does not fire in every client). Exit 1 lists the problems for one fix
                                        round; --record writes what is still wrong to validation-warnings.log.
  validate_output.py --hook <role>      SubagentStop hook (wired as a `Stop` hook in each agent's frontmatter).
                                        Checks the file(s) that role just wrote in the active run. On failure it
                                        blocks the stop (exit 2) so the agent fixes its own output, at most
                                        `max_output_retries` times (budgets.json); after that it lets the agent stop
                                        and records the problem in <feature>/.state/validation-warnings.log.
  validate_output.py <kind> <file>      check one file; kind = analyst | designer | stories | story-map | dod |
                                        coverage | final-prd | prd | business-case | retro
  validate_output.py package <run dir>  lint a finished run: every file above plus altitude words and unlogged 🔵

Exit code 0 = no problems, 1 = problems (CLI), 2 = blocked stop (hook).
"""
import datetime
import glob
import json
import os
import re
import sys

from pipeline_common import active_run, budgets, parse_log, project_root, read_lines, split_cells, tier_budget

DIMENSIONS = ("Purpose", "Data", "Behavior", "Security", "Testability")
SEVERITIES = ("blocking", "major", "minor")
DISPOSITIONS = ("FIX", "ACCEPT-RISK", "OPEN-QUESTION", "TECH-QUESTION")
COVERAGE_RESULTS = ("COVERED", "COVERED (DoD)", "GAP", "GAP (DoD-only)",
                    "N/A — risk accepted without mitigation", "N/A — accepted by PO", "N/A — tech team")
# Words that signal technical design in product-level artifacts (CLAUDE.md "Altitude"). Warnings, not proof.
NAME = re.compile(r"^[^\W_]+(-[^\W_]+){1,5}$")  # kebab-case, 2–6 words: the row name people read
LONG_SENTENCE = 30  # words; prose written for the package reader is split above this
STOP = set("with from that this your their into over when what have been will must should than then only also "
           "each every more less other same them they which while about".split())
ALTITUDE = re.compile(r"\b(endpoints?|API|HTTP|JSON|database|SQL|replicas?|microservices?|webhooks?|"
                      r"status codes?|backend|frontend)\b", re.I)


def bullets(lines):
    return [l.strip()[2:].strip() for l in lines if l.strip().startswith("- ")]


def headings(lines):
    return [l for l in lines if l.startswith("#")]


def rows(lines):
    return [split_cells(l) for l in lines if l.startswith("|") and not re.match(r"^\|\s*-{2,}", l)]


def section(lines, title_re):
    out, inside = [], False
    for l in lines:
        if l.startswith("## "):
            if inside:
                break
            inside = bool(re.search(title_re, l[3:], re.I))
            continue
        if inside:
            out.append(l)
    return out


def budget_check(name, lines, tier):
    hi = tier_budget(tier)["lines"].get(name)
    if hi and len(lines) > hi:
        return [f"{name} is {len(lines)} lines, over the {tier} budget of {hi}. Cut detail, not whole sections."]
    return []


# ---------- per-kind checks: each returns a list of problems ----------

def check_analyst(lines, tier, name=""):
    errs = []
    for s in ("## Findings", "## Compounding risks", "## Verdict"):
        if not any(l.startswith(s) for l in lines):
            errs.append(f"missing section '{s}'")
    text = "\n".join(lines)
    verdict = re.search(r"^VERDICT:\s*(.+)$", text, re.M)
    if not verdict or verdict.group(1).strip() not in ("READY FOR GROOMING", "NEEDS ANOTHER ROUND", "BLOCKED"):
        errs.append("Verdict must have a line 'VERDICT: READY FOR GROOMING | NEEDS ANOTHER ROUND | BLOCKED'")
    new_issues = re.search(r"^NEW_ISSUES:\s*(\d+)\s*$", text, re.M)
    if not new_issues:
        errs.append("Verdict must have a line 'NEW_ISSUES: <number>'")
    if not re.search(r"^BLOCKING:\s*\S", text, re.M):
        errs.append("Verdict must have a line 'BLOCKING: <refs or none>'")
    B = tier_budget(tier)
    per_dim, counted = {}, 0
    for c in rows(section(lines, r"^Findings")):
        if not c or c[0].lower() == "ref" or c[0] in ("-", "—"):
            continue
        if len(c) != 7:
            errs.append(f"finding {c[0]}: expected 7 cells (Ref | Name | Dimension | Type | Severity | Finding | "
                        f"Evidence), got {len(c)} (escape '|' as '\\|')")
            continue
        name, c = c[1], c[:1] + c[2:]
        typ, sev = c[2], c[3].lower()
        if typ == "NEW" and not NAME.match(name):
            errs.append(f"finding {c[0]}: Name must be 2–6 lower-case words joined by '-', e.g. "
                        f"'empty-deck-message', got '{name}'")
        if not (typ == "NEW" or re.match(r"REOPEN DL-\d{3,}$", typ)):
            errs.append(f"finding {c[0]}: Type must be NEW or 'REOPEN DL-###', got '{typ}'")
        if sev not in SEVERITIES:
            errs.append(f"finding {c[0]}: Severity must be blocking, major or minor, got '{c[3]}'")
        if typ == "NEW":
            dim = next((d for d in DIMENSIONS if c[1].startswith(d)), c[1])
            per_dim[dim] = per_dim.get(dim, 0) + 1
        counted += 1
    for dim, n in per_dim.items():
        if n > B["new_per_dimension"]:
            errs.append(f"{n} NEW findings in {dim}; the {tier} budget is {B['new_per_dimension']} per dimension")
    comp = [c for c in rows(section(lines, r"^Compounding")) if c and c[0].lower() != "ref"
            and c[0] not in ("-", "—") and len(c) > 2 and c[2] not in ("-", "—")]
    if len(comp) > B["compounding"]:
        errs.append(f"{len(comp)} compounding risks; the {tier} budget is {B['compounding']}")
    for c in comp:
        if len(c) != 5 or c[4].lower() not in SEVERITIES:
            errs.append(f"compounding {c[0]}: needs 5 cells (Ref | Name | Combines | How | Severity) ending in a "
                        f"severity (blocking/major/minor)")
        elif not NAME.match(c[1]):
            errs.append(f"compounding {c[0]}: Name must be 2–6 lower-case words joined by '-', got '{c[1]}'")
    counted += len(comp)
    if new_issues and int(new_issues.group(1)) != counted:
        errs.append(f"NEW_ISSUES says {new_issues.group(1)} but the tables hold {counted} NEW/REOPEN/compounding rows")
    return errs


def check_question_blocks(lines, ids=None):
    errs, blocks, cur = [], {}, None
    for l in lines:
        m = re.match(r"^###\s+(DL-\d{3,})", l)
        if m:
            cur = m.group(1)
            blocks[cur] = []
        elif l.startswith("#"):
            cur = None
        elif cur:
            blocks[cur].append(l.strip())
    for rid in ids if ids is not None else blocks:
        b = blocks.get(rid)
        if b is None:
            errs.append(f"{rid}: OPEN-QUESTION without a '### {rid}' block under '## Questions for the PO'")
            continue
        if any(l.startswith("TECH-QUESTION:") for l in b):
            continue
        if not any(l.startswith("Question:") for l in b):
            errs.append(f"{rid}: block needs a 'Question:' line")
        opts = [re.match(r"^(\d)\.\s+(.+?)\s+—\s+(.+)$", l) for l in b if re.match(r"^\d\.", l)]
        if not 2 <= len(opts) <= 3 or not all(opts):
            errs.append(f"{rid}: needs 2–3 options written '<n>. <label> — <consequence>'")
        for o in filter(None, opts):
            if len(o.group(2).split()) > 5:
                errs.append(f"{rid}: option {o.group(1)} label '{o.group(2)}' is longer than 5 words")
        rec = next((re.match(r"Recommended:\s*(\d)\s+—\s+\S", l) for l in b if l.startswith("Recommended:")), None)
        if not rec or not any(o and o.group(1) == rec.group(1) for o in opts):
            errs.append(f"{rid}: needs 'Recommended: <option number> — <reason>' naming an existing option")
        if not any(l.startswith("Combinable:") for l in b):
            errs.append(f"{rid}: needs a 'Combinable: yes|no' line")
        header = next((l.split(":", 1)[1].strip() for l in b if l.startswith("Header:")), None)
        if not header or len(header) > 12:
            errs.append(f"{rid}: needs a 'Header: <topic in ≤ 12 characters>' line (the chip the PO sees)")
    return errs


def check_designer(lines, tier, name=""):
    if "proposal" in name:
        return [f"{name} is {len(lines)} lines; the proposal is ≤ 30"] if len(lines) > 30 else []
    if "apply" in name:
        ok = any(l.startswith("|") and "Follow-on edits" in l for l in lines)
        return [] if ok else ["apply table must have the header '| DL id | PRD section | Follow-on edits |'"]
    if "options" in name:
        return check_question_blocks(lines) or ([] if any(l.startswith("### DL-") for l in lines)
                                                else ["no '### DL-###' blocks found"])
    errs, open_q = [], []
    table = [c for c in rows(lines) if c and re.match(r"DL-\d{3,}$", c[0])]
    if not table:
        errs.append("no response table rows ('| DL-### | <disposition> | <resolution> | <PRD section> |')")
    for c in table:
        if len(c) != 4:
            errs.append(f"{c[0]}: expected 4 cells, got {len(c)}")
        elif c[1] not in DISPOSITIONS:
            errs.append(f"{c[0]}: disposition must be one of {', '.join(DISPOSITIONS)}, got '{c[1]}'")
        elif c[1] == "OPEN-QUESTION":
            open_q.append(c[0])
    return errs + check_question_blocks(lines, open_q)


def check_stories(lines, tier, name="user-stories.md"):
    B = tier_budget(tier)
    errs = budget_check("user-stories.md", lines, tier)
    stories, cur = {}, None
    for l in lines:
        m = re.match(r"^#{2,4}\s*(US-\d+)", l)
        if m:
            cur = m.group(1)
            stories[cur] = {"scen": 0, "invest": False, "covers": False, "slice": False}
        elif l.startswith("## "):
            cur = None
        elif cur:
            s = stories[cur]
            s["scen"] += bool(re.search(r"Scenario( Outline)?:", l))
            s["invest"] |= "INVEST:" in l
            s["covers"] |= "Covers:" in l
            s["slice"] |= bool(re.match(r"^\s*Slice:\s*\S", l))
    lo, hi = B["stories"]
    if not lo <= len(stories) <= hi:
        errs.append(f"{len(stories)} stories; the {tier} range is {lo}–{hi}")
    slo, shi = B["scenarios"]
    for sid, s in stories.items():
        if not slo <= s["scen"] <= shi:
            errs.append(f"{sid} has {s['scen']} scenarios; the {tier} range is {slo}–{shi}")
        if not s["invest"]:
            errs.append(f"{sid} has no 'INVEST:' line")
        if not s["covers"]:
            errs.append(f"{sid} has no 'Covers:' line")
        if not s["slice"]:
            errs.append(f"{sid} has no 'Slice:' line (Walking skeleton, Hardening or Edge cases & polish)")
    return errs


def check_dod(lines, tier, name=""):
    ids = set(re.findall(r"DoD-\d+", "\n".join(lines)))
    lo, hi = tier_budget(tier)["dod"]
    return [] if lo <= len(ids) <= hi else [f"{len(ids)} DoD items; the {tier} range is {lo}–{hi}"]


def check_coverage(lines, tier, name=""):
    errs = [f"missing section '{s}'" for s in ("## Decision coverage", "## Gaps to reopen", "## Vague acceptance",
                                                 "## Implementation detail", "## DoD / AC separation")
            if not any(l.startswith(s) for l in lines)]
    for c in rows(section(lines, r"Decision coverage")):
        if c and re.match(r"DL-\d{3,}$", c[0]) and c[-1] not in COVERAGE_RESULTS:
            errs.append(f"{c[0]}: Result '{c[-1]}' is not one of {', '.join(COVERAGE_RESULTS)}")
    return errs


def check_final(lines, tier, name=""):
    errs = budget_check("final-prd.md", lines, tier)
    for n in range(12):
        if not any(re.match(rf"^## {n}\.", l) for l in lines):
            errs.append(f"missing section '## {n}.'")
    return errs


def long_sentences(lines):
    """Prose sentences over LONG_SENTENCE words (tables, headings and code are skipped; each line ends a sentence)."""
    out = []
    for l in lines:
        if not l.strip() or l.startswith(("|", "#", "```")):
            continue
        t = re.sub(r"[*_`>]", "", l).strip().lstrip("- ").strip()
        out += [x for x in re.split(r"(?<=[.!?])\s+", t) if len(x.split()) > LONG_SENTENCE]
    return out


def check_summary(lines, tier, name=""):
    errs = budget_check("package-summary.md", lines, tier)
    if not any(l.startswith("# ") for l in lines):
        errs.append("needs a '# <Feature>' title line")
    for n in range(3):
        if not any(re.match(rf"^## {n}\.", l) for l in lines):
            errs.append(f"missing section '## {n}.'")
    errs += [f"sentence over {LONG_SENTENCE} words, split it or make it a list: '{x[:70]}…'"
             for x in long_sentences(lines)]
    return errs


def check_business_case(lines, tier, name=""):
    return budget_check("business-case.md", lines, tier) + [
        f"sentence over {LONG_SENTENCE} words, split it: '{x[:70]}…'" for x in long_sentences(lines)]


def check_prd(lines, tier, name=""):
    errs = budget_check("prd-draft.md", lines, tier)
    if not any(re.match(r"^## 10\.", l) for l in lines):
        errs.append("missing '## 10. Open Questions'")
    if not any(l.startswith("### Terms") for l in lines):
        errs.append("missing '### Terms' at the end of §5 (≤ 8 words with their meaning)")
    return errs


def check_simple(file_name):
    return lambda lines, tier, name="": budget_check(file_name, lines, tier)


SCORE_METRICS = ("Understandability", "Clarity", "Completeness", "Testability", "Proportion", "Product focus")


def check_retro(lines, tier, name=""):
    errs = budget_check("retro.md", lines, tier)
    errs += [f"missing section '{s}'" for s in ("## Scorecard", "## A. Package", "## B. Recommendations")
             if not any(l.startswith(s) for l in lines)]
    scored = {c[0]: c[1] for c in rows(section(lines, r"^Scorecard")) if len(c) >= 3}
    for m in SCORE_METRICS:
        if not re.match(r"^[1-5]$", scored.get(m, "").strip()):
            errs.append(f"Scorecard needs a row '| {m} | <1–5> | <evidence> |'")
    if not any(l.startswith("Trend:") for l in section(lines, r"^Scorecard")):
        errs.append("Scorecard needs a 'Trend:' line")
    return errs


KINDS = {"analyst": check_analyst, "designer": check_designer, "stories": check_stories,
         "story-map": check_simple("story-map.md"), "dod": check_dod, "coverage": check_coverage,
         "final-prd": check_final, "prd": check_prd, "business-case": check_business_case,
         "package-summary": check_summary, "retro": check_retro}
KIND_OF_FILE = {"prd-draft.md": "prd", "user-stories.md": "stories", "story-map.md": "story-map",
                "definition-of-done.md": "dod", "final-prd.md": "final-prd", "business-case.md": "business-case",
                "package-summary.md": "package-summary", "retro.md": "retro"}


# ---------- which files a role produced ----------

def newest(pattern):
    files = glob.glob(pattern)
    return max(files, key=os.path.getmtime) if files else None


def role_targets(role, W):
    """(kind, path) pairs to check when `role` stops."""
    j = lambda *a: os.path.join(W, *a)
    if role == "analyst":
        return [("analyst", newest(j("rounds", "r*-analyst.md")))]
    if role == "designer":
        return [("designer", newest(j("rounds", "r*-designer-*.md"))), ("prd", j("prd-draft.md"))]
    if role == "prd-drafter":
        return [("prd", j("prd-draft.md"))]
    if role == "story-writer":
        return [("stories", j("user-stories.md")), ("story-map", j("story-map.md"))]
    if role == "coverage-checker":
        return [("coverage", newest(j("coverage-report*.md")))]
    if role == "packager":
        return [("business-case", j("business-case.md")), ("dod", j("definition-of-done.md")),
                ("package-summary", j("package-summary.md"))]
    if role == "retro":
        return [("retro", j("retro.md"))]
    return []


def run_checks(targets, tier):
    problems = []
    for kind, path in targets:
        if not path or not os.path.exists(path):
            continue
        errs = KINDS[kind](read_lines(path), tier, os.path.basename(path))
        problems += [f"{os.path.basename(path)}: {e}" for e in errs]
    return problems


def package_lint(W, tier):
    j = lambda *a: os.path.join(W, *a)
    targets = [("prd", j("prd-draft.md")), ("stories", j("user-stories.md")), ("story-map", j("story-map.md")),
               ("business-case", j("business-case.md")), ("dod", j("definition-of-done.md")),
               ("final-prd", j("final-prd.md")), ("coverage", j("coverage-report.md")),
               ("package-summary", j("package-summary.md"))]
    targets += [("analyst", f) for f in sorted(glob.glob(j("rounds", "r*-analyst.md")))]
    targets += [("designer", f) for f in sorted(glob.glob(j("rounds", "r*-designer-*.md")))]
    problems = run_checks(targets, tier)
    for name in ("user-stories.md", "final-prd.md"):
        for n, l in enumerate(read_lines(j(name)) or [], 1):
            for m in ALTITUDE.finditer(l):
                problems.append(f"{name}:{n}: technical word '{m.group(0)}' (altitude, CLAUDE.md) — check it")
    problems += consistency(W, tier)
    log_rows, _ = parse_log(os.path.join(os.path.dirname(W.rstrip("/")), "decision-log.md"))
    logged = " ".join(r["issue"] for r in log_rows)
    for n, l in enumerate(read_lines(j("user-stories.md")) or [], 1):
        if "🔵" in l and l.strip().lstrip("-* ").strip()[:60] not in logged:
            problems.append(f"user-stories.md:{n}: 🔵 open question not in the decision log")
    return problems


def consistency(W, tier):
    """Cross-file checks: story ids vs story map, Covers ids vs the log, Later items vs stories."""
    j = lambda *a: os.path.join(W, *a)
    problems = []
    stories = read_lines(j("user-stories.md")) or []
    ids = {m.group(1): m.group(2).strip() for l in stories for m in [re.match(r"^#{2,4}\s*(US-\d+)[:\s]*(.*)$", l)] if m}
    story_map = read_lines(j("story-map.md"))
    if story_map is not None:
        in_map = set(re.findall(r"US-\d+", "\n".join(story_map)))
        problems += [f"story-map.md: {i} is a story but not in the map" for i in sorted(set(ids) - in_map)]
        problems += [f"story-map.md: {i} is in the map but has no story" for i in sorted(in_map - set(ids))]
    elif tier == "standard" and ids:
        problems.append("story-map.md is missing (required in tier standard)")
    log_rows, _ = parse_log(os.path.join(os.path.dirname(W.rstrip("/")), "decision-log.md"))
    known = {r["id"] for r in log_rows}
    for n, l in enumerate(stories, 1):
        if "Covers:" in l:
            problems += [f"user-stories.md:{n}: Covers {i} is not in the decision log"
                         for i in re.findall(r"DL-\d{3,}", l) if i not in known]
    later = [re.sub(r"[*_`]", "", b).lower() for b in
             bullets(section(read_lines(j("prd-draft.md")) or [], r"^8\b|Out of Scope"))]
    problems += consistency_later(ids, later)
    problems += wording(read_lines(j("prd-draft.md")) or [], stories, log_rows)
    return problems


def consistency_later(ids, later):
    """Stories whose title reads like a PRD §8 Later/Out item. At least 3 shared words (not everyday ones like
    'with'): two shared domain words such as 'hide recipes' flagged unrelated stories."""
    problems = []
    for sid, title in ids.items():
        words = set(re.findall(r"\w{4,}", title.lower())) - STOP
        for b in later:
            overlap = words & (set(re.findall(r"\w{4,}", b.lower())) - STOP)
            if len(overlap) >= max(3, round(len(words) * 0.7)):
                problems.append(f"{sid} '{title}' looks like a Later/Out-of-scope item in PRD §8: '{b[:60]}'")
                break
    return problems


QUOTE = re.compile(r"[\"“„]([^\"“”„]{8,}?)[\"”“]")


def norm(t):
    return " ".join(re.sub(r"[\"“”„'’‘.,!?…:;]", " ", t).lower().split())


def wording(prd, stories, log_rows):
    """Exact wording must survive: a message quoted in a PO decision appears in the PRD, and a message quoted in
    the stories appears in the PRD too (the PRD is where wording is decided; stories copy it)."""
    problems, text = [], norm(" ".join(prd))
    for r in log_rows:
        res = r["resolution"].split(" · prev:")[0]
        if not res.startswith("PO DECISION:"):
            continue
        for m in QUOTE.finditer(res):
            before = res[max(0, m.start() - 8):m.start()].lower()
            if len(m.group(1).split()) >= 4 and "e.g" not in before and norm(m.group(1)) not in text:
                problems.append(f"{r['id']}: the PO chose the wording \"{m.group(1)}\" but prd-draft.md words it "
                                f"differently")
    for n, l in enumerate(stories, 1):
        for m in QUOTE.finditer(l):
            q = m.group(1)
            if len(q.split()) >= 4 and re.search(r"[.!?…]\s*$", q) and norm(q) not in text:
                problems.append(f"user-stories.md:{n}: message \"{q[:60]}\" is not worded like this in prd-draft.md")
    return problems


def tier_for(W):
    try:
        with open(os.path.join(os.path.dirname(W.rstrip("/")), ".state", "run-state.json"), encoding="utf-8") as f:
            for r in json.load(f)["runs"]:
                if r["folder"].rstrip("/") == W.rstrip("/").replace(project_root() + "/", ""):
                    return r["size"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass
    words = sum(len(l.split()) for l in read_lines(os.path.join(W, "requirement.md")) or []
                if not l.startswith("> Source:"))
    return "small" if words <= budgets()["small_max_words"] else "standard"


def hook(role):
    payload = json.load(sys.stdin)
    root = project_root(payload)
    run = active_run(root)
    if not run:
        sys.exit(0)
    problems = run_checks(role_targets(role, os.path.join(root, run["run"])), run["tier"])
    if not problems:
        sys.exit(0)
    state = os.path.join(root, run["feature"], ".state")
    retries_file = os.path.join(state, "output-retries.json")
    try:
        with open(retries_file, encoding="utf-8") as f:
            retries = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        retries = {}
    key = payload.get("agent_id") or f"{payload.get('session_id')}:{role}"
    used = retries.get(key, 0)
    if used < budgets()["max_output_retries"]:
        retries[key] = used + 1
        with open(retries_file, "w", encoding="utf-8") as f:
            json.dump(retries, f, indent=1)
        print("[validate] Your output does not meet the pipeline contract. Fix these, then stop again:\n  - "
              + "\n  - ".join(problems), file=sys.stderr)
        sys.exit(2)
    with open(os.path.join(state, "validation-warnings.log"), "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {run['run']} {role}: "
                + " | ".join(problems) + "\n")
    print("[validate] retry cap reached; problems recorded in validation-warnings.log", file=sys.stderr)
    sys.exit(0)


def after(role, files, record):
    """Orchestrator-side check after an agent finished: the same contract as the Stop hook."""
    root = project_root()
    run = active_run(root) or sys.exit("no active run")
    W = os.path.join(root, run["run"])
    targets = [(KIND_OF_FILE[os.path.basename(f)] if os.path.basename(f) in KIND_OF_FILE else
                "analyst" if f.endswith("-analyst.md") else "designer", os.path.join(W, f)) for f in files] \
        if files else role_targets(role, W)
    problems = run_checks(targets, run["tier"])
    if problems and record:
        with open(os.path.join(root, run["feature"], ".state", "validation-warnings.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {run['run']} {role}: "
                    + " | ".join(problems) + "\n")
    print("\n".join(problems) if problems else "OK")
    sys.exit(1 if problems else 0)


def main():
    a = sys.argv[1:]
    if a[:1] == ["--hook"] and len(a) == 2:
        hook(a[1])
    if a[:1] == ["--after"] and len(a) >= 2:
        after(a[1], [x for x in a[2:] if x != "--record"], "--record" in a)
    if len(a) == 2 and a[0] == "package":
        W = a[1].rstrip("/")
        problems = package_lint(W, tier_for(W))
    elif len(a) == 2 and a[0] in KINDS:
        W = os.path.dirname(os.path.abspath(a[1]))
        W = os.path.dirname(W) if os.path.basename(W) == "rounds" else W
        problems = [f"{os.path.basename(a[1])}: {e}"
                    for e in KINDS[a[0]](read_lines(a[1]) or [], tier_for(W), os.path.basename(a[1]))]
    else:
        print(__doc__)
        sys.exit(1)
    print("\n".join(problems) if problems else "OK")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
