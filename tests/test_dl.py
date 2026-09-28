"""dl.py end to end: the orchestrator's bookkeeping, run the way groom.md runs it."""
import json
import os
import unittest

from helpers import FIXTURES, readf, ProjectTest


class DlTest(ProjectTest):
    def test_start_creates_run_and_pins_it(self):
        run = self.start()
        self.assertEqual(run["k"], 1)
        self.assertEqual(run["tier"], "small")
        self.assertTrue(os.path.isdir(self.path(run["run"], "rounds")))
        req = readf(self.path(run["run"], "requirement.md"), encoding="utf-8")
        self.assertTrue(req.startswith("> Source: requirements/req.md"))
        self.assertIn("Admins export orders", req)
        self.assertIn("_Nothing confirmed yet._", readf(self.path(run["feature"], "confirmed-facts.md")))
        self.assertEqual(self.log(run), {})

    def test_incomplete_run_asks_then_resumes_or_starts_new(self):
        run = self.start()
        r = self.dl("start", "requirements/req.md", "order-export", ok=False)
        self.assertEqual(r.returncode, 3)
        self.assertIn("INCOMPLETE", r.stdout)
        self.dl("start", "requirements/req.md", "order-export", "--resume")
        self.assertEqual(json.loads(readf(self.path("groomed", ".active-run.json")))["run"], run["run"])
        self.dl("state", "complete")
        self.assertFalse(os.path.exists(self.path("groomed", ".active-run.json")))
        run2 = self.start()
        self.assertEqual(run2["k"], 2)
        self.assertEqual(run2["prev"], run["run"])

    def test_debate_round_bookkeeping(self):
        run = self.start()
        f = self.fixture("r1-analyst.md", f"{run['run']}/rounds/r1-analyst.md")
        out = self.dl("findings", f, "run1-R1").stdout
        self.assertIn("respond to: DL-001,DL-002,DL-003", out)
        log = self.log(run)
        self.assertEqual(log["DL-001"]["status"], "Still Open (BLOCKING)")
        self.assertEqual(log["DL-002"]["issue"], "[Data] A failed export shows nothing \\| the user retries blindly")

        f = self.fixture("r1-designer-response.md", f"{run['run']}/rounds/r1-designer-response.md")
        out = self.dl("dispositions", f, "run1-R1", "DL-001,DL-002,DL-003").stdout
        self.assertIn("NOT ADDRESSED 1 (DL-003)", out)
        self.assertIn("open questions for the PO: DL-001", out)
        log = self.log(run)
        self.assertEqual(log["DL-001"]["status"], "Still Open (BLOCKING)", "OPEN-QUESTION keeps BLOCKING")
        self.assertEqual(log["DL-002"]["resolution"], 'FIX: Admin sees "Export failed, try again" (§5.3)')
        self.assertTrue(log["DL-003"]["resolution"].startswith("NOT ADDRESSED run1-R1"))

        ask = json.loads(self.dl("ask", "DL-001").stdout)
        q = ask["questions"][0]
        self.assertEqual((q["header"], q["dl_id"]), ("Access", "DL-001"), "the chip shows the topic, not the id")
        self.assertEqual([o["label"] for o in q["options"]],
                         ["Admins and finance (Recommended)", "Admins only", "Everyone", "Leave for grooming"])

        self.dl("decide", "DL-001", "run1-R1", "Admins and finance — finance self-serves; wider access")
        log = self.log(run)
        self.assertEqual(log["DL-001"]["status"], "Resolved")
        self.assertTrue(log["DL-001"]["resolution"].startswith("PO DECISION: Admins and finance"))
        self.assertIn("· prev: OPEN QUESTION (PO)", log["DL-001"]["resolution"])
        facts = readf(self.path(run["feature"], "confirmed-facts.md"), encoding="utf-8")
        self.assertIn("- PO decision on DL-001: Admins and finance", facts)
        self.assertNotIn("_Nothing confirmed yet._", facts)

    def test_closing_minor_findings_are_not_asked_live(self):
        run = self.start()
        f = self.fixture("r1-analyst.md", f"{run['run']}/rounds/rF-analyst.md")
        self.dl("findings", f, "run1-RF", "--closing")
        out = self.dl("open").stdout
        self.assertIn("to ask: DL-001 who-may-export, DL-002 failed-export-message\n", out)  # DL-003 is minor: proposed accept/Later, not asked
        self.assertIn("deferred to grooming", self.log(run)["DL-003"]["resolution"])

    def test_final_checkpoint_asks_parked_rows_but_not_po_deferrals(self):
        run = self.start()
        f = self.fixture("r1-analyst.md", f"{run['run']}/rounds/rF-analyst.md")
        self.dl("findings", f, "run1-RF", "--closing")  # DL-003 (minor) is parked by the pipeline
        self.dl("defer", "DL-002")                     # the PO leaves DL-002 for grooming
        out = self.dl("open", "--final").stdout
        self.assertIn("to ask: DL-001 who-may-export, DL-003 export-speed-undefined\n", out)

    def test_final_ask_is_not_capped(self):
        run = self.start()
        f = self.fixture("r1-analyst.md", f"{run['run']}/rounds/r1-analyst.md")
        self.dl("findings", f, "run1-R1")
        self.fixture("r1-designer-response.md", f"{run['run']}/rounds/r1-designer-response.md")
        st_file = self.path(run["feature"], ".state", "run-state.json")
        st = json.loads(readf(st_file))
        st["runs"][-1]["po_questions"] = 12
        self.write(os.path.relpath(st_file, self.root), json.dumps(st))
        self.assertEqual(json.loads(self.dl("ask", "DL-001", "--final").stdout)["questions"][0]["dl_id"], "DL-001")
        self.dl("decide", "DL-001", "run1-final", "Admins only")
        r = json.loads(readf(st_file))["runs"][-1]
        self.assertEqual((r["po_questions"], r["po_questions_final"]), (12, 1), "final answers do not use the cap")

    def test_scores_are_stored_with_trend(self):
        run = self.start()
        card = ("# Retro\n\n## Scorecard\n| Metric | Score | Why (evidence) |\n|---|---|---|\n"
                + "".join(f"| {m} | {n} | x |\n" for m, n in [("Understandability", 4), ("Clarity", 3),
                          ("Completeness", 5), ("Testability", 4), ("Proportion", 2), ("Product focus", 5)])
                + "Trend: First scored run.\n")
        self.write(f"{run['run']}/retro.md", card)
        out = self.dl("scores").stdout
        self.assertIn("Proportion 2", out)
        self.assertIn("average 3.8", out)
        out = self.dl("scores").stdout
        self.assertIn("earlier runs: 3.8 over 1 runs", out)
        csv = readf(self.path("groomed", "scorecard.csv")).splitlines()
        self.assertEqual(csv[0], "date,feature,run,Understandability,Clarity,Completeness,Testability,Proportion,"
                                 "Product focus,average")
        self.assertEqual(len(csv), 3)
        self.write(f"{run['run']}/retro.md", "# Retro\n## Scorecard\n| Clarity | 3 | x |\n")
        self.assertIn("missing: Understandability", self.dl("scores", ok=False).stderr)

    def test_question_cap(self):
        run = self.start()
        f = self.fixture("r1-analyst.md", f"{run['run']}/rounds/r1-analyst.md")
        self.dl("findings", f, "run1-R1")
        self.fixture("r1-designer-response.md", f"{run['run']}/rounds/r1-designer-response.md")
        st_file = self.path(run["feature"], ".state", "run-state.json")
        st = json.loads(readf(st_file))
        st["runs"][-1]["po_questions"] = 12
        self.write(os.path.relpath(st_file, self.root), json.dumps(st))
        self.assertTrue(json.loads(self.dl("ask", "DL-001").stdout)["cap_reached"])
        self.dl("defer", "DL-001", "--cap")
        self.assertIn("deferred to grooming by question cap", self.log(run)["DL-001"]["resolution"])

    def test_prd_import_and_coverage(self):
        run = self.start()
        self.fixture("prd-draft.md", f"{run['run']}/prd-draft.md")
        out = self.dl("import-prd").stdout
        self.assertIn("tech rows: DL-001, DL-002", out)
        self.assertIn("PRD open rows (§10 and 🔵): DL-003", out)  # only the open PO row that cites no DL id
        self.dl("import-prd")
        self.assertEqual(len(self.log(run)), 3, "importing twice adds nothing")
        with open(self.path(run["run"], "prd-draft.md"), "a", encoding="utf-8") as f:
            f.write("\n## 5. Solution\n### Terms\n- profile: 🔵 Open Question: what does a profile hold?\n"
                    "- export: 🔵 Open Question: which formats? (DL-001)\n")
        out = self.dl("import-prd").stdout
        self.assertIn("PRD open rows (§10 and 🔵): DL-004", out)  # a 🔵 outside §10 that cites no DL id
        self.assertEqual(self.log(run)["DL-004"]["issue"],
                         "[PRD §5] profile: 🔵 Open Question: what does a profile hold?")
        self.dl("import-prd")
        self.assertEqual(len(self.log(run)), 4, "importing twice adds nothing")

        self.fixture("user-stories.md", f"{run['run']}/user-stories.md")
        cov = self.fixture("coverage-report.md", f"{run['run']}/coverage-report.md")
        f = self.fixture("r1-analyst.md", f"{run['run']}/rounds/r1-analyst.md")
        self.dl("findings", f, "run1-R1")  # adds DL-004..006 so DL-003 below is a real row
        self.dl("gaps", cov)
        self.assertTrue(self.log(run)["DL-003"]["resolution"].startswith("COVERAGE GAP run1: a scenario must show"))
        out = self.dl("import-stories", cov).stdout
        log = self.log(run)
        new = [r for r in log.values() if r["raised"] == "run1-stories"]
        self.assertEqual(len(new), 2, out)
        self.assertTrue(any(r["issue"].startswith("[Stories] US-02:") for r in new))
        self.assertFalse(any(r["issue"].startswith("[DoD]") for r in new), "DoD overlaps are never PO questions")
        self.assertIn("DoD overlaps to fix without asking the PO (packager dod-fix): 1", out)

    def test_invalid_log_write_is_rolled_back(self):
        run = self.start()
        f = self.fixture("r1-analyst.md", f"{run['run']}/rounds/r1-analyst.md")
        self.dl("findings", f, "run1-R1")
        log_file = self.path(run["feature"], "decision-log.md")
        before = readf(log_file, encoding="utf-8")
        r = self.dl("decide", "DL-099", "run1-R1", "x", ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(readf(log_file, encoding="utf-8"), before)

    def test_package_parts(self):
        run = self.start()
        W = run["run"]
        self.dl("findings", self.fixture("r1-analyst.md", f"{W}/rounds/r1-analyst.md"), "run1-R1")
        self.dl("dispositions", self.fixture("r1-designer-response.md", f"{W}/rounds/r1-designer-response.md"),
                "run1-R1", "DL-001,DL-002")
        self.dl("decide", "DL-001", "run1-R1", "Admins and finance")
        self.fixture("user-stories.md", f"{W}/user-stories.md")
        self.fixture("coverage-report.md", f"{W}/coverage-report.md")
        out = self.dl("package-parts").stdout
        self.assertIn("Ready: 1 of 3 stories.", out)
        ready = readf(self.path(W, "readiness.md"))
        self.assertIn("| US-01 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **Ready** |", ready)
        self.assertIn("US-02 (open: DL-003)", ready)          # Covers a Still Open row, and has a 🔵 line
        self.assertIn("US-03 (vague criteria; not small)", ready)
        decisions = readf(self.path(W, "po-decisions.md"))
        self.assertIn("| DL-001 | who-may-export | Who may export orders? | Admins and finance — finance self-serves; "
                      "wider access |", decisions)
        slices = readf(self.path(W, "slices.md"))
        self.assertIn("- **Walking skeleton:** US-01, US-02", slices)
        self.assertIn("- **Hardening:** US-03", slices)

    def test_package_parts_story_that_cannot_be_estimated_is_not_ready(self):
        run = self.start()
        W = run["run"]
        stories = readf(os.path.join(FIXTURES, "user-stories.md"), encoding="utf-8").replace(
            "INVEST: I ✓ | N ✓ | V ✓ | E ✓ | S ✓ | T ✓",
            "INVEST: I ✓ | N ✓ | V ✓ | E ✗ (waits for the list of formats) | S ✓ | T ✓", 1)
        self.write(f"{W}/user-stories.md", stories)
        self.fixture("coverage-report.md", f"{W}/coverage-report.md")
        out = self.dl("package-parts").stdout
        self.assertIn("Ready: 0 of 3 stories.", out)
        self.assertIn("US-01 (not estimable: waits for the list of formats)", readf(self.path(W, "readiness.md")))

    def test_state_updates(self):
        run = self.start()
        self.dl("state", "stage=1", "rounds=2", "verdict=READY FOR GROOMING")
        self.dl("state", "complete")
        r = json.loads(readf(self.path(run["feature"], ".state", "run-state.json")))["runs"][-1]
        self.assertEqual((r["rounds"], r["verdict"], r["complete"]), (2, "READY FOR GROOMING", True))
        self.assertTrue(r["completed"])


if __name__ == "__main__":
    unittest.main()
