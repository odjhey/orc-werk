"""Issue #192: record-only assurance config composition; plus its ship-seat
sibling `orc record --outcome` (record-only execution-outcome composition)."""
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


class RecordOutcomeCliTest(unittest.TestCase):
    """`orc record --outcome`: the ship-seat sibling of the #192 verdict path.
    Record-only sugar over the same merge-only atomic config write; never
    advances the run itself and never sets candidate identity."""

    def executing(self, root: Path, run: str = "outcome-run") -> Path:
        """Dispatch a fully-incremental run resting at EXECUTING pending
        (awaiting `execution-outcome`, SCN-007) and return its persisted
        config path."""
        cfg = root / "input.json"
        cfg.write_text("{}")
        result = cli(root, "dispatch", "outcome test", "--config", str(cfg),
                     "--run-id", run, "--journal", str(root / ".orc"))
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("awaiting=execution-outcome", result.stdout)
        return root / ".orc" / run / "config.json"

    def test_outcome_merge_is_additive_and_redispatch_advances_to_assuring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.executing(root); journal = str(root / ".orc")
            # Scripted candidate stays hand-authored (the documented limit:
            # --outcome never sets candidate identity) -- author it first,
            # then let the verb merge outcome + extensions into the SAME slot.
            data = json.loads(path.read_text())
            data.setdefault("attempts", {})["work-1"] = [{"candidate": {"pr": 7, "head_sha": "abc"}}]
            path.write_text(json.dumps(data))
            result = cli(root, "record", "outcome-run", "--work", "work-1", "--outcome", "completed",
                         "--evidence-ref", "gh-pr:7", "--evidence-ref", "head:abc", "--model", "pi",
                         "--session-ref", "session-1", "--seat-ref", "ship-1", "--journal", journal)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("recorded execution outcome: run=outcome-run work=work-1 outcome=completed",
                          result.stdout)
            self.assertIn("next:\n  - orc dispatch", result.stdout)
            entry = json.loads(path.read_text())["attempts"]["work-1"][0]
            self.assertEqual(entry["candidate"], {"pr": 7, "head_sha": "abc"})  # untouched
            self.assertEqual(entry["outcome"], "completed")
            # Issue #224 ruling: --evidence-ref now rides the canonical
            # attempt-entry artifact_refs field (FACT-EXEC-SETTLED.
            # artifact_refs), not execution-session/v1 -- that extension is
            # reserved for real provider session provenance and is no
            # longer emitted by this verb.
            self.assertEqual(entry["artifact_refs"], ["gh-pr:7", "head:abc"])
            self.assertNotIn("execution-session/v1", entry.get("extensions", {}))
            self.assertEqual(entry["extensions"]["executor-identity/v1"], {
                "model": "pi", "session_ref": "session-1", "seat_ref": "ship-1", "role": "ship"})
            # record never advances the run: only re-dispatch observes it.
            advanced = cli(root, "dispatch", "--run-id", "outcome-run", "--journal", journal)
            self.assertEqual(advanced.returncode, 3, advanced.stdout + advanced.stderr)
            self.assertIn("state=ASSURING", advanced.stdout)
            self.assertIn("awaiting=assurance-verdict", advanced.stdout)
            self.assertIn("candidate_fingerprint=fp-", advanced.stdout)
            # End-to-end (issue #224): the re-dispatch's FACT-EXEC-SETTLED
            # carries artifact_refs verbatim from the recorded evidence.
            settled_records = [
                json.loads(line)
                for line in layout.journal_path(root / ".orc", "outcome-run")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            settled = next(
                r for r in settled_records if r["kind"] == "fact" and r["id"] == "FACT-EXEC-SETTLED"
            )
            self.assertEqual(settled["data"]["artifact_refs"], ["gh-pr:7", "head:abc"])

    def test_mutual_exclusion_and_verdict_only_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.executing(root); journal = str(root / ".orc")
            both = cli(root, "record", "outcome-run", "--work", "work-1", "--verdict", "accepted",
                       "--outcome", "completed", "--journal", journal)
            self.assertEqual(both.returncode, 2)
            self.assertEqual(json.loads(both.stderr)["error"], "ERR-VALIDATION")
            neither = cli(root, "record", "outcome-run", "--work", "work-1", "--journal", journal)
            self.assertEqual(json.loads(neither.stderr)["error"], "ERR-VALIDATION")
            for extra in (("--finding", "x"), ("--derived-identity", '{"pr": 7}')):
                scoped = cli(root, "record", "outcome-run", "--work", "work-1", "--outcome",
                             "completed", *extra, "--journal", journal)
                self.assertEqual(json.loads(scoped.stderr)["error"], "ERR-VALIDATION",
                                 scoped.stdout + scoped.stderr)

    def test_outcome_refusals_are_canonical_and_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); journal = str(root / ".orc")
            unknown_run = cli(root, "record", "absent", "--work", "work-1", "--outcome", "completed",
                              "--journal", journal)
            self.assertEqual(json.loads(unknown_run.stderr)["error"], "ERR-NOT-FOUND")
            path = self.executing(root)
            unknown_work = cli(root, "record", "outcome-run", "--work", "missing", "--outcome",
                               "completed", "--journal", journal)
            self.assertEqual(json.loads(unknown_work.stderr)["error"], "ERR-NOT-FOUND")
            # Wrong seat direction while awaiting execution-outcome.
            verdict_now = cli(root, "record", "outcome-run", "--work", "work-1", "--verdict",
                              "accepted", "--journal", journal)
            error = json.loads(verdict_now.stderr)
            self.assertEqual(error["error"], "ERR-CONFLICT")
            self.assertEqual(error["details"]["actual_pending_state"], "execution-outcome")
            first = cli(root, "record", "outcome-run", "--work", "work-1", "--outcome", "failed",
                        "--journal", journal)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            before = path.read_bytes()
            # Already-recorded: refused, config byte-identical, no temp litter
            # (atomic same-directory tempfile + os.replace write path).
            repeated = cli(root, "record", "outcome-run", "--work", "work-1", "--outcome",
                           "completed", "--journal", journal)
            self.assertEqual(json.loads(repeated.stderr)["error"], "ERR-CONFLICT")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in path.parent.iterdir() if p.name.startswith(".config")], [])
            # Re-dispatch observes the failed attempt (retry opens attempt 2,
            # legal to record next) and never rewrites the attempts entries.
            settled = cli(root, "dispatch", "--run-id", "outcome-run", "--journal", journal)
            self.assertEqual(settled.returncode, 3, settled.stdout + settled.stderr)
            self.assertEqual(len(json.loads(path.read_text())["attempts"]["work-1"]), 1)

    def test_outcome_refused_after_settlement_names_actual_pending_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.executing(root); journal = str(root / ".orc")
            data = json.loads(path.read_text())
            data.setdefault("attempts", {})["work-1"] = [{"candidate": {"pr": 9, "head_sha": "def"}}]
            path.write_text(json.dumps(data))
            recorded = cli(root, "record", "outcome-run", "--work", "work-1", "--outcome",
                           "completed", "--journal", journal)
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
            cli(root, "dispatch", "--run-id", "outcome-run", "--journal", journal)
            # Now resting at ASSURING: recording another outcome is the
            # not-awaiting refusal, naming what the work actually awaits.
            late = cli(root, "record", "outcome-run", "--work", "work-1", "--outcome", "completed",
                       "--journal", journal)
            error = json.loads(late.stderr)
            self.assertEqual(error["error"], "ERR-CONFLICT")
            self.assertEqual(error["details"]["actual_pending_state"], "assurance-verdict")


if __name__ == "__main__":
    unittest.main()
