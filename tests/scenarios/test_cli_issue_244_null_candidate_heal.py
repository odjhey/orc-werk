"""Issue #244 (SCN-014 regression): a re-dispatch after a null
`FX-IDENTIFY-CANDIDATE` observation must heal (re-derive and bind once the
subject exists again), never crash. SCN-014's semantics are unchanged --
null identification is a non-binding observation, re-derived every
dispatch (`docs/scenarios/SCN-014-null-candidate-recovery.md`) -- the bug
was a CLI-layer read-side defect, not an orchestrator/core one.

Root cause: `orc_werk.cli.config._observed_candidate_bindings` read
`dispatch_result.get("candidate", {})` -- a bare `.get` with a `{}`
default. That default only fires when the key is ABSENT; a null
observation journals `dispatch_result: {"candidate": null}`, a PRESENT key
whose value is `None`, so `.get("candidate", {})` returned `None`, and the
very next line's `.get("fingerprint")` crashed with `AttributeError:
'NoneType' object has no attribute 'get'`. Every other reader of a
`FX-IDENTIFY-CANDIDATE` record's `dispatch_result.candidate` in this
codebase (`cli.show`, `cli.affordances`, `cli.main`, `cli.refs`,
`cli.report`) already guards with `isinstance(candidate, Mapping)`; this
was the one call site that skipped the guard. Confirmed pre-existing since
#189 (`d7f3a7f`), unrelated to #221/#198's append-on-change compare (which
remains correct and untouched).

`build_real_assurance_script` (and therefore this bug) is on the read path
of every `orc dispatch`/`orc record` invocation for a `candidate.adapter:
"git"` config whose `assurance.adapter` is not `"command"` -- i.e. exactly
the shape the issue #244 reporter used (git candidate, default/scripted
assurance, `record --outcome` driving execution settlement)."""

from __future__ import annotations

import json
import shutil
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


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "a@b.com"],
        ["git", "config", "user.name", "a"],
    ):
        subprocess.run(args, cwd=path, check=True)
    (path / "f.txt").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


class Issue244ReportersSequenceTest(unittest.TestCase):
    def test_delete_dispatch_restore_dispatch_heals_instead_of_crashing(self) -> None:
        """(a): the reporter's exact repro. git-candidate run -> record
        --outcome completed -> DELETE repo_path -> dispatch (null
        journaled, NO crash, exit 3, R3's new next: affordance line) ->
        a SECOND dispatch while still deleted (issue #244: "every dispatch
        after that crashes") -> RESTORE repo_path -> dispatch -> candidate
        binds, proceeds to ASSURING."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "worktree" / "repo"
            _init_git_repo(repo)
            journal = str(root / ".orc")
            cfg = root / "cfg.json"
            cfg.write_text(json.dumps({"candidate": {"adapter": "git", "repo_path": str(repo)}}))

            started = cli(root, "dispatch", "issue 244 repro", "--config", str(cfg),
                          "--run-id", "issue244", "--journal", journal)
            self.assertEqual(started.returncode, 3, started.stdout + started.stderr)

            recorded = cli(root, "record", "issue244", "--work", "work-1", "--outcome", "completed",
                           "--evidence-ref", "pr:317", "--journal", journal)
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

            shutil.rmtree(repo)

            null_journaled = cli(root, "dispatch", "--run-id", "issue244", "--journal", journal)
            self.assertEqual(null_journaled.returncode, 3, null_journaled.stdout + null_journaled.stderr)
            combined = null_journaled.stdout + null_journaled.stderr
            self.assertNotIn("ERR-PERMANENT", combined)
            self.assertNotIn("AttributeError", combined)
            # R3: the pending output's next: block now names the likely
            # cause instead of staying silent.
            self.assertIn("candidate identification returned no subject", null_journaled.stdout)
            self.assertIn("ensure candidate.repo_path exists", null_journaled.stdout)
            self.assertIn("re-derivation is automatic", null_journaled.stdout)

            # A second dispatch while the subject is STILL absent must also
            # not crash -- the issue's "every dispatch after that crashes".
            still_null = cli(root, "dispatch", "--run-id", "issue244", "--journal", journal)
            self.assertEqual(still_null.returncode, 3, still_null.stdout + still_null.stderr)
            self.assertNotIn("ERR-PERMANENT", still_null.stdout + still_null.stderr)

            _init_git_repo(repo)
            healed = cli(root, "dispatch", "--run-id", "issue244", "--journal", journal)
            self.assertEqual(healed.returncode, 3, healed.stdout + healed.stderr)
            self.assertIn("state=ASSURING", healed.stdout)
            self.assertIn("candidate_fingerprint=fp-", healed.stdout)


class Issue244PreFixDamagedJournalReplayTest(unittest.TestCase):
    def test_precrafted_journal_matching_reporters_tail_shape_heals(self) -> None:
        """(c)/R4: recover EXISTING damaged runs, not just prevent new
        ones. This journal is written directly to disk -- never produced by
        this test's own `dispatch`/`record` calls -- to stand in for a run
        journaled by an orc build that predates this fix; its tail is the
        issue's own quoted excerpt verbatim:

            [0010] fact   FACT-EXEC-SETTLED     {"artifact_refs":[...],"outcome":"completed","work_id":"work-1"}
            [0011] effect FX-IDENTIFY-CANDIDATE {"dispatch_result":{"candidate":null},...,"work_id":"work-1"}

        Reading it (repo_path still absent) must not crash; restoring the
        subject and re-dispatching must heal -- proving the fix recovers a
        journal that already contains the damaging null record, not merely
        prevents a fresh one from crashing later."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "worktree" / "repo"  # deliberately not created yet
            run_id = "issue244-precrafted"
            journal_dir = root / ".orc"
            execution_id = "exec-aa3918192d7d5cb2"
            pr_ref = "https://github.com/example/xatu-delivery-companion/pull/317"

            def rec(seq: int, kind: str, id_: str, data: dict) -> dict:
                return {
                    "data": data, "delivery_run_id": run_id, "extensions": {},
                    "id": id_, "kind": kind, "schema_version": 1, "seq": seq,
                }

            records = [
                rec(1, "fact", "FACT-INTENT-SUBMITTED", {"intent_id": run_id, "text": "issue 244 precrafted"}),
                rec(2, "effect", "FX-CREATE-WORK", {
                    "dispatch_result": {"works": [{"delivery_run_id": run_id, "id": "work-1"}]},
                    "idempotency_key": f"{run_id}|FX-CREATE-WORK", "max_attempts": 3,
                    "plan": {"works": [{"deps": [], "work_id": "work-1"}]}, "work_id": "",
                }),
                rec(3, "fact", "FACT-WORK-CREATED", {"delivery_run_id": run_id, "work_id": "work-1"}),
                rec(4, "effect", "FX-CLAIM-WORK", {
                    "dispatch_result": {"claim_ref": "claim:work-1", "work_id": "work-1"},
                    "idempotency_key": f"{run_id}|work-1|FX-CLAIM-WORK", "work_id": "work-1",
                }),
                rec(5, "fact", "FACT-WORK-CLAIMED", {"claim_ref": "claim:work-1", "work_id": "work-1"}),
                rec(6, "fact", "FACT-WORK-READY", {"work_id": "work-1"}),
                rec(7, "decision", "DEC-DISPATCH", {
                    "attempt_number": 1, "attribution": {"policy": "v0-deterministic"},
                    "basis": [{"data": {"work_id": "work-1"}, "delivery_run_id": run_id,
                               "extensions": {}, "id": "FACT-WORK-READY"}],
                    "work_id": "work-1",
                }),
                rec(8, "effect", "FX-START-EXECUTION", {
                    "attempt_number": 1, "dispatch_result": {"execution_id": execution_id, "via": "start"},
                    "idempotency_key": f"{run_id}|work-1|1|FX-START-EXECUTION", "work_id": "work-1",
                }),
                rec(9, "fact", "FACT-EXEC-STARTED", {"execution_id": execution_id, "work_id": "work-1"}),
                # --- reporter's exact quoted tail shape (issue #244) starts here ---
                rec(10, "fact", "FACT-EXEC-SETTLED", {
                    "artifact_refs": [pr_ref], "execution_id": execution_id,
                    "outcome": "completed", "work_id": "work-1",
                }),
                rec(11, "effect", "FX-IDENTIFY-CANDIDATE", {
                    "dispatch_result": {"candidate": None}, "execution_id": execution_id,
                    "idempotency_key": f"{run_id}|work-1|1|FX-IDENTIFY-CANDIDATE", "work_id": "work-1",
                }),
                # --- end reporter's quoted tail ---
            ]

            journal_path = layout.journal_path(journal_dir, run_id)
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            journal_path.write_text("".join(json.dumps(r) + "\n" for r in records))
            layout.config_path(journal_dir, run_id).write_text(json.dumps({
                "attempts": {"work-1": [{"artifact_refs": [pr_ref], "outcome": "completed"}]},
                "candidate": {"adapter": "git", "repo_path": str(repo)},
            }))

            # repo_path still does not exist -- reading this pre-crafted
            # damaged journal must not crash (the issue's "every dispatch
            # after that crashes", reproduced from a journal this test
            # never itself dispatched into).
            still_damaged = cli(root, "dispatch", "--run-id", run_id, "--journal", str(journal_dir))
            self.assertEqual(still_damaged.returncode, 3, still_damaged.stdout + still_damaged.stderr)
            combined = still_damaged.stdout + still_damaged.stderr
            self.assertNotIn("ERR-PERMANENT", combined)
            self.assertNotIn("AttributeError", combined)
            self.assertIn("candidate identification returned no subject", still_damaged.stdout)

            _init_git_repo(repo)
            healed = cli(root, "dispatch", "--run-id", run_id, "--journal", str(journal_dir))
            self.assertEqual(healed.returncode, 3, healed.stdout + healed.stderr)
            self.assertIn("state=ASSURING", healed.stdout)
            self.assertIn("candidate_fingerprint=fp-", healed.stdout)


if __name__ == "__main__":
    unittest.main()
