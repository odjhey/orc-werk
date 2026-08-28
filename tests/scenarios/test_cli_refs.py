"""`orc refs` (GitHub issue #100 part 1): pure journal-projection tests for
`orc_werk.cli.refs`, mirroring `test_cli_beads_mirror_wiring.py`'s
mixed shape -- unit-level coverage of the per-source row builders
(`RefsUnitTest`), plus subprocess-driven CLI wiring/regression coverage
(`RefsCliTest`) matching `test_cli_report.py`'s pattern.

`execution-session/v1` fixtures are crafted directly through
`orc_werk.app.Orchestrator` + a real `JSONLJournal` (`test_extension_
lossless_transport.py`'s pattern) rather than through `orc dispatch
--config`'s scripted-execution path: as of this writing, `orc_werk.cli.
config._exec_entry_from_attempt` validates an attempt-level `extensions`
key (`_ATTEMPT_ENTRY_KEYS`) but never actually copies it into the
`ScriptedExecution` script entry it builds, so a config-authored
`attempts[work].extensions` is silently dropped before it ever reaches a
settled `FACT-EXEC-SETTLED` record -- a pre-existing gap in `config.py`,
out of this task's scope (`orc refs` is a pure read-side projection; this
gap is CLI dispatch-config wiring), noted here and in the PR body rather
than fixed. `evidence_refs`/candidate/mirror fixtures use the ordinary
`orc dispatch --config` path, where the equivalent wiring (`assurance`
sub-object `evidence_refs`, attempt-level `candidate`, top-level
`mirror`) is exercised correctly by existing tests and by this file.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl import layout
from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate, fingerprint_of
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app import Orchestrator, RunConfig, default_single_work_plan
from orc_werk.cli.refs import (
    RefRow,
    _candidate_rows,
    _command_field,
    _evidence_ref_rows,
    _execution_session_rows,
    _has_repo_context,
    _mirror_row,
    _session_resolve,
    collect_refs,
)
from tests.conformance.support_beads_stub import install_stub, read_calls
from tests.scenarios.support import predicted_execution_id

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run_cli(tmp_dir: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"}
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=tmp_dir,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Unit-level coverage of the per-source row builders
# ---------------------------------------------------------------------------


class SessionResolveUnitTest(unittest.TestCase):
    def test_acpx_provider_derives_conservative_tool_form(self) -> None:
        self.assertEqual(_session_resolve("acpx-pi", "sess-123"), "acpx pi sessions history sess-123")

    def test_non_acpx_provider_renders_no_resolve(self) -> None:
        self.assertEqual(_session_resolve("some-other-provider", "sess-123"), "-")
        self.assertEqual(_session_resolve(None, "sess-123"), "-")
        self.assertEqual(_session_resolve("acpx-", "sess-123"), "-")  # empty agent name


class CommandFieldUnitTest(unittest.TestCase):
    def test_plain_command_field(self) -> None:
        self.assertEqual(_command_field({"command": "do-the-thing"}), "do-the-thing")

    def test_specific_suffixed_command_wins_over_generic(self) -> None:
        entry = {"command": "status check", "logs_command": "full logs"}
        self.assertEqual(_command_field(entry), "full logs")

    def test_no_command_field_returns_none(self) -> None:
        self.assertIsNone(_command_field({"no_mistakes_run_id": "r1", "repo_path": "/tmp"}))

    def test_non_string_command_value_ignored(self) -> None:
        self.assertIsNone(_command_field({"command": 123}))


class EvidenceRefRowsUnitTest(unittest.TestCase):
    def _history(self, evidence_refs) -> list[dict]:
        return [
            {
                "kind": "fact",
                "id": "FACT-ASSURE-SETTLED",
                "data": {"assurance_id": "a1", "verdict": "accepted", "evidence_refs": evidence_refs},
            }
        ]

    def test_plain_string_entry_renders_verbatim_no_resolve(self) -> None:
        rows = _evidence_ref_rows(self._history(["evidence-for-fp-1"]))
        self.assertEqual(rows, [RefRow(kind="evidence", provider="-", value="evidence-for-fp-1", resolve="-")])

    def test_structured_entry_with_command_field_surfaces_resolve(self) -> None:
        entry = {
            "no_mistakes_run_id": "r1",
            "repo_path": "/abs/repo",
            "command": "no-mistakes axi status --run r1",
        }
        rows = _evidence_ref_rows(self._history([entry]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].resolve, "no-mistakes axi status --run r1")
        # value carries the entry verbatim (portable JSON), not a summary.
        self.assertEqual(json.loads(rows[0].value), entry)

    def test_unknown_future_shape_passes_through_never_crashes(self) -> None:
        entry = {"future_field": "an-unregistered-shape", "nested": {"a": [1, 2, 3]}}
        rows = _evidence_ref_rows(self._history([entry]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].resolve, "-")
        self.assertEqual(json.loads(rows[0].value), entry)

    def test_absent_evidence_refs_yields_no_rows(self) -> None:
        history = [{"kind": "fact", "id": "FACT-ASSURE-SETTLED", "data": {"assurance_id": "a1", "verdict": "accepted"}}]
        self.assertEqual(_evidence_ref_rows(history), [])


class ExecutionSessionRowsUnitTest(unittest.TestCase):
    def _history(self, payload) -> list[dict]:
        return [
            {
                "kind": "fact",
                "id": "FACT-EXEC-SETTLED",
                "data": {"execution_id": "e1", "work_id": "w1", "outcome": "completed"},
                "extensions": {"execution-session/v1": payload},
            }
        ]

    def test_full_payload_yields_session_resume_transcript_rows(self) -> None:
        payload = {
            "provider": "acpx-pi",
            "native_session_id": "sess-9f2c",
            "resume": {"strength": "best-effort", "ref": "resume-ref-9f2c"},
            "transcript_ref": "/abs/transcript.log",
        }
        rows = _execution_session_rows(self._history(payload))
        self.assertEqual(
            rows,
            [
                RefRow(kind="session", provider="acpx-pi", value="sess-9f2c", resolve="acpx pi sessions history sess-9f2c"),
                RefRow(kind="resume", provider="acpx-pi", value="resume-ref-9f2c", resolve="-"),
                RefRow(kind="transcript", provider="acpx-pi", value="/abs/transcript.log", resolve="cat /abs/transcript.log"),
            ],
        )

    def test_minimal_payload_yields_session_row_only(self) -> None:
        payload = {"provider": "opaque-provider-c", "native_session_id": "opaque-session-55zz"}
        rows = _execution_session_rows(self._history(payload))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "session")
        self.assertEqual(rows[0].resolve, "-")

    def test_unknown_future_field_in_payload_does_not_break_known_rows(self) -> None:
        payload = {
            "provider": "acpx-pi",
            "native_session_id": "sess-1",
            "some_future_field": {"anything": True},
        }
        rows = _execution_session_rows(self._history(payload))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].value, "sess-1")

    def test_no_extension_payload_yields_no_rows(self) -> None:
        history = [{"kind": "fact", "id": "FACT-EXEC-SETTLED", "data": {}, "extensions": {}}]
        self.assertEqual(_execution_session_rows(history), [])


class CandidateRowsUnitTest(unittest.TestCase):
    def _history(self, subject_identity) -> list[dict]:
        return [
            {
                "kind": "effect",
                "id": "FX-IDENTIFY-CANDIDATE",
                "data": {
                    "work_id": "w1",
                    "dispatch_result": {
                        "candidate": {"id": "cand-1", "subject_identity": subject_identity, "fingerprint": "fp-1"}
                    },
                },
            }
        ]

    def test_head_sha_and_repo_path_yield_resolvable_git_command(self) -> None:
        rows = _candidate_rows(self._history({"head_sha": "abc123", "repo_path": "/abs/repo"}))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "candidate")
        self.assertEqual(rows[0].resolve, "git -C /abs/repo show abc123 --stat")

    def test_head_sha_without_repo_path_has_no_resolve(self) -> None:
        rows = _candidate_rows(self._history({"head_sha": "abc123"}))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].resolve, "-")

    def test_pr_without_repo_context_has_no_resolve(self) -> None:
        rows = _candidate_rows(self._history({"pr": 42}))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "candidate-pr")
        self.assertEqual(rows[0].resolve, "-")

    def test_pr_with_repo_context_field_yields_gh_resolve(self) -> None:
        rows = _candidate_rows(self._history({"pr": 42, "repo_path": "/abs/repo"}))
        pr_row = next(r for r in rows if r.kind == "candidate-pr")
        self.assertEqual(pr_row.resolve, "gh pr view 42")

    def test_no_candidate_effect_yields_no_rows(self) -> None:
        self.assertEqual(_candidate_rows([]), [])


class HasRepoContextUnitTest(unittest.TestCase):
    def test_repo_path_key_counts_as_context(self) -> None:
        self.assertTrue(_has_repo_context({"pr": 1, "repo_path": "/abs/repo"}))

    def test_url_key_counts_as_context(self) -> None:
        self.assertTrue(_has_repo_context({"pr": 1, "repo_url": "https://example.invalid/x"}))

    def test_no_matching_key_is_false(self) -> None:
        self.assertFalse(_has_repo_context({"pr": 1, "label": "x"}))

    def test_pr_key_itself_never_counts(self) -> None:
        self.assertFalse(_has_repo_context({"pr": 1}))


class MirrorRowUnitTest(unittest.TestCase):
    def test_absent_config_yields_no_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(_mirror_row(Path(tmp), "no-such-run"))

    def test_config_without_mirror_yields_no_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = layout.config_path(directory, "run-1")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"attempts": {}}), encoding="utf-8")
            self.assertIsNone(_mirror_row(directory, "run-1"))

    def test_configured_mirror_yields_label_workspace_and_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = layout.config_path(directory, "run-1")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"mirror": {"adapter": "beads", "workspace": "/abs/bd-workspace"}}), encoding="utf-8"
            )
            row = _mirror_row(directory, "run-1")
            self.assertIsNotNone(row)
            self.assertEqual(row.kind, "mirror")
            self.assertEqual(row.provider, "beads")
            self.assertIn("run:run-1", row.value)
            self.assertIn("/abs/bd-workspace", row.value)
            self.assertEqual(
                row.resolve, "bd --json -C /abs/bd-workspace list --label run:run-1"
            )


# ---------------------------------------------------------------------------
# Subprocess CLI wiring / regression coverage
# ---------------------------------------------------------------------------


class RefsCliHelpTest(unittest.TestCase):
    def test_refs_registered_in_top_level_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", "--help"],
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("refs", result.stdout)

    def test_refs_help_is_self_sufficient(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", "refs", "--help"],
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("orc refs", result.stdout)
        self.assertIn("--journal", result.stdout)


class RefsMissingRunTest(unittest.TestCase):
    def test_missing_run_is_err_not_found_no_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "refs", "totally-nonexistent-run-id")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")
            self.assertFalse((tmp_dir / ".orc").exists())


class RefsEmptyRunTest(unittest.TestCase):
    def test_pending_run_with_no_settled_facts_is_definitive_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps({"attempts": {}}), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "pending demo", "--config", str(config_path), "--run-id", "refs-empty")
            self.assertEqual(dispatch.returncode, 3, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "refs", "refs-empty")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("run: refs-empty", result.stdout)
            self.assertIn("0 refs for refs-empty", result.stdout)
            self.assertIn("orc status refs-empty", result.stdout)

    def test_non_tty_output_has_zero_escape_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps({"attempts": {}}), encoding="utf-8")
            _run_cli(tmp_dir, "dispatch", "pending demo", "--config", str(config_path), "--run-id", "refs-nontty")
            result = _run_cli(tmp_dir, "refs", "refs-nontty")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertNotIn("\x1b", result.stdout)


class RefsEvidenceAndCandidateCliTest(unittest.TestCase):
    """Full CLI wiring: a scripted run whose settled assurance carries
    structured `evidence_refs` (including a `logs_command`-bearing entry
    and a plain string) and whose candidate carries `head_sha`/`repo_path`/
    `pr` -- values verbatim through the real `orc dispatch` -> `orc refs`
    pipeline, not just the unit-level row builders above."""

    def test_rows_present_with_values_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"head_sha": "abc123def456", "repo_path": "/abs/some-repo", "pr": 42},
                            "assurance": {
                                "verdict": "accepted",
                                "evidence_refs": [
                                    "evidence-plain-string",
                                    {
                                        "no_mistakes_run_id": "r1",
                                        "repo_path": "/abs/some-repo",
                                        "command": "no-mistakes axi status --run r1",
                                        "step": "review",
                                        "logs_command": "no-mistakes axi logs --run r1 --step review --full",
                                    },
                                ],
                            },
                        }
                    ]
                }
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "refs evidence demo", "--config", str(config_path), "--run-id", "refs-evidence")
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "refs", "refs-evidence")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            out = result.stdout

            self.assertIn("evidence-plain-string", out)
            self.assertIn("(resolve: -)", out)  # the plain-string evidence row
            self.assertIn("no-mistakes axi logs --run r1 --step review --full", out)
            self.assertIn("git -C /abs/some-repo show abc123def456 --stat", out)
            self.assertIn("gh pr view 42", out)


class RefsExecutionSessionCraftedJournalTest(unittest.TestCase):
    """`execution-session/v1` fixture crafted directly through the
    Orchestrator + a real `JSONLJournal` (see module docstring for why
    `orc dispatch --config` isn't used for this source)."""

    DRID = "refs-session"
    WORK_ID = "work-1"

    def _build_journal(self, directory: Path) -> None:
        payload = {
            "execution-session/v1": {
                "provider": "acpx-pi",
                "native_session_id": "sess-9f2c",
                "resume": {"strength": "best-effort", "ref": "resume-ref-9f2c"},
                "transcript_ref": str(directory / "transcript.log"),
            }
        }
        journal = JSONLJournal(directory)
        work_graph = MemoryWorkGraph()
        execution = ScriptedExecution(script={self.WORK_ID: [{"outcome": "completed", "extensions": payload}]})
        candidate_content = {"label": "C1"}
        execution_id = predicted_execution_id(delivery_run_id=self.DRID, work_id=self.WORK_ID, attempt_number=1)
        candidate = ScriptedCandidate(
            subjects={execution_id: {"work_id": self.WORK_ID, "subject_identity": candidate_content}},
            current_by_work={},
        )
        assurance = ScriptedAssurance(script={fingerprint_of(candidate_content): {"verdict": "accepted"}})
        orchestrator = Orchestrator(
            delivery_run_id=self.DRID,
            journal=journal,
            work_graph=work_graph,
            execution=execution,
            candidate=candidate,
            assurance=assurance,
            config=RunConfig(max_attempts=3),
        )
        orchestrator.bootstrap(intent_id=self.DRID, text="session refs fixture", plan=default_single_work_plan(self.WORK_ID))
        orchestrator.run()

    def test_session_resume_transcript_rows_via_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            self._build_journal(journal_dir)

            result = _run_cli(tmp_dir, "refs", self.DRID, "--journal", str(journal_dir))
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            out = result.stdout
            self.assertIn("session", out)
            self.assertIn("sess-9f2c", out)
            self.assertIn("acpx pi sessions history sess-9f2c", out)
            self.assertIn("resume-ref-9f2c", out)
            self.assertIn(f"cat {tmp_dir / '.orc' / 'transcript.log'}", out)


class RefsMirrorCliTest(unittest.TestCase):
    def test_mirror_row_present_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            stub_bin = install_stub(tmp_dir)
            workspace = tmp_dir / "bd-workspace"
            (workspace / ".beads").mkdir(parents=True)
            config = {
                "mirror": {"adapter": "beads", "workspace": str(workspace), "bd_bin": str(stub_bin)},
                "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "m1"}, "assurance": {"verdict": "accepted"}}]},
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            env = {"ORC_BEADS_STUB_LOG": str(tmp_dir / "bd-stub.log")}
            dispatch = _run_cli(tmp_dir, "dispatch", "mirror refs demo", "--config", str(config_path), "--run-id", "refs-mirror", env=env)
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "refs", "refs-mirror")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("mirror", result.stdout)
            self.assertIn("run:refs-mirror", result.stdout)
            self.assertIn(f"bd --json -C {workspace} list --label run:refs-mirror", result.stdout)


if __name__ == "__main__":
    unittest.main()
