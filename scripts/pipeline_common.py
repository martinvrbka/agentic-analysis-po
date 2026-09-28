"""Shared helpers for the /groom scripts: budgets, the active-run pointer, decision-log parsing, path matching.

Imported by guard.py, check_decision_log.py, dl.py, validate_output.py and run_metrics.py
(they run as `python3 scripts/<name>.py`, so this directory is on sys.path).
"""
import fnmatch
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BUDGETS_FILE = os.path.join(HERE, "budgets.json")
ACTIVE_NAME = os.path.join("groomed", ".active-run.json")

STATUSES = ("Resolved", "Still Open", "Still Open (BLOCKING)", "Tech team")
ROW = re.compile(r"^\|\s*(DL-\d{3,})\s*\|")
CELL_SEP = re.compile(r"(?<!\\)\|")  # "|" not preceded by a backslash
FIELDS = ("id", "name", "issue", "raised", "status", "resolution", "updated")
OLD_FIELDS = ("id", "issue", "raised", "status", "resolution", "updated")  # logs written before rows had a Name
STOPWORDS = set("""a an the and or but if of to in on at by for from with without into onto over under than then
that this these those is are was were be been being it its as not no do does did can could should would will may
must what which who whom whose when where why how all any each every both either neither our their your my his her
we you they he she i me us them there here also only just still even more most less least very same other such
per via about after before while during between against because so too up down out off again once""".split())


def budgets():
    with open(BUDGETS_FILE, encoding="utf-8") as f:
        return json.load(f)


def tier_budget(tier):
    return budgets()["tiers"][tier]


def project_root(payload=None):
    return os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR") or (payload or {}).get("cwd") or os.getcwd())


def active_run(root):
    """The run the orchestrator pinned with `dl.py start`, or None. Paths in it are relative to the project root."""
    try:
        with open(os.path.join(root, ACTIVE_NAME), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def path_match(path, pattern):
    """Glob match where `*` never crosses a `/` (plain fnmatch lets `groomed/*/x` match any depth)."""
    ps, qs = path.split("/"), pattern.split("/")
    return len(ps) == len(qs) and all(fnmatch.fnmatchcase(p, q) for p, q in zip(ps, qs))


def split_cells(line):
    return [c.strip() for c in CELL_SEP.split(line.strip())[1:-1]]


def esc(text):
    """Make text safe for one markdown table cell."""
    return re.sub(r"(?<!\\)\|", r"\\|", " ".join(str(text).split()))


def parse_log(path):
    """Return (rows as dicts in file order, errors)."""
    rows, errors, seen = [], [], set()
    try:
        f = open(path, encoding="utf-8")
    except FileNotFoundError:
        return [], []
    with f:
        fields = FIELDS
        for n, line in enumerate(f, 1):
            if re.match(r"^\|\s*ID\s*\|", line):  # the header says which layout this log uses
                fields = FIELDS if "Name" in split_cells(line) else OLD_FIELDS
                continue
            if not ROW.match(line):
                continue
            cells = split_cells(line)
            if len(cells) != len(fields):
                errors.append(f"line {n}: expected {len(fields)} cells, got {len(cells)} "
                              f"(escape '|' inside cells as '\\|')")
                continue
            r = dict(zip(fields, cells))
            r.setdefault("name", "")
            if r["id"] in seen:
                errors.append(f"line {n}: duplicate id {r['id']}")
            seen.add(r["id"])
            if not r["issue"]:
                errors.append(f"line {n}: {r['id']} has an empty Question/Issue")
            if r["status"] not in STATUSES:
                errors.append(f"line {n}: {r['id']} status '{r['status']}' not in {STATUSES}")
            rows.append(r)
    return rows, errors


def row_line(r):
    return "| " + " | ".join(r.get(k, "") for k in FIELDS) + " |"


def slug(text, max_words=5, max_len=40):
    """Kebab-case label: lower case, words joined by '-', at most max_words words and max_len characters."""
    words = re.findall(r"\w+", text.lower().replace("_", " "))
    out = ""
    for w in words[:max_words]:
        if len(out) + len(w) + 1 > max_len:
            break
        out = f"{out}-{w}" if out else w
    return out


def auto_name(issue):
    """A descriptive name made from a row's text, for rows nobody named (script-made rows, older logs)."""
    text = re.sub(r"^(\[[^\]]*\]\s*)+", "", issue)  # leading tags like [Data] [UNVERIFIED-SOURCE]
    words = [w for w in re.findall(r"[^\W\d_]{3,}", text.lower()) if w not in STOPWORDS]
    return slug(" ".join(words), max_words=4) or "unnamed"


def display(r):
    """`DL-007 do-not-eat-blocks-matches`: the id scripts use, plus the name people read."""
    return f"{r['id']} {r.get('name') or auto_name(r['issue'])}"


def read_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()
    except FileNotFoundError:
        return None
