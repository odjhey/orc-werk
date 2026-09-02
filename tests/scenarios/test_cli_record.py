"""Issue #192: record-only assurance config composition."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args], cwd=root,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=30,
    )


class RecordCliTest(unittest.TestCase):
    def pending(self, root: Path, run: str = "record-run", *, candidate=None) -> Path:
        cfg = root / "input.json"
        cfg.write_text(json.dumps({"attempts": {"work-1": [{
            "outcome": "completed", "candidate": candidate or {"head_sha": "right", "pr": 192}
        }]}}))
        result = cli(root, "dispatch", "record test", "--config", str(cfg),
                     "--run-id", run, "--journal", str(root / ".orc"))
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("awaiting=assurance-verdict", result.stdout)
        return root / ".orc" / run / "config.json"

    def test_scripted_entry_is_merge_only_and_dispatch_settles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.pending(root)
            before = json.loads(path.read_text())["attempts"]["work-1"][0]
            result = cli(root, "record", "record-run", "--work", "work-1", "--verdict", "accepted",
                         "--evidence-ref", "audit.log", "--finding", "looks good", "--model", "pi",
                         "--session-ref", "session-1", "--seat-ref", "verify-1", "--journal", str(root / ".orc"))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("next:\n  - orc dispatch", result.stdout)
            entry = json.loads(path.read_text())["attempts"]["work-1"][0]
            self.assertEqual(entry["outcome"], before["outcome"])
            self.assertEqual(entry["candidate"], before["candidate"])
            assurance = entry["assurance"]
            self.assertEqual(assurance["evidence_refs"], ["audit.log"])
            self.assertEqual(assurance["extensions"]["review-findings/v1"]["findings"], ["looks good"])
            self.assertEqual(assurance["extensions"]["executor-identity/v1"], {
                "model": "pi", "session_ref": "session-1", "seat_ref": "verify-1", "role": "verify"})
            settled = cli(root, "dispatch", "--run-id", "record-run", "--journal", str(root / ".orc"))
            self.assertEqual(settled.returncode, 0, settled.stdout + settled.stderr)

    def test_real_candidate_entry_created_with_only_assurance(self) -> None:
        # A5 (ADR-0005): the git-candidate half of this real-adapter shape
        # survives 0.5.0's acp removal -- `candidate.adapter == "git"`
        # alone still restricts the attempt entry (real CandidatePort
        # supplies the subject, so a config-declared `candidate` key would
        # be silently ignored), while `record`'s own merge-only write still
        # adds nothing but `assurance` to an entry that started empty.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.pending(root, "record-git-candidate")
            data = json.loads(path.read_text())
            data["candidate"] = {"adapter": "git", "repo_path": str(root)}
            data["attempts"]["work-1"][0] = {}
            path.write_text(json.dumps(data))
            result = cli(root, "record", "record-git-candidate", "--work", "work-1", "--verdict", "rejected",
                         "--journal", str(root / ".orc"))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(set(json.loads(path.read_text())["attempts"]["work-1"][0]), {"assurance"})

    def test_refusals_are_canonical_and_do_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); journal = str(root / ".orc")
            unknown = cli(root, "record", "absent", "--work", "work-1", "--verdict", "accepted", "--journal", journal)
            self.assertEqual(json.loads(unknown.stderr)["error"], "ERR-NOT-FOUND")
            path = self.pending(root)
            missing = cli(root, "record", "record-run", "--work", "missing", "--verdict", "accepted", "--journal", journal)
            self.assertEqual(json.loads(missing.stderr)["error"], "ERR-NOT-FOUND")
            first = cli(root, "record", "record-run", "--work", "work-1", "--verdict", "accepted", "--journal", journal)
            self.assertEqual(first.returncode, 0)
            repeated = cli(root, "record", "record-run", "--work", "work-1", "--verdict", "rejected", "--journal", journal)
            self.assertEqual(json.loads(repeated.stderr)["error"], "ERR-CONFLICT")
            self.assertEqual(json.loads(path.read_text())["attempts"]["work-1"][0]["assurance"]["verdict"], "accepted")
            cli(root, "dispatch", "--run-id", "record-run", "--journal", journal)
            terminal = cli(root, "record", "record-run", "--work", "work-1", "--verdict", "accepted", "--journal", journal)
            error = json.loads(terminal.stderr)
            self.assertEqual(error["error"], "ERR-CONFLICT")
            self.assertEqual(error["details"]["actual_pending_state"], "ACCEPTED")

    def test_derived_identity_reuses_validation_and_mismatch_conflicts_on_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.pending(root); journal = str(root / ".orc")
            bad_shape = cli(root, "record", "record-run", "--work", "work-1", "--verdict", "accepted",
                            "--derived-identity", "[]", "--journal", journal)
            self.assertEqual(json.loads(bad_shape.stderr)["error"], "ERR-VALIDATION")
            result = cli(root, "record", "record-run", "--work", "work-1", "--verdict", "accepted",
                         "--derived-identity", '{"head_sha":"wrong"}', "--journal", journal)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(path.read_text())["attempts"]["work-1"][0]["assurance"]["derived_identity"], {"head_sha": "wrong"})
            dispatch = cli(root, "dispatch", "--run-id", "record-run", "--journal", journal)
            self.assertEqual(json.loads(dispatch.stderr)["error"], "ERR-CONFLICT")


if __name__ == "__main__":
    unittest.main()
