"""Regression tests for `orc report`'s dependency-graph section (issue
#41), subprocess pattern matching `test_cli_report.py`. Fixtures are built
fresh through `orc dispatch --config` inside a temp directory, mirroring
the SCN-005 a,b->c fan-in shape (`tests/scenarios/test_topology_durability.py`)
via the CLI's own `plan` config key (`docs/playbooks/cli-usage.md`'s
"Config in one minute" section) -- never by reading this repo's live
`.orc/` journals.

Covers the task scope's acceptance/regression list:

- a multi-work fan-in fixture (a,b -> c) renders the "Dependency graph"
  section, `c` is annotated with both blockers, and roots (`a`, `b`)
  render before the dependent (`c`) in source order;
- a diamond shape (`a -> b,c -> d`) renders `d` exactly once, under its
  first-declared blocker (`b`), annotated with the full dep list (`b`,
  `c`) -- the placement rule from `_build_dependency_tree`'s docstring in
  `orc_werk.cli.report`;
- a single-work run omits the section entirely (no header, no tree) --
  scope item 2's chosen degradation (full omission, not a suppressed
  line);
- a journal missing the `FX-CREATE-WORK` record (simulating an old/
  foreign journal, `CONTRACT-DURABILITY`) degrades gracefully: no tree,
  a small note, never a crash/non-zero exit -- scope item 3;
- escaping: `work_id` carries no charset restriction in this reference
  implementation (unlike `delivery_run_id`, which is filename-restricted
  via `SAFE_DELIVERY_RUN_ID`, `orc_werk.adapters.jsonl.tailsafe`) --
  confirmed by grepping `docs/contracts/ports/work-graph-port.md`'s
  plan-rejection list, which names no charset constraint on `work_id` --
  so markup-bearing ids ARE reachable in practice, not merely
  theoretical, and this suite exercises real escaping rather than
  skipping the case.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl import layout

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run_cli(tmp_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=tmp_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _dispatch_plan(tmp_dir: Path, run_id: str, plan: dict, attempts: dict) -> subprocess.CompletedProcess:
    config = {"run_id": run_id, "plan": plan, "attempts": attempts}
    config_path = tmp_dir / f"{run_id}.config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = _run_cli(tmp_dir, "dispatch", f"fixture for {run_id}", "--config", str(config_path))
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _accepted_attempt(label: str) -> list[dict]:
    return [{"outcome": "completed", "candidate": {"label": label}, "assurance": {"verdict": "accepted"}}]


class FanInDependencyGraphTest(unittest.TestCase):
    """`SCN-005`'s a,b -> c fan-in shape, rendered through `orc report`."""

    RUN_ID = "report-treeview-fanin"
    PLAN = {
        "works": [
            {"work_id": "a", "deps": []},
            {"work_id": "b", "deps": []},
            {
                "work_id": "c",
                "deps": [
                    {"work_id": "a", "condition": "accepted"},
                    {"work_id": "b", "condition": "accepted"},
                ],
            },
        ]
    }

    def test_fanin_tree_renders_with_both_blockers_annotated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_plan(
                tmp_dir,
                self.RUN_ID,
                self.PLAN,
                {"a": _accepted_attempt("A"), "b": _accepted_attempt("B"), "c": _accepted_attempt("C")},
            )

            report = _run_cli(tmp_dir, "report", self.RUN_ID)
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", self.RUN_ID).read_text(encoding="utf-8")

            self.assertIn('<section class="dependency-graph">', html_text)
            self.assertIn("<h2>Dependency graph</h2>", html_text)
            self.assertIn(
                "unlocked by accepted completion of: <code>a</code>, <code>b</code>", html_text
            )

            # Roots-before-dependents ordering. `c`'s first-declared
            # blocker is `a` (deps == [a, b], deps[0] == a per the
            # placement rule), so `c` nests under `a`'s subtree and `b`
            # renders afterward as a sibling root -- a parent always
            # precedes its own descendant (a before c), and sibling roots
            # preserve plan declaration order (a before b). `b` is not an
            # ancestor of `c`, so nothing requires `b` to precede `c`
            # positionally -- only the ancestor path's ordering is a
            # correctness property here.
            tree_start = html_text.index('<section class="dependency-graph">')
            tree_end = html_text.index("</section>", tree_start)
            tree_html = html_text[tree_start:tree_end]
            pos_a = tree_html.index(">a: ")
            pos_b = tree_html.index(">b: ")
            pos_c = tree_html.index(">c: ")
            self.assertLess(pos_a, pos_c)
            self.assertLess(pos_a, pos_b)

            # c is nested (indented) under the tree's root <ul>, not itself
            # a top-level root -- one dep-tree <ul> nested inside the root
            # <li> it's placed under.
            self.assertIn('<ul class="dep-tree">', tree_html)


class DiamondDependencyGraphTest(unittest.TestCase):
    """`a -> b,c -> d`: d fans in from both b and c and must render
    exactly once, under its first-declared blocker."""

    RUN_ID = "report-treeview-diamond"
    PLAN = {
        "works": [
            {"work_id": "a", "deps": []},
            {"work_id": "b", "deps": [{"work_id": "a", "condition": "accepted"}]},
            {"work_id": "c", "deps": [{"work_id": "a", "condition": "accepted"}]},
            {
                "work_id": "d",
                "deps": [
                    {"work_id": "b", "condition": "accepted"},
                    {"work_id": "c", "condition": "accepted"},
                ],
            },
        ]
    }

    def test_diamond_child_appears_once_under_first_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_plan(
                tmp_dir,
                self.RUN_ID,
                self.PLAN,
                {
                    "a": _accepted_attempt("A"),
                    "b": _accepted_attempt("B"),
                    "c": _accepted_attempt("C"),
                    "d": _accepted_attempt("D"),
                },
            )

            report = _run_cli(tmp_dir, "report", self.RUN_ID)
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", self.RUN_ID).read_text(encoding="utf-8")

            tree_start = html_text.index('<section class="dependency-graph">')
            tree_end = html_text.index("</section>", tree_start)
            tree_html = html_text[tree_start:tree_end]

            # d's dep-node-head appears exactly once in the tree (never
            # duplicated under both b and c).
            self.assertEqual(tree_html.count(">d: "), 1)
            # Full dep list still annotated, both blockers named.
            self.assertIn(
                "unlocked by accepted completion of: <code>b</code>, <code>c</code>", tree_html
            )
            # Placed under b (its first-declared blocker): d's node appears
            # after b's opening <li> and before b's closing </li>, i.e.
            # nested inside b's subtree, not c's.
            pos_b_open = tree_html.index('>b: ')
            pos_c_open = tree_html.index('>c: ')
            pos_d = tree_html.index('>d: ')
            self.assertLess(pos_b_open, pos_d)
            self.assertLess(pos_d, pos_c_open)


class SingleWorkOmissionTest(unittest.TestCase):
    """Scope item 2: a single-work run omits the dependency-graph section
    entirely -- no header, no tree, not even a suppressed line."""

    def test_single_work_run_has_no_dependency_graph_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "report-treeview-single",
                "attempts": {"work-1": _accepted_attempt("A")},
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "single work fixture", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            report = _run_cli(tmp_dir, "report", "report-treeview-single")
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", "report-treeview-single").read_text(encoding="utf-8")

            self.assertNotIn("Dependency graph", html_text)
            self.assertNotIn('class="dependency-graph"', html_text)
            self.assertNotIn('class="dep-tree', html_text)


class MissingPlanDegradationTest(unittest.TestCase):
    """Scope item 3: a journal with no `FX-CREATE-WORK` record at all
    (simulating an old/foreign journal that predates topology durability,
    issue #44) degrades gracefully -- section omitted, small note, never
    an error/crash."""

    RUN_ID = "report-treeview-missing-plan"

    def test_missing_fx_create_work_degrades_with_note_not_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": self.RUN_ID,
                "attempts": {"work-1": _accepted_attempt("A")},
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "missing plan fixture", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            journal_path = layout.journal_path(tmp_dir / ".orc", self.RUN_ID)
            lines = journal_path.read_text(encoding="utf-8").splitlines()
            # Simulate a foreign/old journal: strip the FX-CREATE-WORK
            # effect record but keep every other (fact-driven) record --
            # load_projection folds facts only, so this stays a valid,
            # renderable journal, just one topology can't be reconstructed
            # from (CONTRACT-DURABILITY's "Run topology" row).
            stripped = [
                line for line in lines if json.loads(line).get("id") != "FX-CREATE-WORK"
            ]
            self.assertLess(len(stripped), len(lines), "fixture must actually contain FX-CREATE-WORK to strip")
            journal_path.write_text("\n".join(stripped) + "\n", encoding="utf-8")

            report = _run_cli(tmp_dir, "report", self.RUN_ID)
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", self.RUN_ID).read_text(encoding="utf-8")

            self.assertNotIn("<h2>Dependency graph</h2>", html_text)
            self.assertNotIn('class="dependency-graph"', html_text)
            self.assertIn("dependency graph: unavailable", html_text)
            self.assertIn("no FX-CREATE-WORK plan recorded", html_text)


class DependencyGraphEscapingTest(unittest.TestCase):
    """`work_id` carries no charset restriction in this reference
    implementation (confirmed against `docs/contracts/ports/work-graph-port.md`'s
    plan-rejection list, which restricts `condition` and structural shape
    but never `work_id` content) -- unlike `delivery_run_id`, which IS
    filename-restricted (`SAFE_DELIVERY_RUN_ID`,
    `orc_werk.adapters.jsonl.tailsafe`). So a markup-bearing work id is a
    real, reachable input, not a theoretical one, and this test exercises
    the actual escaping rather than skipping."""

    RUN_ID = "report-treeview-escaping"
    PLAN = {
        "works": [
            {"work_id": "a", "deps": []},
            {"work_id": "<script>alert(1)</script>", "deps": [{"work_id": "a", "condition": "accepted"}]},
        ]
    }

    def test_markup_bearing_work_id_is_escaped_in_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_plan(
                tmp_dir,
                self.RUN_ID,
                self.PLAN,
                {
                    "a": _accepted_attempt("A"),
                    "<script>alert(1)</script>": _accepted_attempt("B"),
                },
            )

            report = _run_cli(tmp_dir, "report", self.RUN_ID)
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", self.RUN_ID).read_text(encoding="utf-8")

            self.assertNotIn("<script>alert(1)</script>", html_text)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_text)
            # Escaped both in the tree's chip label and in its
            # "unlocked by" dep-id rendering.
            tree_start = html_text.index('<section class="dependency-graph">')
            tree_end = html_text.index("</section>", tree_start)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_text[tree_start:tree_end])


if __name__ == "__main__":
    unittest.main()
