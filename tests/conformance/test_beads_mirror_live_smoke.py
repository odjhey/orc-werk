"""ONE live sandbox smoke test for `BeadsMirror` against a REAL `bd`
install (`TASK-M2-006` acceptance item), skipped when `bd` is not on
`PATH` -- there is no `bd` binary in `ci-required`'s `ubuntu-latest` job
(`.github/workflows/ci-required.yml` installs no such tool), so this test
skips there and runs only where a real `bd` is actually present (this
task's own recon: `bd version` 1.2.2, Homebrew, `/opt/homebrew/bin/bd`).

Provisions its own disposable `bd`-initialized workspace under a fresh
temp directory (`bd init --non-interactive`) -- NEVER touches any
operator-configured `bd` database (the task brief's hard safety
requirement). Cleans the temp directory up in `tearDown` regardless of
outcome.

Verification reads real `bd --json show <id>` output directly in this
test (test-infrastructure verification, not `BeadsMirror` reading its own
writes back -- the module under test stays write-only; only the test
itself is allowed to look).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.beads.mirror import BeadsMirror
from tests.scenarios.support import build_run

_BD_BIN = shutil.which("bd")


def _bd_show(workspace: str, bd_id: str) -> dict:
    proc = subprocess.run(
        [_BD_BIN, "--json", "-C", workspace, "show", bd_id],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, f"bd show {bd_id} failed: {proc.stderr}"
    rows = json.loads(proc.stdout)
    return rows[0] if isinstance(rows, list) else rows


@unittest.skipUnless(_BD_BIN, "bd CLI not installed -- live smoke skipped (see module docstring)")
class BeadsMirrorLiveSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._workspace = Path(tempfile.mkdtemp(prefix="orcw-beads-live-"))
        init = subprocess.run(
            ["bd", "init", "--non-interactive", "--prefix", "orcwlive", "-p", "orcwlive"],
            cwd=self._workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(init.returncode, 0, f"bd init failed: {init.stderr}\n{init.stdout}")

    def tearDown(self) -> None:
        shutil.rmtree(self._workspace, ignore_errors=True)

    def test_real_multi_work_run_projects_topology_briefs_and_terminal_states(self) -> None:
        """Drives one real fan-in delivery (a, b independently ready; c
        fans in on both) through a scripted Orchestrator to a terminal
        state, mirrors it into the real sandbox `bd` database, then reads
        real `bd show` output back (test-only) to confirm: replay-stable
        `<run_id>--<work_id>` ids, `run:<run_id>` label scoping, per-work
        briefs as descriptions, dependency edges, and `bd close --reason
        accepted` for the accepted Work -- the exact acceptance bar this
        task card names."""
        delivery_run_id = "orcwlive1"
        plan = {
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
        orch, journal, _wg = build_run(
            delivery_run_id=delivery_run_id,
            attempts_by_work={
                "a": [{"outcome": "completed", "candidate": {"label": "A"}, "verdict": "accepted"}],
                "b": [{"outcome": "completed", "candidate": {"label": "B"}, "verdict": "accepted"}],
                "c": [{"outcome": "completed", "candidate": {"label": "C"}, "verdict": "accepted"}],
            },
            plan=plan,
        )
        projection = orch.run()
        history = journal.history(delivery_run_id=delivery_run_id)
        for work_id in ("a", "b", "c"):
            self.assertEqual(projection.works[work_id].state, "ACCEPTED")

        mirror = BeadsMirror(workspace=str(self._workspace))
        report = mirror.project_run(
            delivery_run_id=delivery_run_id,
            history=history,
            projection=projection,
            briefs={"a": "brief for A", "b": "brief for B"},
            intent_text="ship the fan-in widget",
        )
        self.assertFalse(report.degraded, msg=[(e.argv, e.stderr) for e in report.errors])

        a_row = _bd_show(str(self._workspace), f"{delivery_run_id}--a")
        b_row = _bd_show(str(self._workspace), f"{delivery_run_id}--b")
        c_row = _bd_show(str(self._workspace), f"{delivery_run_id}--c")

        for row, expected_description in ((a_row, "brief for A"), (b_row, "brief for B")):
            self.assertEqual(row["description"], expected_description)
        self.assertEqual(c_row["description"], "ship the fan-in widget")

        for row in (a_row, b_row, c_row):
            self.assertEqual(row["labels"], [f"run:{delivery_run_id}"])
            self.assertEqual(row["status"], "closed")
            self.assertEqual(row["close_reason"], "accepted")
            self.assertEqual(row["metadata"]["state"], "accepted")

        dep_ids = {dep["id"] for dep in c_row["dependencies"]}
        self.assertEqual(dep_ids, {f"{delivery_run_id}--a", f"{delivery_run_id}--b"})


if __name__ == "__main__":
    unittest.main()
