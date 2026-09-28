"""check_decision_log.py: rows are never dropped or reworded, statuses are valid, Bash writes are caught too."""
import json
import unittest

from helpers import ProjectTest

import check_decision_log as cdl

HEAD = "# Decision Log — x\n\n| ID | Question/Issue | Raised in | Status | Resolution | Last updated |\n|---|---|---|---|---|---|\n"
ROW1 = "| DL-001 | [Data] Export can fail \\| silently | run1-R1 | Still Open | — | run1-R1 |\n"
ROW2 = "| DL-002 | [Purpose] Who exports? | run1-R1 | Resolved | FIX: admins (§5) | run1-R1 |\n"


class DecisionLogTest(ProjectTest):
    def setUp(self):
        super().setUp()
        self.log_path = self.path("groomed", "f", "decision-log.md")
        self.write("groomed/f/decision-log.md", HEAD + ROW1 + ROW2)
        self.assertEqual(cdl.check(self.log_path), [])  # seeds the snapshot

    def test_status_and_resolution_may_change(self):
        self.write("groomed/f/decision-log.md", HEAD + ROW1.replace("Still Open | —", "Resolved | FIX: shown") + ROW2)
        self.assertEqual(cdl.check(self.log_path), [])

    def test_deleted_row_is_rejected(self):
        self.write("groomed/f/decision-log.md", HEAD + ROW1)
        self.assertIn("DL-002 was deleted", "\n".join(cdl.check(self.log_path)))

    def test_reworded_issue_is_rejected(self):
        self.write("groomed/f/decision-log.md", HEAD + ROW1 + ROW2.replace("Who exports?", "Who may export?"))
        self.assertIn("Question/Issue text changed", "\n".join(cdl.check(self.log_path)))

    def test_bad_status_and_cell_count(self):
        self.write("groomed/f/decision-log.md", HEAD + ROW1 + ROW2.replace("Resolved", "Done"))
        self.assertIn("status 'Done'", "\n".join(cdl.check(self.log_path)))
        self.write("groomed/f/decision-log.md", HEAD + ROW1.replace("\\|", "|") + ROW2)
        self.assertIn("expected 6 cells", "\n".join(cdl.check(self.log_path)))

    def test_rejected_write_does_not_advance_snapshot(self):
        self.write("groomed/f/decision-log.md", HEAD + ROW1)
        self.assertTrue(cdl.check(self.log_path))
        self.write("groomed/f/decision-log.md", HEAD + ROW1)
        self.assertTrue(cdl.check(self.log_path), "the deletion must still be caught on the next check")

    def test_summary_and_next_id(self):
        self.assertEqual(cdl.summary(self.log_path), "2 rows: 1 Resolved, 1 Still Open, 0 BLOCKING, 0 for tech team")
        self.assertEqual(cdl.next_id(self.log_path), "DL-003")

    def test_hook_checks_active_log_after_bash(self):
        self.write("groomed/.active-run.json", json.dumps({"feature": "groomed/f", "run": "groomed/f/run-1_x"}))
        self.write("groomed/f/decision-log.md", HEAD + ROW1)  # a shell command dropped DL-002
        r = self.run_script("check_decision_log.py", "--hook",
                            stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": "sed ..."}}))
        self.assertEqual(r.returncode, 2)
        self.assertIn("DL-002 was deleted", r.stderr)

    def test_hook_ignores_other_files(self):
        r = self.run_script("check_decision_log.py", "--hook",
                            stdin=json.dumps({"tool_name": "Write", "tool_input": {"file_path": "x/notes.md"}}))
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
