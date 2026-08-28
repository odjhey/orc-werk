"""M-000 portability acceptance (`docs/delivery/M0-pure-core.md`):
canonical persisted/interchange records must be reconstructable from
portable, explicit data without importing Python implementation classes.

This test drives one run through the `orc` CLI (subprocess, `JSONLJournal`
on disk), then reads the resulting `.jsonl` file as plain JSON lines --
`json.loads` only, no `orc_werk.adapters`/`orc_werk.ports` import at all --
and folds the fact records through `orc_werk.core.reducer.reduce` (the
only `orc_werk` import in the reconstruction step) to prove the same
projection is reconstructable from the portable bytes alone.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

CONFIG = {
    "run_id": "portability-run",
    "max_attempts": 3,
    "attempts": {
        "work-1": [
            {"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "rejected"}},
            {"outcome": "completed", "candidate": {"label": "B"}, "assurance": {"verdict": "accepted"}},
        ]
    },
}


class PortabilityAcceptanceTest(unittest.TestCase):
    def test_projection_reconstructable_from_plain_json_without_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(CONFIG), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, "-m", "orc_werk.cli", "dispatch", "portable run", "--config", str(config_path)],
                cwd=tmp_dir,
                env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            # issue #55 H1: don't hardcode a flat `<run_id>.jsonl` path here
            # (the new per-run-dir layout writes `<run_id>/journal.jsonl`
            # instead) -- and don't import orc_werk.adapters.jsonl.layout to
            # find it either, since this test's whole point is that nothing
            # beyond plain JSON + orc_werk.core is needed for the portable
            # reconstruction proof below. Instead, parse the path CLI itself
            # already printed (`journal: <path>`) -- exactly how a real
            # portable consumer with no orc_werk knowledge would find it.
            journal_line = next(l for l in result.stdout.splitlines() if l.startswith("journal: "))
            journal_path = Path(journal_line[len("journal: ") :])
            self.assertTrue(journal_path.exists())

            # Plain JSON only -- no orc_werk import of any kind here.
            raw_records = [
                json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines() if line.strip()
            ]
            self.assertGreater(len(raw_records), 0)
            for record in raw_records:
                self.assertEqual(record["schema_version"], 1)
                self.assertIn(record["kind"], ("fact", "decision", "effect"))
                self.assertIn("data", record)

            # Reconstruct the projection using ONLY orc_werk.core (the pure,
            # stdlib-only, adapter-free reference implementation) -- proving
            # the portable bytes alone are sufficient (M-000 acceptance).
            from orc_werk.core.facts import Fact
            from orc_werk.core.reducer import reduce

            fact_records = sorted(
                (r for r in raw_records if r["kind"] == "fact"), key=lambda r: r["seq"]
            )
            facts = [
                Fact(id=r["id"], delivery_run_id=r["delivery_run_id"], data=r["data"], extensions=r.get("extensions", {}))
                for r in fact_records
            ]
            projection = reduce(facts, delivery_run_id="portability-run", max_attempts=3)

            wp = projection.works["work-1"]
            self.assertEqual(wp.state, "ACCEPTED")
            self.assertTrue(wp.completed_confirmed)
            self.assertEqual(wp.attempt_number, 2)
            self.assertEqual(len(wp.executions), 2)


if __name__ == "__main__":
    unittest.main()
