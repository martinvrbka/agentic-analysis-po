"""Names on decision-log rows, script-assembled packages, wording checks and the orchestrator-side output check."""
import json
import os
import subprocess
import sys
import unittest

from helpers import SCRIPTS, ProjectTest, readf

import validate_output as vo

SUMMARY = """# Order export
## 0. In one minute
- Admins export orders as CSV for finance.
## 1. Business case
Finance reconciles monthly (confirmed by PO).
## 2. Scope at a glance
- IN: CSV export for a date range
- Later: scheduled exports
"""
DOD = "# Definition of Done — Order export\n\n## Testing\n" + "".join(
    f"- DoD-0{i}: item {i} holds for every story\n" for i in range(1, 6))


class NamesTest(ProjectTest):
    def test_analyst_names_and_auto_names(self):
        run = self.start()
        W = run["run"]
        out = self.dl("findings", self.fixture("r1-analyst.md", f"{W}/rounds/r1-analyst.md"), "run1-R1").stdout
        self.assertIn("new: DL-001 who-may-export, DL-002 failed-export-message", out)
        self.fixture("prd-draft.md", f"{W}/prd-draft.md")
        out = self.dl("import-prd").stdout
        log = self.log(run)
        self.assertEqual(log["DL-001"]["name"], "who-may-export")
        tq = next(r for r in log.values() if r["issue"].startswith("[Tech] How do we keep"))
        self.assertEqual(tq["name"], "keep-large-exports-slowing", "script-made rows are named from their text")
        self.assertIn("| ID | Name | Question/Issue |", readf(self.path(run["feature"], "decision-log.md")))

    def test_old_log_gets_name_column_and_names_stay_fixed(self):
        run = self.start()
        log_file = self.path(run["feature"], "decision-log.md")
        self.write(os.path.relpath(log_file, self.root),
                   "# Decision Log — x\n\n| ID | Question/Issue | Raised in | Status | Resolution | Last updated |\n"
                   "|---|---|---|---|---|---|\n| DL-001 | [Data] Old row | run0-R1 | Still Open | — | run0-R1 |\n")
        self.dl("findings", self.fixture("r1-analyst.md", f"{run['run']}/rounds/r1-analyst.md"), "run1-R1")
        log = self.log(run)
        self.assertEqual(log["DL-001"]["name"], "", "an older row keeps an empty name (shown with an auto name)")
        self.assertEqual(log["DL-002"]["name"], "who-may-export")
        import check_decision_log as cdl
        text = readf(log_file).replace("| DL-002 | who-may-export |", "| DL-002 | renamed-row |")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(text)
        self.assertIn("Name changed", "\n".join(cdl.check(log_file)))

    def test_decide_keeps_the_option_consequence_and_says_what_it_affects(self):
        run = self.start()
        W = run["run"]
        self.dl("findings", self.fixture("r1-analyst.md", f"{W}/rounds/r1-analyst.md"), "run1-R1")
        self.dl("dispositions", self.fixture("r1-designer-response.md", f"{W}/rounds/r1-designer-response.md"),
                "run1-R1", "DL-001,DL-002")
        out = self.dl("decide", "DL-001", "run1-R1", "Admins only (Recommended)").stdout
        self.assertIn("DL-001 who-may-export decided · affects: PRD, stories", out)
        self.assertTrue(self.log(run)["DL-001"]["resolution"].startswith(
            "PO DECISION: Admins only — smallest audience; finance asks an admin"))


class AssembleTest(ProjectTest):
    def build(self):
        run = self.start()
        W = run["run"]
        self.dl("findings", self.fixture("r1-analyst.md", f"{W}/rounds/r1-analyst.md"), "run1-R1")
        self.dl("dispositions", self.fixture("r1-designer-response.md", f"{W}/rounds/r1-designer-response.md"),
                "run1-R1", "DL-001,DL-002")
        self.dl("decide", "DL-001", "run1-R1", "Admins and finance")
        self.fixture("prd-draft.md", f"{W}/prd-draft.md")
        self.dl("import-prd")
        self.fixture("user-stories.md", f"{W}/user-stories.md")
        self.fixture("coverage-report.md", f"{W}/coverage-report.md")
        self.write(f"{W}/definition-of-done.md", DOD)
        self.write(f"{W}/package-summary.md", SUMMARY)
        self.dl("state", "rounds=2", "verdict=READY FOR GROOMING")
        self.dl("package-parts")
        return run, W

    def test_package_is_built_from_the_checked_files(self):
        run, W = self.build()
        out = self.dl("assemble", f"{W}/coverage-report.md").stdout
        self.assertRegex(out, r"final-prd.md: \d+ lines · budget \(small\): ≤ 220 · ok")
        pkg = readf(self.path(W, "final-prd.md"))
        self.assertEqual(vo.check_final(pkg.splitlines(), "small"), [])
        self.assertTrue(pkg.startswith("# Order export — Grooming package\nRun 1 · "))
        self.assertIn("Debate: READY FOR GROOMING after 2 rounds", pkg)
        self.assertIn("## 3. Terms\n- export: a CSV file of orders for a chosen date range", pkg)
        self.assertIn("### US-01: Export orders\nAs an admin, I want to export orders", pkg, "stories copied verbatim")
        self.assertNotIn("Cross-cutting candidates", pkg)
        self.assertIn("- DoD-05: item 5 holds for every story", pkg)
        self.assertIn("| DL-001 | who-may-export |", pkg)
        self.assertIn("- **DL-003 export-speed-undefined** — ", pkg, "open rows are listed with their names")
        self.assertIn("## 10. Questions for the technical team\n- **DL-00", pkg)
        self.assertIn("How do we keep large exports from slowing the site?", pkg)

    def test_missing_summary_section_is_an_error(self):
        run, W = self.build()
        self.write(f"{W}/package-summary.md", SUMMARY.replace("## 2. Scope at a glance", "## Scope"))
        r = self.dl("assemble", f"{W}/coverage-report.md", ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no '## 2.' section", r.stderr)


class WordingTest(unittest.TestCase):
    ROWS = [{"id": "DL-012", "resolution": 'PO DECISION: Keep deck — shows "Couldn\'t apply your filters. Try again."'}]

    def test_po_wording_must_reach_the_prd(self):
        prd = ['Step 2: the partner sees "Couldn\'t update your recipes. Try again."']
        self.assertIn("DL-012: the PO chose the wording", "\n".join(vo.wording(prd, [], self.ROWS)))
        prd = ['Step 2: the partner sees "Couldn\'t apply your filters. Try again."']
        self.assertEqual(vo.wording(prd, [], self.ROWS), [])

    def test_example_wording_is_not_binding(self):
        rows = [{"id": "DL-1", "resolution": 'PO DECISION: Reword — e.g. "No recipes left: your filters hide them"'}]
        self.assertEqual(vo.wording([], [], rows), [])

    def test_stories_copy_messages_from_the_prd(self):
        prd = ['Empty deck says "No recipes match your filters. Try clearing them."']
        stories = ['  Then I see "No recipes left. Your filters hide them all."',
                   '  Then I see "No recipes match your filters. Try clearing them."',
                   '  When I type "mushroom"']
        errs = vo.wording(prd, stories, [])
        self.assertEqual(len(errs), 1)
        self.assertIn("user-stories.md:1:", errs[0])

    def test_later_check_ignores_shared_everyday_words(self):
        self.assertEqual(vo.consistency_later({"US-03": "Hide recipes with food I won't eat"},
                                              ['a "hide recipes missing this field" option per filter']), [])
        self.assertTrue(vo.consistency_later({"US-09": "Scheduled monthly export email"},
                                             ["scheduled monthly export sent by email"]))


class AfterCheckTest(ProjectTest):
    def test_after_reports_then_records(self):
        run = self.start()
        W = run["run"]
        self.write(f"{W}/business-case.md", "# Business case\n" + "line\n" * 20)
        r = self.run_script("validate_output.py", "--after", "packager", "business-case.md")
        self.assertEqual(r.returncode, 1)
        self.assertIn("over the small budget of 15", r.stdout)
        warnings = self.path(run["feature"], ".state", "validation-warnings.log")
        self.assertFalse(os.path.exists(warnings), "without --record nothing is logged yet")
        self.run_script("validate_output.py", "--after", "packager", "business-case.md", "--record")
        self.assertIn("packager: business-case.md", readf(warnings))

    def test_summary_rejects_run_on_sentences(self):
        long = "- IN: " + "; ".join(f"item number {i} with details" for i in range(8)) + "."
        errs = vo.check_summary((SUMMARY + long).splitlines(), "small")
        self.assertTrue(any("sentence over 30 words" in e for e in errs))
        self.assertEqual(vo.check_summary(SUMMARY.splitlines(), "small"), [])

    def test_coverage_accepts_po_accepted_rows(self):
        lines = ["## Decision coverage", "| DL id | Decision | Covered by | Result |", "|---|---|---|---|",
                 "| DL-030 | Evidence not needed | — | N/A — accepted by PO |", "## Gaps to reopen",
                 "## Vague acceptance criteria", "## Implementation detail", "## DoD / AC separation issues"]
        self.assertEqual(vo.check_coverage(lines, "small"), [])


class MetricsTest(ProjectTest):
    def test_dod_items_without_bold_are_counted(self):
        run = self.start()
        W = run["run"]
        self.write(f"{W}/definition-of-done.md", DOD)
        subprocess.run([sys.executable, os.path.join(SCRIPTS, "run_metrics.py"), self.path(W)], check=True,
                       capture_output=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=self.root))
        self.assertIn("- Definition of Done items: 5 · ok", readf(self.path(W, "run-metrics.md")))


if __name__ == "__main__":
    unittest.main()
