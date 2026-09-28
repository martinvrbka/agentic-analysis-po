"""Shared test helpers: a throwaway project folder and a way to run the scripts inside it."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
FIXTURES = os.path.join(REPO, "tests", "fixtures")
sys.path.insert(0, SCRIPTS)

REQUIREMENT = "# Order export\nAdmins export orders as CSV so finance can reconcile each month.\n"


def readf(path, encoding="utf-8"):
    with open(path, encoding=encoding) as f:
        return f.read()


class ProjectTest(unittest.TestCase):
    """Each test gets an empty project root with requirements/req.md; scripts run with CLAUDE_PROJECT_DIR=root."""

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="groom-test-"))
        os.makedirs(os.path.join(self.root, "requirements"))
        os.makedirs(os.path.join(self.root, "groomed"))
        with open(os.path.join(self.root, "requirements", "req.md"), "w", encoding="utf-8") as f:
            f.write(REQUIREMENT)
        self._env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.root

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        if self._env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._env

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def run_script(self, script, *args, stdin=None):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.root)
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], cwd=self.root, env=env,
                              input=stdin, capture_output=True, text=True)

    def dl(self, *args, ok=True):
        r = self.run_script("dl.py", *args)
        if ok:
            self.assertEqual(r.returncode, 0, f"dl.py {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
        return r

    def start(self, slug="order-export"):
        self.dl("start", "requirements/req.md", slug)
        return json.loads(readf(self.path("groomed", ".active-run.json")))

    def fixture(self, name, dest):
        shutil.copy(os.path.join(FIXTURES, name), self.path(dest))
        return dest

    def log(self, run):
        from pipeline_common import parse_log
        rows, errors = parse_log(self.path(run["feature"], "decision-log.md"))
        self.assertEqual(errors, [])
        return {r["id"]: r for r in rows}

    def write(self, rel, text):
        full = self.path(rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
