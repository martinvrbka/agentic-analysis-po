#!/usr/bin/env python3
"""Deterministic bookkeeping for the /groom orchestrator: run setup, run state, decision log, confirmed facts.

The orchestrator transcribes agent output through these commands instead of editing files by hand. Every
decision-log write is validated by check_decision_log.check() and rolled back if it is invalid.
All commands act on the active run pinned by `start` (groomed/.active-run.json).

  start <requirement.md> <slug> [--resume|--new] [--lang cs|en]
                                                   create or resume a run, pin it, print k / W / P / tier / language
                                                   and whether the requirement changed since the previous run
  state stage=<n> | rounds=<n> | verdict=<text> | complete
  fact "<text>"                                    append a user-confirmed fact
  findings <analyst.md> <label> [--closing]        log NEW / REOPEN findings and compounding risks
  dispositions <designer-response.md> <label> <ids>  log FIX / ACCEPT-RISK / OPEN-QUESTION / TECH-QUESTION
  options <designer-options.md> <label>            ids the designer marked TECH-QUESTION -> Tech team
  import-prd                                       §9 `- TQ:` lines, open PO rows of §10, other 🔵 lines -> log rows
  gaps <coverage-report.md>                        GAP rows -> Still Open, COVERAGE GAP
  import-stories <coverage-report.md>              🔵 lines in stories, leftover vague items -> log rows; counts
                                                   DoD overlaps (fixed by the packager, never asked)
  open [--final]                                   ids the PO checkpoint must still ask, and which lack a question
                                                   (--final: also rows parked by the pipeline; for the last checkpoint)
  ask <DL-id> ... [--final]                        AskUserQuestion JSON for up to 4 ids, within the question cap
                                                   (--final: not capped)
  decide <DL-id> <label> "<answer>"                record a PO decision (fact + Resolved row)
  defer <DL-id> [--cap|--final]                    record "Leave for grooming" (--final: at the last checkpoint)
  summary                                          the log summary line
  package-parts                                    write readiness.md, po-decisions.md, slices.md for the packager
  assemble <coverage-report.md>                    build final-prd.md from package-summary.md and the checked files
  scores                                           append the retro scorecard to groomed/scorecard.csv, print trend
"""
import datetime
import glob
import hashlib
import json
import os
import re
import sys

import check_decision_log as cdl
from pipeline_common import (ACTIVE_NAME, auto_name, budgets, display, esc, parse_log, project_root, read_lines,
                             row_line, slug, split_cells)

ROOT = project_root()
TODAY = datetime.date.today().isoformat()
DEFERRED = "deferred to grooming"

LOG_HEADER = """# Decision Log — {slug}

Cumulative across all rounds and runs. Rows are never deleted; status may change.
Status: Resolved | Still Open | Still Open (BLOCKING) | Tech team.
Resolution prefixes: FIX / ACCEPTED RISK / PO DECISION / OPEN QUESTION (PO) / TECH QUESTION / REOPENED / COVERAGE GAP / NOT ADDRESSED.

| ID | Name | Question/Issue | Raised in | Status | Resolution | Last updated |
|---|---|---|---|---|---|---|
"""
HEADER_ROW = "| ID | Name | Question/Issue | Raised in | Status | Resolution | Last updated |"
HEADER_SEP = "|---|---|---|---|---|---|---|"


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def p(*parts):
    return os.path.join(ROOT, *parts)


# ---------- active run and state ----------

def active():
    try:
        with open(p(ACTIVE_NAME), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        die("No active run. Run `dl.py start <requirement> <slug>` first.")


def state_file(run):
    return p(run["feature"], ".state", "run-state.json")


def load_state(run):
    with open(state_file(run), encoding="utf-8") as f:
        return json.load(f)


def save_state(run, st):
    with open(state_file(run), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def current(st, run):
    return next(r for r in st["runs"] if r["folder"] == run["run"])


# ---------- decision log I/O ----------

def log_path(run):
    return p(run["feature"], "decision-log.md")


def rows_of(run):
    rows, errors = parse_log(log_path(run))
    if errors:
        die("decision-log.md is invalid before this change:\n  " + "\n  ".join(errors))
    return rows


def save_rows(run, rows):
    """Rewrite the table rows in place (header kept), validate, roll back on error."""
    path = log_path(run)
    with open(path, encoding="utf-8") as f:
        old = f.read()
    head = [l for l in old.splitlines() if not re.match(r"^\|\s*DL-\d", l)]
    # Logs from before rows had a Name: widen the table header to the 7-column layout.
    head = [HEADER_ROW if re.match(r"^\|\s*ID\s*\|", l) else HEADER_SEP if re.match(r"^\|(-{3,}\|){6,7}\s*$", l) else l
            for l in head]
    while head and not head[-1].strip():
        head.pop()
    new = "\n".join(head + [row_line(r) for r in rows]) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    errors = cdl.check(path)
    if errors:
        with open(path, "w", encoding="utf-8") as f:
            f.write(old)
        die("Log write rejected and rolled back:\n  " + "\n  ".join(errors))


def next_id(rows):
    return f"DL-{max((int(r['id'][3:]) for r in rows), default=0) + 1:03d}"


def add_row(rows, issue, label, status, resolution="—", name=""):
    r = {"id": next_id(rows), "name": slug(name) or auto_name(issue), "issue": esc(issue), "raised": label,
         "status": status, "resolution": esc(resolution), "updated": label}
    rows.append(r)
    return r["id"]


def get(rows, rid):
    r = next((r for r in rows if r["id"] == rid), None)
    if r is None:
        die(f"{rid} is not in the decision log.")
    return r


def update(r, status, resolution, label, keep_prev=True):
    prev = r["resolution"]
    r["status"] = status
    r["resolution"] = esc(resolution + (f" · prev: {prev}" if keep_prev and prev not in ("", "—") else ""))
    r["updated"] = label


# ---------- markdown helpers ----------

def section(lines, title_re):
    """Lines under the first `## ` heading matching title_re, up to the next `## ` heading."""
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


def table(lines):
    return [split_cells(l) for l in lines if l.startswith("|") and not re.match(r"^\|\s*-{2,}", l)]


def keyed(t, default):
    """Table rows as dicts keyed by the lower-case header, e.g. {'ref':…, 'name':…}; `default` names the columns
    of a table without a header row."""
    hdr = next((c for c in t if c and c[0].lower() == "ref"), None)
    cols = [h.lower() for h in hdr] if hdr else list(default)
    return [dict(zip(cols, c)) for c in t if c is not hdr and c and c[0].lower() != "ref"]


def names(rows, ids):
    return ", ".join(display(get(rows, i)) for i in ids) or "none"


def bullets(lines):
    return [l[2:].strip() for l in lines if l.startswith("- ")]


def persona_check():
    sums = p("personas", "SOURCES.sha256")
    if not os.path.exists(sums):
        return "no SOURCES.sha256"
    changed = []
    for line in read_lines(sums) or []:
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        f = p("personas", name.strip().lstrip("*"))
        try:
            with open(f, "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() != digest:
                    changed.append(name.strip())
        except FileNotFoundError:
            changed.append(name.strip() + " (missing)")
    return "ok" if not changed else "CHANGED: " + ", ".join(changed)


# ---------- commands ----------

def context_status():
    lines = read_lines(p("context", "product-context.md"))
    if lines is None:
        return "missing (context/product-context.md)"
    facts = [l for l in lines if l.strip().startswith("- ")]
    return f"{len(facts)} facts" if facts else "empty (the PO can fill it in any time)"


CZECH = set("ěščřžýáíéůúťďňĚŠČŘŽÝÁÍÉŮÚŤĎŇ")
LANGS = {"cs": "Czech", "en": "English"}


# Text the scripts themselves put in front of the PO or into the package, per requirement language (CLAUDE.md
# "Language"). Ids, statuses and field labels the scripts parse stay English in every language.
TEXT = {
    "en": {"recommended": "(Recommended)", "leave": "Leave for grooming",
           "leave_desc": "Keep it open and discuss it with the team",
           "package": "Grooming package", "run": "Run", "status": "Status", "debate": "Debate",
           "after_rounds": "after {n} round{s}", "log": "Decision log",
           "all_decided": "every product question decided", "n_open": "{n} product question(s) left for grooming",
           "s3": "Terms", "s4": "User stories & acceptance criteria", "s5": "Definition of Ready",
           "s6": "Definition of Done", "s7": "Proposed slices", "s8": "PO decisions",
           "s9": "Open product questions for grooming", "s10": "Questions for the technical team",
           "s11": "Working files", "no_terms": "_No terms defined in the PRD._",
           "none_open": "_None: every product question was decided before this package was written._",
           "none": "_None._", "decision_log": "decision log", "rounds": "debate rounds",
           "gaps_since": "gaps decided by the PO since",
           "all_ready": "Each has value, testable criteria, nothing open, named dependencies, can be estimated and is small "
                        "(checked by script, see readiness.md).",
           "dor_intro": "_Checked by script from the stories, the coverage report and the decision log. ✓ = met._",
           "crit": ("Value", "Testable", "Nothing open", "Dependencies named", "Estimable", "Small"), "ready_col": "Ready",
           "ready": "**Ready**", "not_yet": "Not yet", "ready_line": "Ready: {r} of {n} stories.",
           "not_yet_line": " Not yet: {x}.", "dec_title": "PO decisions",
           "dec_intro": "_Questions the PO answered during this feature's grooming runs._",
           "dec_head": "| DL | Topic | Question | Decision |", "dec_none": "| — | — | No PO decisions yet. | — |",
           "slices": "Slices", "slices_intro": "_Proposal for discussion at grooming, not a commitment._"},
    "cs": {"recommended": "(Doporučeno)", "leave": "Nechat na grooming",
           "leave_desc": "Nechat otevřené a probrat s týmem",
           "package": "Podklady pro grooming", "run": "Běh", "status": "Stav", "debate": "Debata",
           "after_rounds": "počet kol: {n}{s}", "log": "Log rozhodnutí",
           "all_decided": "všechny produktové otázky rozhodnuty", "n_open": "otevřené produktové otázky na grooming: {n}",
           "s3": "Pojmy", "s4": "User stories a akceptační kritéria", "s5": "Definition of Ready",
           "s6": "Definition of Done", "s7": "Navržené řezy (slices)", "s8": "Rozhodnutí PO",
           "s9": "Otevřené produktové otázky na grooming", "s10": "Otázky pro technický tým",
           "s11": "Pracovní soubory", "no_terms": "_PRD nedefinuje žádné pojmy._",
           "none_open": "_Žádné: všechny produktové otázky byly rozhodnuty před sepsáním podkladů._",
           "none": "_Žádné._", "decision_log": "log rozhodnutí", "rounds": "kola debaty",
           "gaps_since": "mezery, které PO mezitím rozhodl",
           "all_ready": "Každá má hodnotu, testovatelná kritéria, nic otevřeného, pojmenované závislosti, jde odhadnout a je malá "
                        "(ověřeno skriptem, viz readiness.md).",
           "dor_intro": "_Ověřeno skriptem ze stories, coverage reportu a logu rozhodnutí. ✓ = splněno._",
           "crit": ("Hodnota", "Testovatelné", "Nic otevřeného", "Závislosti pojmenované", "Odhadnutelné", "Malé"),
           "ready_col": "Připraveno", "ready": "**Připraveno**", "not_yet": "Zatím ne",
           "ready_line": "Připraveno: {r} z {n} stories.", "not_yet_line": " Zatím ne: {x}.",
           "dec_title": "Rozhodnutí PO", "dec_intro": "_Otázky, na které PO odpověděl během groomingu této feature._",
           "dec_head": "| DL | Téma | Otázka | Rozhodnutí |", "dec_none": "| — | — | Zatím žádná rozhodnutí PO. | — |",
           "slices": "Řezy (slices)", "slices_intro": "_Návrh k diskusi na groomingu, ne závazek._"},
}


def tx(run, key, **kw):
    t = TEXT.get(run.get("lang") or "en", TEXT["en"])[key]
    return t.format(**kw) if kw else t


def detect_language(text):
    """cs if the text has Czech diacritics (≥ 5, or ≥ 0.5 % of letters), else en."""
    letters = sum(ch.isalpha() for ch in text) or 1
    cz = sum(ch in CZECH for ch in text)
    return "cs" if cz >= 5 or cz / letters >= 0.005 else "en"


def requirement_body(path):
    return "\n".join(l for l in (read_lines(path) or []) if not l.startswith("> Source:")).strip()


def cmd_start(args):
    if len(args) < 2:
        die("usage: start <requirement.md> <slug> [--resume|--new]")
    req, slug = args[0], args[1]
    if not os.path.isfile(p(req)):
        die(f"Requirement file not found: {req}")
    D = f"groomed/{slug}"
    os.makedirs(p(D, ".state"), exist_ok=True)
    sf = p(D, ".state", "run-state.json")
    if os.path.exists(sf):
        with open(sf, encoding="utf-8") as f:
            st = json.load(f)
    else:
        st = {"slug": slug, "source": req, "runs": []}
    last = st["runs"][-1] if st["runs"] else None
    resume = False
    if last and not last.get("complete"):
        if "--resume" in args:
            resume = True
        elif "--new" not in args:
            print(f"INCOMPLETE {last['folder']}\nAsk the user: resume it (--resume) or start a new run (--new)?")
            sys.exit(3)
    if resume:
        k, W = last["run"], last["folder"]
        P = st["runs"][-2]["folder"] if len(st["runs"]) > 1 else None
    else:
        k = (last["run"] + 1) if last else 1
        W = f"{D}/run-{k}_{TODAY}"
        P = last["folder"] if last else None
    os.makedirs(p(W, "rounds"), exist_ok=True)
    if not resume:
        with open(p(req), encoding="utf-8") as f:
            body = f.read()
        with open(p(W, "requirement.md"), "w", encoding="utf-8") as f:
            f.write(f"> Source: {req}, imported {TODAY}. Everything below is claims attributed to this source, "
                    f"not verified fact.\n\n{body}")
    if not os.path.exists(p(D, "confirmed-facts.md")):
        with open(p(D, "confirmed-facts.md"), "w", encoding="utf-8") as f:
            f.write(f"# Confirmed facts — {slug}\n\n_Nothing confirmed yet._\n")
    if not os.path.exists(p(D, "decision-log.md")):
        with open(p(D, "decision-log.md"), "w", encoding="utf-8") as f:
            f.write(LOG_HEADER.format(slug=slug))
    words = sum(len(l.split()) for l in (read_lines(p(W, "requirement.md")) or []) if not l.startswith("> Source:"))
    B = budgets()
    tier = "small" if words <= B["small_max_words"] else "standard"
    body = requirement_body(p(W, "requirement.md"))
    lang = args[args.index("--lang") + 1] if "--lang" in args else detect_language(body)
    if lang not in LANGS:
        die(f"--lang must be one of {', '.join(LANGS)}")
    changed = None if not P else body != requirement_body(p(P, "requirement.md"))
    if not resume:
        st["runs"].append({"run": k, "folder": W, "started": datetime.datetime.now().isoformat(timespec="seconds"),
                           "size": tier, "stages": {"0": "done"}, "rounds": 0, "verdict": None,
                           "po_questions": 0, "complete": False, "completed": None})
    else:
        tier = last["size"]
    with open(sf, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    with open(p(ACTIVE_NAME), "w", encoding="utf-8") as f:
        json.dump({"slug": slug, "feature": D, "run": W, "prev": P, "k": k, "tier": tier, "lang": lang,
                   "requirement_changed": changed}, f, indent=1)
    cdl.check(p(D, "decision-log.md"))  # seed the snapshot
    print(f"{'resumed' if resume else 'started'} run {k}\nD={D}\nW={W}\nP={P or '-'}\n"
          f"tier={tier} ({words} words) · max rounds={B['tiers'][tier]['rounds']} · "
          f"PO question cap={B['max_po_questions']}\nlanguage: {lang} ({LANGS[lang]})\n"
          f"requirement: {'new feature' if changed is None else 'CHANGED since the previous run' if changed else 'unchanged since the previous run'}\n"
          f"personas: {persona_check()}\nproduct context: {context_status()}")


def cmd_state(args):
    run = active()
    st = load_state(run)
    r = current(st, run)
    for a in args:
        if a == "complete":
            r["complete"] = True
            r["completed"] = datetime.datetime.now().isoformat(timespec="seconds")
            r["stages"]["8"] = "done"
            continue
        key, _, val = a.partition("=")
        if key == "stage":
            r["stages"][val] = "done"
        elif key == "rounds":
            r["rounds"] = int(val)
        elif key == "verdict":
            r["verdict"] = val
        else:
            die(f"unknown state key: {key}")
    save_state(run, st)
    if "complete" in args:
        os.remove(p(ACTIVE_NAME))
        print("run complete; active-run pin removed")
    else:
        print(json.dumps(r["stages"]))


def append_fact(run, text):
    path = p(run["feature"], "confirmed-facts.md")
    with open(path, encoding="utf-8") as f:
        body = f.read().replace("_Nothing confirmed yet._\n", "")
    body = body.rstrip("\n") + "\n" + f"- {text}\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def cmd_fact(args):
    run = active()
    append_fact(run, f"{' '.join(args)} (confirmed by user, /groom run {run['k']}, {TODAY})")
    print("fact recorded")


def cmd_findings(args):
    if len(args) < 2:
        die("usage: findings <analyst.md> <label> [--closing]")
    run, lines = active(), read_lines(args[0]) or die(f"missing {args[0]}")
    label, closing = args[1], "--closing" in args
    rows = rows_of(run)
    added, reopened, blocking = [], [], []
    for c in keyed(table(section(lines, r"^Findings")),
                   ("ref", "dimension", "type", "severity", "finding", "evidence")):
        if not c.get("finding"):
            continue
        dim, typ, sev, finding = c.get("dimension", ""), c.get("type", ""), c.get("severity", "").lower(), c["finding"]
        status = "Still Open (BLOCKING)" if sev == "blocking" else "Still Open"
        if typ == "NEW":
            res = "—"
            if closing and sev == "minor":
                res = f"OPEN QUESTION (PO): minor closing-round finding — proposed: accept for v1 or move to Later · {DEFERRED} by pipeline"
            rid = add_row(rows, f"[{dim}] {finding}", label, status, res, name=c.get("name", ""))
            added.append(rid)
        elif typ.startswith("REOPEN"):
            m = re.search(r"DL-\d{3,}", typ)
            if not m:
                die(f"REOPEN without a DL id: {typ}")
            r = get(rows, m.group(0))
            update(r, status, f"REOPENED {label}: {finding}", label)
            rid = r["id"]
            reopened.append(rid)
        else:
            continue
        if sev == "blocking":
            blocking.append(rid)
    for c in keyed(table(section(lines, r"^Compounding")), ("ref", "combines", "how they undercut each other", "severity")):
        combines = c.get("combines", "")
        if c.get("ref", "") in ("-", "—", "") or combines in ("-", "—", ""):
            continue
        sev = c.get("severity", "").lower()
        how = next((v for k, v in c.items() if k.startswith("how")), "")
        status = "Still Open (BLOCKING)" if sev == "blocking" else "Still Open"
        res = "—"
        if closing and sev == "minor":
            res = f"OPEN QUESTION (PO): minor closing-round risk — proposed: accept for v1 or move to Later · {DEFERRED} by pipeline"
        rid = add_row(rows, f"[Compounding {combines}] {how}", label, status, res, name=c.get("name", ""))
        added.append(rid)
        if sev == "blocking":
            blocking.append(rid)
    save_rows(run, rows)
    print(f"new: {names(rows, added)} · reopened: {names(rows, reopened)} · blocking: {', '.join(blocking) or 'none'}")
    print("respond to: " + ",".join(added + reopened) if added or reopened else "respond to: none")


DISPOSITIONS = {"FIX", "ACCEPT-RISK", "OPEN-QUESTION", "TECH-QUESTION"}


def cmd_dispositions(args):
    if len(args) < 3:
        die("usage: dispositions <designer-response.md> <label> <DL-a,DL-b,...>")
    run, lines = active(), read_lines(args[0]) or die(f"missing {args[0]}")
    label, asked = args[1], [x.strip() for x in args[2].split(",") if x.strip()]
    rows = rows_of(run)
    counts, answered, open_q = {d: 0 for d in DISPOSITIONS}, set(), []
    for c in table(lines):
        if len(c) < 4 or not re.match(r"DL-\d{3,}$", c[0]):
            continue
        rid, disp, res, sec = c[0], c[1].upper(), c[2], c[3]
        if disp not in DISPOSITIONS:
            die(f"{rid}: unknown disposition '{c[1]}'")
        r = get(rows, rid)
        if disp == "FIX":
            update(r, "Resolved", f"FIX: {res} ({sec})", label, keep_prev=False)
        elif disp == "ACCEPT-RISK":
            update(r, "Resolved", f"ACCEPTED RISK: {res}", label, keep_prev=False)
        elif disp == "OPEN-QUESTION":
            st = "Still Open (BLOCKING)" if r["status"] == "Still Open (BLOCKING)" else "Still Open"
            update(r, st, f"OPEN QUESTION (PO): {res}", label, keep_prev=False)
            open_q.append(rid)
        else:
            update(r, "Tech team", f"TECH QUESTION: {res}", label, keep_prev=False)
        counts[disp] += 1
        answered.add(rid)
    missing = [i for i in asked if i not in answered]
    for rid in missing:
        r = get(rows, rid)
        update(r, "Still Open (BLOCKING)" if "BLOCKING" in r["status"] else "Still Open", f"NOT ADDRESSED {label}", label)
    save_rows(run, rows)
    no_block = [i for i in open_q if not question_block(run, i)]
    print(" · ".join(f"{k} {v}" for k, v in sorted(counts.items())) +
          f" · NOT ADDRESSED {len(missing)}{(' (' + ', '.join(missing) + ')') if missing else ''}")
    print(f"open questions for the PO: {names(rows, open_q)}"
          + (f" · WARNING no question block: {', '.join(no_block)}" if no_block else ""))


def cmd_options(args):
    run, lines = active(), read_lines(args[0]) or die(f"missing {args[0]}")
    label, rows, tech = args[1], rows_of(run), []
    rid = None
    for l in lines:
        m = re.match(r"^###\s+(DL-\d{3,})", l)
        if m:
            rid = m.group(1)
        elif rid and l.strip().startswith("TECH-QUESTION:"):
            update(get(rows, rid), "Tech team", f"TECH QUESTION: {l.split(':', 1)[1].strip()}", label)
            tech.append(rid)
    save_rows(run, rows)
    print(f"tech questions: {', '.join(tech) or 'none'}")


def cmd_import_prd(args):
    run = active()
    lines = read_lines(p(run["run"], "prd-draft.md")) or die("missing prd-draft.md")
    rows = rows_of(run)
    text = " ".join(r["issue"] for r in rows)
    k = run["k"]
    tq, oq = [], []
    for l in lines:
        if l.startswith("- TQ: "):
            q = l[6:].strip()
            if esc(q) not in text:
                tq.append(add_row(rows, f"[Tech] {q}", f"run{k}-TQ", "Tech team", f"TECH QUESTION: {q}"))
    t = table(section(lines, r"^10\b|Open Questions"))
    if t:
        hdr = [h.lower() for h in t[0]]
        qi = next((i for i, h in enumerate(hdr) if "question" in h), None)
        oi = next((i for i, h in enumerate(hdr) if "owner" in h), None)
        si = next((i for i, h in enumerate(hdr) if "status" in h), None)
        if None not in (qi, oi, si):
            for c in t[1:]:
                if len(c) <= max(qi, oi, si):
                    continue
                q = c[qi]
                if c[si].strip().lower() == "open" and "PO" in c[oi] and not re.search(r"DL-\d{3,}", q) \
                        and esc(q) not in text:
                    oq.append(add_row(rows, f"[PRD §10] {q}", f"run{k}-OQ", "Still Open"))
    # a 🔵 outside §10 (a term, the evidence line…) is an open question too; without a row nobody asks the PO
    sec = ""
    for l in lines:
        m = re.match(r"^##\s*(\d+)\b", l)
        if m:
            sec = m.group(1)
            continue
        if "🔵" not in l or sec in ("", "10") or re.search(r"DL-\d{3,}", l):
            continue
        item = f"[PRD §{sec}] {l.strip().lstrip('-* ').strip()}"
        if esc(item) not in text:
            oq.append(add_row(rows, item, f"run{k}-OQ", "Still Open"))
    save_rows(run, rows)
    print(f"tech rows: {', '.join(tq) or 'none'} · PRD open rows (§10 and 🔵): {', '.join(oq) or 'none'}")


def coverage_gaps(lines):
    gaps = {m.group(1): m.group(2).strip() for b in bullets(section(lines, r"Gaps to reopen"))
            for m in [re.match(r"(DL-\d{3,}):\s*(.*)", b)] if m}
    for c in table(section(lines, r"Decision coverage")):
        if len(c) >= 4 and re.match(r"DL-\d{3,}$", c[0]) and c[-1].upper().startswith("GAP"):
            gaps.setdefault(c[0], c[1])
    return gaps


def cmd_gaps(args):
    run, lines = active(), read_lines(args[0]) or die(f"missing {args[0]}")
    rows, label = rows_of(run), f"run{active()['k']}-coverage"
    gaps = coverage_gaps(lines)
    for rid, what in gaps.items():
        update(get(rows, rid), "Still Open", f"COVERAGE GAP run{run['k']}: {what}", label)
    save_rows(run, rows)
    print(f"coverage gaps reopened: {', '.join(gaps) or 'none'}")


def cmd_import_stories(args):
    run, cov = active(), read_lines(args[0]) or die(f"missing {args[0]}")
    rows = rows_of(run)
    text = " ".join(r["issue"] for r in rows)
    label = f"run{run['k']}-stories"
    added, where = [], "stories"
    for l in read_lines(p(run["run"], "user-stories.md")) or []:
        m = re.match(r"^#{2,4}\s*(US-\d+)", l)
        if m:
            where = m.group(1)
        elif l.startswith("## "):
            where = "stories"
        if "🔵" in l:
            item = f"[Stories] {where}: {l.strip().lstrip('-* ').strip()}"
            if esc(item) not in text:
                added.append(add_row(rows, item, label, "Still Open"))
    for b in bullets(section(cov, r"Vague acceptance")):
        if "🔵" in b:  # the story's own 🔵 line was imported above
            continue
        item = f"[Stories] {b}"
        if esc(item) not in text:
            added.append(add_row(rows, item, label, "Still Open"))
    # DoD / AC overlaps are housekeeping, not product questions: the orchestrator has the packager fix them
    # (dod-fix) instead of asking the PO. Only a story's own open question or vague criterion becomes a row.
    dod_notes = [b for b in bullets(section(cov, r"DoD / AC separation")) if not b.lower().startswith(("none", "žádn"))]
    save_rows(run, rows)
    print(f"story rows: {names(rows, added)}")
    print(f"DoD overlaps to fix without asking the PO (packager dod-fix): {len(dod_notes)}")


def question_block(run, rid):
    """The newest designer file's `### DL-id` block, parsed; None if there is none."""
    files = sorted(glob.glob(p(run["run"], "rounds", "*designer-*.md")), key=os.path.getmtime, reverse=True)
    for f in files:
        lines = read_lines(f) or []
        start = next((i for i, l in enumerate(lines) if re.match(rf"^###\s+{rid}\b", l)), None)
        if start is None:
            continue
        block = []
        for l in lines[start + 1:]:
            if l.startswith("#"):
                break
            block.append(l)
        q = next((l.split(":", 1)[1].strip() for l in block if l.startswith("Question:")), None)
        if not q:
            continue
        opts = [m.groups() for l in block for m in [re.match(r"^(\d)\.\s+(.+?)\s+—\s+(.+)$", l.strip())] if m]
        rec = next((re.match(r"Recommended:\s*(\d)", l) for l in block if l.startswith("Recommended:")), None)
        comb = next((l for l in block if l.startswith("Combinable:")), "Combinable: no")
        header = next((l.split(":", 1)[1].strip() for l in block if l.startswith("Header:")), "")
        return {"question": q, "options": opts, "recommended": rec.group(1) if rec else None,
                "multi": comb.split(":", 1)[1].strip().lower().startswith("yes"), "header": header[:12]}
    return None


def open_ids(rows, final=False):
    """Rows the PO checkpoint must ask. `final` (the last checkpoint before the package) also includes rows the
    pipeline parked (minor closing-round findings, question cap); only a PO's own "Leave for grooming" is final."""
    skip = f"{DEFERRED} by PO" if final else DEFERRED
    return [r["id"] for r in rows if r["status"] in ("Still Open", "Still Open (BLOCKING)")
            and skip not in r["resolution"]]


def cmd_open(args):
    run = active()
    rows = rows_of(run)
    ids = open_ids(rows, final="--final" in args)
    ids.sort(key=lambda i: (get(rows, i)["status"] != "Still Open (BLOCKING)", i))
    need = [i for i in ids if not question_block(run, i)]
    print(f"to ask: {names(rows, ids)}\nneed a question block (designer options): {', '.join(need) or 'none'}")


def cmd_ask(args):
    run = active()
    st = load_state(run)
    r = current(st, run)
    final = "--final" in args
    ids = [a for a in args if a != "--final"][:4]
    cap = budgets()["max_po_questions"]
    left = len(ids) if final else cap - r.get("po_questions", 0)  # the final checkpoint is not capped
    if left <= 0:
        print(json.dumps({"cap_reached": True, "defer": ids}))
        return
    ask, over = ids[:left], ids[left:]
    qs = []
    for rid in ask:
        b = question_block(run, rid)
        if not b:
            die(f"{rid} has no question block; run the designer in options mode first.")
        opts = b["options"]
        rec = [o for o in opts if o[0] == b["recommended"]]
        rest = [o for o in opts if o[0] != b["recommended"]][:2]
        options = [{"label": f"{o[1]} {tx(run, 'recommended')}", "description": o[2]} for o in rec] + \
                  [{"label": o[1], "description": o[2]} for o in rest] + \
                  [{"label": tx(run, "leave"), "description": tx(run, "leave_desc")}]
        qs.append({"header": b["header"] or rid, "question": b["question"], "multiSelect": b["multi"],
                   "options": options, "dl_id": rid})
    print(json.dumps({"questions": qs, "over_cap_defer": over, "questions_left_after": left - len(ask)},
                     ensure_ascii=False, indent=1))


def count_question(run, final=False):
    """Debate-checkpoint answers count toward the cap; last-checkpoint answers (label *-final) are counted apart."""
    st = load_state(run)
    r = current(st, run)
    key = "po_questions_final" if final else "po_questions"
    r[key] = r.get(key, 0) + 1
    save_state(run, st)


def cmd_decide(args):
    if len(args) < 3:
        die('usage: decide <DL-id> <label> "<answer>"')
    run, rid, label, answer = active(), args[0], args[1], " ".join(args[2:])
    rows = rows_of(run)
    r = get(rows, rid)
    # A chosen option carries its consequence line, which often holds the exact wording (a message, a limit).
    # Keep it with the answer so the agents that apply the decision copy that wording instead of inventing one.
    b = question_block(run, rid)
    chosen = [o for o in (b["options"] if b else []) for part in answer.split(" AND ")
              if o[1].strip().lower() == re.sub(r"\s*\((Recommended|Doporučeno)\)\s*$", "", part).strip().lower()]
    if chosen:
        answer = " AND ".join(f"{o[1]} — {o[2]}" for o in chosen)
    update(r, "Resolved", f"PO DECISION: {answer}", label)
    save_rows(run, rows)
    append_fact(run, f"PO decision on {rid}: {answer} (confirmed by user, /groom run {run['k']}, {label})")
    count_question(run, final=label.endswith("-final"))
    affects = "DoD, stories" if r["issue"].startswith("[DoD]") else \
        "stories" if r["issue"].startswith("[Stories]") else "PRD, stories"
    print(f"{display(r)} decided · affects: {affects}")


def cmd_defer(args):
    run, rid = active(), args[0]
    by_cap = "--cap" in args
    rows = rows_of(run)
    r = get(rows, rid)
    r["resolution"] = esc(r["resolution"] + f" · {DEFERRED} by {'question cap' if by_cap else 'PO'}")
    save_rows(run, rows)
    if not by_cap:
        count_question(run, final="--final" in args)
    print(f"{rid} deferred")


def cmd_summary(args):
    print(cdl.summary(log_path(active())))


def stories_of(lines):
    """[(US id, title, lines)] from user-stories.md; a story ends at the next `## ` heading."""
    out, cur = [], None
    for l in lines:
        m = re.match(r"^#{2,4}\s*(US-\d+)[:\s]*(.*)$", l)
        if m:
            cur = (m.group(1), m.group(2).strip(), [])
            out.append(cur)
        elif l.startswith("## "):
            cur = None
        elif cur:
            cur[2].append(l)
    return out


def readiness_rows(stories, cov_lines, rows, tier):
    """Definition of Ready per story: (id, {criterion: bool}, notes). Deterministic, so the team can trust it."""
    lo, hi = budgets()["tiers"][tier]["scenarios"]
    vague = " ".join(bullets(section(cov_lines, r"Vague acceptance")))
    open_rows = {r["id"]: r for r in rows if r["status"].startswith("Still Open")}
    out = []
    for sid, _, body in stories:
        text = "\n".join(body)
        scen = len(re.findall(r"(?:Scenario(?: Outline)?|Scénář|Náčrt scénáře):", text))
        covers = re.findall(r"DL-\d{3,}", next((l for l in body if "Covers:" in l), ""))
        still = [i for i in covers if i in open_rows] + \
                [r["id"] for r in open_rows.values() if r["issue"].startswith(f"[Stories] {sid}:")]
        invest = next((l for l in body if "INVEST:" in l), "")
        c = {"Value": bool(re.search(r"\b(so that|aby|abych|abychom)\b", text, re.I)),
             "Testable": lo <= scen <= hi and sid not in vague,
             "Nothing open": "🔵" not in text and "Blocked by:" not in text and not still,
             "Dependencies named": bool(re.search(r"\bI\s*✓|\bI\s*✗\s*\(", invest)),
             "Estimable": bool(re.search(r"\bE\s*✓", invest)),
             "Small": bool(re.search(r"\bS\s*✓", invest))}
        notes = []
        if not c["Testable"]:
            notes.append(f"{scen} scenarios" if not lo <= scen <= hi else "vague criteria")
        if not c["Nothing open"]:
            notes.append("open: " + ", ".join(sorted(set(still))) if still else "open question or blocked")
        if not c["Dependencies named"]:
            notes.append("dependency without a reason")
        if not c["Estimable"]:
            why = re.search(r"\bE\s*✗\s*\(([^)]*)\)", invest)
            notes.append(f"not estimable: {why.group(1)}" if why else "not estimable")
        if not c["Small"]:
            notes.append("not small")
        if not c["Value"]:
            notes.append("no 'so that'")
        out.append((sid, c, notes))
    return out


def cmd_package_parts(args):
    """Write readiness.md, po-decisions.md and slices.md into the run folder for the packager (Stage 7)."""
    run = active()
    W = run["run"]
    stories = stories_of(read_lines(p(W, "user-stories.md")) or die("missing user-stories.md"))
    cov = read_lines(p(W, "coverage-report.md")) or read_lines(p(W, "coverage-report-1.md")) or []
    rows = rows_of(run)
    ready = readiness_rows(stories, cov, rows, run["tier"])
    crit = ("Value", "Testable", "Nothing open", "Dependencies named", "Estimable", "Small")
    out = ["# Definition of Ready", "", tx(run, "dor_intro"), "",
           "| Story | " + " | ".join(tx(run, "crit")) + f" | {tx(run, 'ready_col')} |",
           "|---|" + "---|" * (len(crit) + 1)]
    for sid, c, _ in ready:
        out.append(f"| {sid} | " + " | ".join("✓" if c[k] else "✗" for k in crit) + " | "
                   + (tx(run, "ready") if all(c.values()) else tx(run, "not_yet")) + " |")
    not_ready = [f"{sid} ({'; '.join(n)})" for sid, c, n in ready if not all(c.values())]
    out += ["", tx(run, "ready_line", r=len(ready) - len(not_ready), n=len(ready))
            + (tx(run, "not_yet_line", x=", ".join(not_ready)) if not_ready else "")]
    with open(p(W, "readiness.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    dec = [f"# {tx(run, 'dec_title')}", "", tx(run, "dec_intro"), "", tx(run, "dec_head"), "|---|---|---|---|"]
    n = 0
    for r in rows:
        if not r["resolution"].startswith("PO DECISION:"):
            continue
        answer = r["resolution"][len("PO DECISION:"):].split(" · prev:")[0].strip()
        b = question_block(run, r["id"])
        q = b["question"] if b else re.sub(r"^\[[^\]]*\]\s*", "", r["issue"])
        q = q if len(q) <= 140 else q[:137].rstrip() + "…"
        dec.append(f"| {r['id']} | {r['name'] or auto_name(r['issue'])} | {esc(q)} | {esc(answer)} |")
        n += 1
    if not n:
        dec.append(tx(run, "dec_none"))
    with open(p(W, "po-decisions.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(dec) + "\n")

    order, slices = [], {}
    for sid, _, body in stories:
        m = next((re.match(r"^\s*Slice:\s*(.+?)\s*$", l) for l in body if re.match(r"^\s*Slice:", l)), None)
        name = m.group(1) if m else "Unsliced"
        if name not in slices:
            order.append(name)
            slices[name] = []
        slices[name].append(sid)
    sl = [f"# {tx(run, 'slices')}", "", tx(run, "slices_intro"), ""] + \
         [f"- **{name}:** {', '.join(slices[name])}" for name in order]
    with open(p(W, "slices.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(sl) + "\n")
    print(f"readiness.md: {out[-1]}\npo-decisions.md: {n} decisions\nslices.md: "
          + " · ".join(f"{k} {len(v)}" for k, v in slices.items()))


def body_of(lines, stop=None):
    """A markdown file without its `# ` title, headings demoted one level, cut before a `## ` heading matching stop."""
    out = []
    for l in lines:
        if l.startswith("# ") and not out:
            continue
        if stop and l.startswith("## ") and re.search(stop, l[3:], re.I):
            break
        out.append("#" + l if re.match(r"^#{2,5} ", l) else l)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def subsection(lines, title_re):
    """Lines under the first `### ` heading matching title_re, up to the next heading of level ≤ 3."""
    out, inside = [], False
    for l in lines:
        if re.match(r"^#{1,3} ", l):
            if inside:
                break
            inside = l.startswith("### ") and bool(re.search(title_re, l[4:], re.I))
            continue
        if inside:
            out.append(l)
    while out and not out[-1].strip():
        out.pop()
    return out


def issue_text(r, limit=160):
    t = re.sub(r"^(\[[^\]]*\]\s*)+", "", r["issue"]).replace("\\|", "|")
    return t if len(t) <= limit else t[:limit - 1].rstrip() + "…"


def cmd_assemble(args):
    """Stage 7: build final-prd.md. The packager writes only package-summary.md (sections 0–2); everything that must
    appear verbatim (terms, stories, readiness, DoD, slices, PO decisions, open and tech questions) is copied here,
    so it cannot drift from the files that were checked."""
    if not args:
        die("usage: assemble <coverage-report.md>")
    run = active()
    W, k = run["run"], run["k"]
    need = lambda name: read_lines(p(W, name)) or die(f"missing {W}/{name}")
    summary_lines = need("package-summary.md")
    rows = rows_of(run)
    r = current(load_state(run), run)
    title = next((l[2:].strip() for l in summary_lines if l.startswith("# ")), run["slug"])
    title = title if tx(run, "package").lower() in title.lower() else f"{title} — {tx(run, 'package')}"
    still = [x for x in rows if x["status"].startswith("Still Open")]
    still.sort(key=lambda x: (x["status"] != "Still Open (BLOCKING)", x["id"]))
    status = tx(run, "all_decided") if not still else tx(run, "n_open", n=len(still))
    out = [f"# {title}",
           f"{tx(run, 'run')} {k} · {TODAY} · {tx(run, 'status')}: {status} · {tx(run, 'debate')}: "
           f"{r.get('verdict') or '—'} {tx(run, 'after_rounds', n=r.get('rounds', 0), s='s' if r.get('rounds', 0) != 1 and run.get('lang') != 'cs' else '')} · "
           f"{tx(run, 'log')}: {cdl.summary(log_path(run))}", ""]
    for n in ("0", "1", "2"):
        sec = section(summary_lines, rf"^{n}\.")
        head = next((l for l in summary_lines if re.match(rf"^## {n}\.", l)), None) or die(
            f"package-summary.md has no '## {n}.' section")
        while sec and not sec[-1].strip():
            sec.pop()
        out += [head] + sec + [""]
    terms = subsection(need("prd-draft.md"), r"^Terms")
    out += [f"## 3. {tx(run, 's3')}"] + (terms or [tx(run, "no_terms")]) + [""]
    out += [f"## 4. {tx(run, 's4')}"] + body_of(need("user-stories.md"), stop=r"Cross-cutting|Průřezov") + [""]
    ready_lines = body_of(need("readiness.md"))
    table_rows = [l for l in ready_lines if re.match(r"^\|\s*US-\d+", l)]
    if table_rows and all(l.rstrip().endswith(f"{tx(run, 'ready')} |") for l in table_rows):
        # every story is ready: the table would only repeat ✓, so one line says it
        ready_lines = [tx(run, "ready_line", r=len(table_rows), n=len(table_rows)) + " " + tx(run, "all_ready")]
    out += [f"## 5. {tx(run, 's5')}"] + ready_lines + [""]
    out += [f"## 6. {tx(run, 's6')}"] + body_of(need("definition-of-done.md")) + [""]
    story_map = read_lines(p(W, "story-map.md")) if run["tier"] == "standard" else None
    out += [f"## 7. {tx(run, 's7')}"] + body_of(story_map or need("slices.md")) + [""]
    out += [f"## 8. {tx(run, 's8')}"] + body_of(need("po-decisions.md")) + [""]
    out += [f"## 9. {tx(run, 's9')}"]
    out += [f"- **{display(x)}**{' (BLOCKING)' if 'BLOCKING' in x['status'] else ''} — {issue_text(x)}"
            for x in still] or [tx(run, "none_open")]
    tech = [x for x in rows if x["status"] == "Tech team"]
    out += ["", f"## 10. {tx(run, 's10')}"]
    for x in tech:
        q = re.sub(r"^TECH QUESTION:\s*", "", x["resolution"].split(" · prev:")[0]).replace("\\|", "|")
        out.append(f"- **{display(x)}** — {q if q and q != '—' else issue_text(x)}")
    if not tech:
        out.append(tx(run, "none"))
    cov = os.path.basename(args[0])
    gaps = coverage_gaps(read_lines(p(args[0]) if not os.path.isabs(args[0]) else args[0]) or [])
    since = [g for g in gaps if any(x["id"] == g and x["status"] == "Resolved" for x in rows)]
    out += ["", f"## 11. {tx(run, 's11')}",
            f"- [requirement.md](requirement.md) · [prd-draft.md](prd-draft.md) · "
            f"[{tx(run, 'decision_log')}](../decision-log.md) · [{tx(run, 'rounds')}](rounds/)",
            f"- [{cov}]({cov})" + (f" — {tx(run, 'gaps_since')}: {', '.join(since)}" if since else "")]
    with open(p(W, "final-prd.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    hi = budgets()["tiers"][run["tier"]]["lines"]["final-prd.md"]
    print(f"final-prd.md: {len(out)} lines · budget ({run['tier']}): ≤ {hi} · {'ok' if len(out) <= hi else 'OVER'}")


SCORECARD = os.path.join("groomed", "scorecard.csv")
SCORE_METRICS = ("Understandability", "Clarity", "Completeness", "Testability", "Proportion", "Product focus")


def parse_scorecard(lines):
    """{metric: score} from the `## Scorecard` table of retro.md."""
    out = {}
    for c in table(section(lines, r"^Scorecard")):
        if len(c) >= 2 and c[0] in SCORE_METRICS:
            m = re.match(r"\s*([1-5])", c[1])
            if m:
                out[c[0]] = int(m.group(1))
    return out


def cmd_scores(args):
    """Append this run's retro scorecard to groomed/scorecard.csv and print the trend against earlier runs."""
    run = active()
    scores = parse_scorecard(read_lines(p(run["run"], "retro.md")) or [])
    missing = [m for m in SCORE_METRICS if m not in scores]
    if missing:
        die(f"retro.md scorecard is missing: {', '.join(missing)}")
    path = p(SCORECARD)
    history = [l.split(",") for l in (read_lines(path) or [])[1:] if l.strip()]
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("date,feature,run," + ",".join(SCORE_METRICS) + ",average\n")
    avg = sum(scores.values()) / len(scores)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{TODAY},{run['slug']},{run['k']}," + ",".join(str(scores[m]) for m in SCORE_METRICS)
                + f",{avg:.1f}\n")
    line = " · ".join(f"{m} {scores[m]}" for m in SCORE_METRICS) + f" · average {avg:.1f}"
    if history:
        prev = [float(h[-1]) for h in history if len(h) == len(SCORE_METRICS) + 4]
        if prev:
            line += f" (earlier runs: {sum(prev) / len(prev):.1f} over {len(prev)} runs)"
    print(line)


COMMANDS = {"start": cmd_start, "state": cmd_state, "fact": cmd_fact, "findings": cmd_findings,
            "dispositions": cmd_dispositions, "options": cmd_options, "import-prd": cmd_import_prd,
            "gaps": cmd_gaps, "import-stories": cmd_import_stories, "open": cmd_open, "ask": cmd_ask,
            "decide": cmd_decide, "defer": cmd_defer, "summary": cmd_summary, "scores": cmd_scores,
            "package-parts": cmd_package_parts, "assemble": cmd_assemble}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        die(__doc__)
    COMMANDS[sys.argv[1]](sys.argv[2:])
