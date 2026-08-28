"""`TASK-M1-005` CLI wiring: `orc dispatch`'s `execution`/`candidate`
config selecting `AcpExecution`/`GitDiffCandidate` (real ports) in place of
the scripted test doubles (`src/orc_werk/cli/config.py`'s "Real-port
selection" section).

Two groups of coverage:

- `AcpConfigValidationTest` -- `load_config`'s strict validation of the new
  `execution`/`candidate` blocks and their adapter-aware `attempts`
  narrowing (unit-level, in-process).
- `AcpWiringSmokeTest` -- a full `dispatch -> pending -> poll -> settled ->
  (operator records verdict) -> accepted` cycle driven through the REAL
  `orc` CLI entrypoint (subprocess), against a fake `acpx` on `PATH`
  (`tests/conformance/support_acpx_stub.py`, "PATH-override" per the task
  brief) and a real temporary git repository (`GitDiffCandidate`). No live
  Pi/`acpx`/Node dependency anywhere in this suite.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.acp.execution import session_name_for_idempotency_key
from orc_werk.adapters.git.candidate import GitDiffCandidate
from orc_werk.cli.config import build_dispatch_ports, load_config
from orc_werk.core.effects import FX_START_EXECUTION
from orc_werk.core.errors import CoreError
from orc_werk.core.idempotency import idempotency_key
from orc_werk.core.models import Candidate
from orc_werk.ports.base import LIFECYCLE_STATE_RUNNING, LIFECYCLE_STATE_SETTLED
from tests.conformance.support_acpx_stub import AcpxStubWorld

# `tests/core/test_package_imports.py` deliberately clears every
# `orc_werk.*` entry from `sys.modules` (to test-drive a truly fresh
# `orc_werk.core` import graph) -- a real, pre-existing test-isolation
# hazard for any OTHER test that imports `orc_werk.*` symbols locally
# inside a test method rather than at this module's top level: a later
# in-method `from orc_werk.adapters.git.candidate import GitDiffCandidate`
# would re-import a *fresh*, distinct class object after that clearing,
# which then fails `isinstance` against an instance built by
# already-imported production code (`orc_werk.cli.config`, imported here
# at module load time, before any test runs). Every `orc_werk.*` import
# this file needs is therefore imported here, at module top level, during
# test discovery -- matching every other test module's convention -- never
# inside a test method body.

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], cwd=path)
    _git(["config", "user.email", "acp-wiring@example.invalid"], cwd=path)
    _git(["config", "user.name", "ACP Wiring Fixture"], cwd=path)
    (path / "a.txt").write_text("x")
    _git(["add", "."], cwd=path)
    _git(["commit", "-q", "-m", "init"], cwd=path)


class AcpConfigValidationTest(unittest.TestCase):
    """`load_config`'s strict validation of `execution`/`candidate`."""

    def _write(self, tmp: Path, data: dict, *, name: str = "cfg.json") -> str:
        path = tmp / name
        path.write_text(json.dumps(data))
        return str(path)

    def test_acp_requires_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"execution": {"adapter": "acp"}})
            with self.assertRaises(CoreError) as ctx:
                load_config(path)
            self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_acp_requires_git_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"execution": {"adapter": "acp", "cwd": "/tmp"}})
            with self.assertRaises(CoreError) as ctx:
                load_config(path)
            self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_acp_plus_git_candidate_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                {
                    "execution": {"adapter": "acp", "cwd": "/tmp"},
                    "candidate": {"adapter": "git", "repo_path": "/tmp"},
                },
            )
            data = load_config(path)
            self.assertEqual(data["execution"]["adapter"], "acp")

    def test_unknown_execution_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                {
                    "execution": {"adapter": "acp", "cwd": "/tmp", "session_prefix": "x"},
                    "candidate": {"adapter": "git", "repo_path": "/tmp"},
                },
            )
            with self.assertRaises(CoreError) as ctx:
                load_config(path)
            self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_unknown_candidate_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"candidate": {"adapter": "git", "repo_path": "/tmp", "bogus": 1}})
            with self.assertRaises(CoreError):
                load_config(path)

    def test_acp_only_keys_rejected_when_execution_scripted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(Path(tmp), {"execution": {"adapter": "scripted", "cwd": "/tmp"}})
            with self.assertRaises(CoreError):
                load_config(path)

    def test_acp_attempts_reject_outcome_and_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                {
                    "execution": {"adapter": "acp", "cwd": "/tmp"},
                    "candidate": {"adapter": "git", "repo_path": "/tmp"},
                    "attempts": {"work-1": [{"outcome": "completed"}]},
                },
            )
            with self.assertRaises(CoreError):
                load_config(path)

    def test_acp_attempts_allow_assurance_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                {
                    "execution": {"adapter": "acp", "cwd": "/tmp"},
                    "candidate": {"adapter": "git", "repo_path": "/tmp"},
                    "attempts": {"work-1": [{"assurance": {"verdict": "accepted"}}]},
                },
            )
            data = load_config(path)
            self.assertEqual(data["attempts"]["work-1"][0], {"assurance": {"verdict": "accepted"}})

    def test_scripted_default_unchanged(self) -> None:
        # No `execution`/`candidate` keys at all -- the pre-existing schema,
        # `outcome`/`candidate`/`assurance` all still allowed together.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                Path(tmp),
                {
                    "attempts": {
                        "work-1": [
                            {"outcome": "completed", "candidate": {"a": 1}, "assurance": {"verdict": "accepted"}}
                        ]
                    }
                },
            )
            data = load_config(path)
            self.assertIn("candidate", data["attempts"]["work-1"][0])

    def test_scripted_execution_with_git_candidate_allows_outcome_not_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok_path = self._write(
                Path(tmp),
                {
                    "candidate": {"adapter": "git", "repo_path": "/tmp"},
                    "attempts": {"work-1": [{"outcome": "completed", "assurance": {"verdict": "accepted"}}]},
                },
            )
            load_config(ok_path)  # does not raise

            bad_path = self._write(
                Path(tmp),
                {
                    "candidate": {"adapter": "git", "repo_path": "/tmp"},
                    "attempts": {"work-1": [{"outcome": "completed", "candidate": {"a": 1}}]},
                },
                name="bad.json",
            )
            with self.assertRaises(CoreError):
                load_config(bad_path)


class AcpWiringSmokeTest(unittest.TestCase):
    """Full dispatch -> pending -> poll -> settled -> accepted cycle
    through the REAL `cmd_dispatch` path (subprocess `orc` invocation),
    against the stub-`acpx` harness and a real git repo -- no live Pi."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        _init_repo(self.repo)

        # tests/conformance/support_acpx_stub.py: the fake `acpx`, put
        # first on PATH for this subprocess test's real CLI invocations
        # (PATH-override, per the task brief -- no config-level `env` key,
        # no real acpx/Node/pi-acp dependency anywhere in this suite).
        self.world = AcpxStubWorld(self.root / "acpx_world")

        self.journal_dir = self.root / ".orc"
        self.run_id = "acp-wiring-smoke"
        self.config_path = self.root / "cfg.json"

    def _env(self) -> dict:
        import os

        env = dict(self.world.env())
        env["PYTHONPATH"] = str(SRC)
        env["PATH"] = f"{self.world.bin_dir}{os.pathsep}/usr/bin:/bin"
        return env

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", *args],
            cwd=self.root,
            env=self._env(),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def _session_name(self) -> str:
        """Predict work-1 attempt 1's `acpx` session name the same way
        `AcpExecution` derives it: a pure function of the `FX-START-
        EXECUTION` idempotency key (`INV-020`) -- mirrors the conformance
        harness's own prediction (`session_name_for_idempotency_key`)."""
        key = idempotency_key(
            FX_START_EXECUTION, delivery_run_id=self.run_id, work_id="work-1", attempt_number=1
        )
        return session_name_for_idempotency_key(key)

    def _seed_first_attempt(self) -> None:
        """Pre-seed the stub session's script for work-1's first attempt:
        a single entry that reaches "settled" on its second `sessions
        show` call. Before issue #57's fix this could not be relied on --
        `Orchestrator._reconcile_ports`'s unconditional `FX-START-
        EXECUTION` replay resubmitted the prompt on every fresh dispatch
        process, which reset the stub's per-call materialization progress
        before a second dispatch ever got to observe it, so the test used
        `AcpxStubWorld.force_settle` to sidestep polling entirely (see the
        fix's PR for the full trace). Now that `AcpExecution.start()` is
        cross-process idempotent (no resubmission, `docs/adapters/acp/
        mapping.md` "Idempotency behavior"), the states list genuinely
        advances one step per real `sessions show` call across the two
        dispatch processes below: dispatch 1 contributes the submit-time
        pre-check show (my new durable-signal check in `start()`, before
        `turns_submitted` advances -- doesn't consume a states index) plus
        its own `inspect()` poll (states[0] == "running"); dispatch 2's
        `_reconcile_ports` replay's own pre-submit durable check is the
        SECOND materializing `sessions show` call and lands on
        states[1] == "settled" -- no `force_settle`/wall-clock stand-in
        needed."""
        self.world.seed_script(
            self._session_name(),
            [{"states": ["running", "settled"], "outcome": "completed"}],
        )

    def _write_config(self, *, attempts: dict | None = None) -> None:
        data: dict = {
            "execution": {"adapter": "acp", "cwd": str(self.repo), "thought_level": "low"},
            "candidate": {"adapter": "git", "repo_path": str(self.repo)},
        }
        if attempts is not None:
            data["attempts"] = attempts
        self.config_path.write_text(json.dumps(data))

    def test_full_dispatch_pending_poll_settled_accepted_cycle(self) -> None:
        self._seed_first_attempt()
        self._write_config()

        # 1) First dispatch: starts the real (stubbed) execution, rests
        # pending at EXECUTING (exit 3) -- the stub's first `sessions show`
        # sees states[0] == "running".
        result1 = self._run_cli(
            "dispatch", "reply with the word ping",
            "--config", str(self.config_path), "--journal", str(self.journal_dir),
            "--run-id", self.run_id,
        )
        self.assertEqual(result1.returncode, 3, result1.stdout + result1.stderr)
        self.assertIn("awaiting=execution-outcome", result1.stdout)

        # 2) Poll (re-dispatch): `_reconcile_ports`'s replay of this
        # attempt's `FX-START-EXECUTION` calls `AcpExecution.start()`
        # again from a fresh instance -- issue #57's cross-process
        # idempotency check consults the session's durable "already
        # prompted" signal (no resubmit) and, as a side effect of that
        # same `sessions show` call, genuinely advances the stub's states
        # list to "settled" (see `_seed_first_attempt`). The now-
        # materialized result settles the execution, a REAL git candidate
        # is identified (fingerprint "fp-..."), and assurance is
        # requested but still pending (no verdict recorded yet) -- exit 3
        # again, now awaiting the assurance verdict.
        result2 = self._run_cli(
            "dispatch", "reply with the word ping",
            "--config", str(self.config_path), "--journal", str(self.journal_dir),
            "--run-id", self.run_id,
        )
        self.assertEqual(result2.returncode, 3, result2.stdout + result2.stderr)
        self.assertIn("awaiting=assurance-verdict", result2.stdout)
        self.assertIn("candidate_fingerprint=fp-", result2.stdout)
        self.assertNotIn("candidate_fingerprint=-", result2.stdout)

        journal_path = self.journal_dir / f"{self.run_id}.jsonl"
        records = [json.loads(line) for line in journal_path.read_text().splitlines() if line.strip()]

        settled = [r for r in records if r.get("id") == "FACT-EXEC-SETTLED"]
        self.assertEqual(len(settled), 1)
        self.assertEqual(settled[0]["data"]["outcome"], "completed")
        session_ext = settled[0]["extensions"].get("execution-session/v1")
        self.assertIsNotNone(session_ext, "execution-session/v1 provenance must be journaled losslessly")
        self.assertEqual(session_ext["provider"], "acpx-pi")
        self.assertIn("native_session_id", session_ext)
        self.assertEqual(session_ext["resume"]["strength"], "best-effort")

        observed = [r for r in records if r.get("id") == "FACT-CANDIDATE-OBSERVED"]
        self.assertEqual(len(observed), 1)
        fingerprint = observed[0]["data"]["fingerprint"]
        self.assertTrue(fingerprint.startswith("fp-"))

        # 3) Operator/verification agent records the assurance verdict --
        # ONLY the `assurance` key, per the attempts-merge semantics (the
        # real fingerprint is never authored into the config; it is
        # derived from the run's own journal, exactly as
        # `docs/playbooks/agent-cli-usage.md` prescribes for a real
        # candidate).
        self._write_config(attempts={"work-1": [{"assurance": {"verdict": "accepted"}}]})

        result3 = self._run_cli(
            "dispatch", "reply with the word ping",
            "--config", str(self.config_path), "--journal", str(self.journal_dir),
            "--run-id", self.run_id,
        )
        self.assertEqual(result3.returncode, 0, result3.stdout + result3.stderr)
        self.assertIn("state=ACCEPTED", result3.stdout)

    def test_build_dispatch_ports_binds_real_fingerprint_from_history(self) -> None:
        """Focused unit coverage of `build_real_assurance_script`'s
        position-matched, journal-observed-fingerprint binding, isolated
        from the subprocess/stub machinery above: an assurance run
        requested against the journal-observed fingerprint settles with
        the config's recorded verdict; a *different* fingerprint is left
        unscripted (pending, per `ScriptedAssurance`'s SCN-007 mode) rather
        than raising, matching this run's own not-yet-observed attempts."""
        real_fingerprint = "fp-realfingerprint000000"
        config = {
            "execution": {"adapter": "acp", "cwd": str(self.repo)},
            "candidate": {"adapter": "git", "repo_path": str(self.repo)},
            "attempts": {"work-1": [{"assurance": {"verdict": "accepted"}}]},
        }
        history = [
            {
                "kind": "fact",
                "id": "FACT-CANDIDATE-OBSERVED",
                "data": {"work_id": "work-1", "fingerprint": real_fingerprint},
            }
        ]

        class _FakeJournal:
            def history(self, *, delivery_run_id: str):
                return history

        execution, candidate, assurance = build_dispatch_ports(
            config, delivery_run_id="r1", intent_text="do the thing", journal=_FakeJournal()
        )
        self.assertIsInstance(candidate, GitDiffCandidate)
        self.assertTrue(callable(execution.start))

        bound = Candidate(
            id="c1", work_id="work-1", execution_id="e1", subject_identity=None, fingerprint=real_fingerprint
        )
        run = assurance.request(candidate=bound, requirements={}, idempotency_key="k1")
        observation = assurance.inspect(assurance_id=run.id)
        self.assertEqual(observation.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observation.verdict, "accepted")

        unbound = Candidate(
            id="c2", work_id="work-1", execution_id="e2", subject_identity=None, fingerprint="fp-unrelated00000000000"
        )
        pending_run = assurance.request(candidate=unbound, requirements={}, idempotency_key="k2")
        pending_observation = assurance.inspect(assurance_id=pending_run.id)
        self.assertEqual(pending_observation.state, LIFECYCLE_STATE_RUNNING)


if __name__ == "__main__":
    unittest.main()
