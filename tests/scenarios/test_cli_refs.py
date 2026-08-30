"""`orc refs` (GitHub issue #100 part 1) and `orc refs --resolve`/
`--resolve-all` (`TASK-M3C-002`, part 2): pure journal-projection tests
for `orc_werk.cli.refs`, mirroring `test_cli_beads_mirror_wiring.py`'s
mixed shape -- unit-level coverage of the per-source row builders and the
`ResolveCommand`/allowlist/selector/execution machinery, plus subprocess-
driven CLI wiring/regression coverage matching `test_cli_report.py`'s
pattern.

`execution-session/v1` fixtures are crafted directly through
`orc_werk.app.Orchestrator` + a real `JSONLJournal` (`test_extension_
lossless_transport.py`'s pattern). `evidence_refs`/candidate/mirror
fixtures use the ordinary `orc dispatch --config` path.

`--resolve`/`--resolve-all` execution tests run the real CLI subprocess
with a deliberately restricted `PATH=/usr/bin:/bin` (matching `_run_cli`'s
existing env below) -- `cat`/`git` are real binaries there (used for
genuine success-path resolution: `cat` on a fixture transcript file,
`git show` in a real fixture repo), while `acpx`/`bd`/`no-mistakes`/`gh`
are deliberately absent, giving an honest "binary not found" degrade path
with no stubbing required.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from orc_werk.adapters.jsonl import layout
from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate, fingerprint_of
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app import Orchestrator, RunConfig, default_single_work_plan
from orc_werk.cli.refs import (
    RESOLVE_OUTPUT_CAP_BYTES,
    RefRow,
    ResolveCommand,
    _assurance_context_rows,
    _candidate_rows,
    _command_field,
    _evidence_ref_rows,
    _execution_session_rows,
    _mirror_row,
    _render_resolution,
    _select_row,
    _session_resolve,
    _vet_read_only,
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
        resolve = _session_resolve("acpx-pi", "sess-123")
        self.assertEqual(resolve.display, "acpx pi sessions history sess-123")
        self.assertEqual(resolve.argv, ("acpx", "pi", "sessions", "history", "sess-123"))

    def test_non_acpx_provider_renders_no_resolve(self) -> None:
        self.assertEqual(_session_resolve("some-other-provider", "sess-123").display, "-")
        self.assertEqual(_session_resolve(None, "sess-123").display, "-")
        self.assertEqual(_session_resolve("acpx-", "sess-123").display, "-")  # empty agent name


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
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "evidence")
        self.assertEqual(rows[0].provider, "-")
        self.assertEqual(rows[0].value, "evidence-for-fp-1")
        self.assertEqual(rows[0].resolve, ResolveCommand.none())

    def test_structured_entry_with_command_field_surfaces_resolve(self) -> None:
        entry = {
            "no_mistakes_run_id": "r1",
            "repo_path": "/abs/repo",
            "command": "no-mistakes axi status --run r1",
        }
        rows = _evidence_ref_rows(self._history([entry]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].resolve.display, "no-mistakes axi status --run r1")
        self.assertEqual(rows[0].resolve.argv, ("no-mistakes", "axi", "status", "--run", "r1"))
        self.assertIsNone(rows[0].resolve.refusal)
        # value carries the entry verbatim (portable JSON), not a summary.
        self.assertEqual(json.loads(rows[0].value), entry)

    def test_unknown_future_shape_passes_through_never_crashes(self) -> None:
        entry = {"future_field": "an-unregistered-shape", "nested": {"a": [1, 2, 3]}}
        rows = _evidence_ref_rows(self._history([entry]))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].resolve, ResolveCommand.none())
        self.assertEqual(json.loads(rows[0].value), entry)

    def test_mutating_command_field_is_refused_never_executable(self) -> None:
        """Safety-critical: a crafted journal evidence entry whose `command`
        field is a mutating provider command must never become an
        executable argv -- `_vet_read_only` refuses it and the row keeps
        only the manual display (TASK-M3C-002's judge-only bar)."""
        for command in ("git push origin main", "bd create --title pwned", "rm -rf /"):
            entry = {"command": command}
            rows = _evidence_ref_rows(self._history([entry]))
            self.assertEqual(len(rows), 1, msg=command)
            self.assertIsNone(rows[0].resolve.argv, msg=command)
            self.assertIsNotNone(rows[0].resolve.refusal, msg=command)
            self.assertEqual(rows[0].resolve.display, command, msg=command)

    def test_malformed_command_text_degrades_to_raw_display(self) -> None:
        entry = {"command": "git show 'unterminated"}
        rows = _evidence_ref_rows(self._history([entry]))
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].resolve.argv)
        self.assertIsNotNone(rows[0].resolve.refusal)
        self.assertEqual(rows[0].resolve.display, "git show 'unterminated")

    def test_absent_evidence_refs_yields_no_rows(self) -> None:
        history = [{"kind": "fact", "id": "FACT-ASSURE-SETTLED", "data": {"assurance_id": "a1", "verdict": "accepted"}}]
        self.assertEqual(_evidence_ref_rows(history), [])


class AssuranceContextRowsUnitTest(unittest.TestCase):
    def test_recorded_base_surfaces_identity_and_ref(self) -> None:
        base = {"identity": "base-sha-immutable", "ref": "master", "relation": "merge-base"}
        history = [{
            "kind": "fact",
            "id": "FACT-ASSURE-SETTLED",
            "data": {"verdict": "accepted"},
            "extensions": {"assurance-context/v1": {"base": base}},
        }]
        rows = _assurance_context_rows(history)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "base")
        self.assertEqual(json.loads(rows[0].value), base)
        self.assertEqual(rows[0].verdict, "accepted")
        self.assertEqual(rows[0].resolve, ResolveCommand.none())

    def test_absent_extension_yields_no_false_base_row(self) -> None:
        history = [{
            "kind": "fact",
            "id": "FACT-ASSURE-SETTLED",
            "data": {"verdict": "accepted"},
            "extensions": {"review-findings/v1": {"findings": []}},
        }]
        self.assertEqual(_assurance_context_rows(history), [])


class AssuranceContextCliTest(unittest.TestCase):
    def _dispatch_and_refs(self, directory: Path, run_id: str, extensions: dict | None) -> str:
        assurance = {"verdict": "accepted"}
        if extensions is not None:
            assurance["extensions"] = extensions
        config = {
            "attempts": {
                "work-1": [{
                    "outcome": "completed",
                    "candidate": {"label": "C1"},
                    "assurance": assurance,
                }]
            }
        }
        path = directory / f"{run_id}.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        dispatched = _run_cli(directory, "dispatch", "audit base", "--config", str(path), "--run-id", run_id)
        self.assertEqual(dispatched.returncode, 0, msg=dispatched.stdout + dispatched.stderr)
        rendered = _run_cli(directory, "refs", run_id)
        self.assertEqual(rendered.returncode, 0, msg=rendered.stdout + rendered.stderr)
        return rendered.stdout

    def test_refs_surfaces_base_and_absence_renders_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with_base = self._dispatch_and_refs(
                directory,
                "with-base",
                {"assurance-context/v1": {"base": {"identity": "deadbeef-immutable", "ref": "master"}}},
            )
            self.assertIn("base", with_base)
            self.assertIn("deadbeef-immutable", with_base)
            self.assertIn('"ref":"master"', with_base)

            without_base = self._dispatch_and_refs(directory, "without-base", None)
            self.assertNotIn("deadbeef-immutable", without_base)
            self.assertNotRegex(without_base, r"(?m)^\[\d+\] base\s")


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
        self.assertEqual(len(rows), 3)
        session, resume, transcript = rows
        self.assertEqual((session.kind, session.provider, session.value), ("session", "acpx-pi", "sess-9f2c"))
        self.assertEqual(session.resolve.display, "acpx pi sessions history sess-9f2c")
        self.assertEqual(session.resolve.argv, ("acpx", "pi", "sessions", "history", "sess-9f2c"))
        self.assertEqual((resume.kind, resume.provider, resume.value), ("resume", "acpx-pi", "resume-ref-9f2c"))
        self.assertEqual(resume.resolve, ResolveCommand.none())
        self.assertEqual(
            (transcript.kind, transcript.provider, transcript.value),
            ("transcript", "acpx-pi", "/abs/transcript.log"),
        )
        self.assertEqual(transcript.resolve.display, "cat /abs/transcript.log")
        self.assertEqual(transcript.resolve.argv, ("cat", "/abs/transcript.log"))

    def test_minimal_payload_yields_session_row_only(self) -> None:
        payload = {"provider": "opaque-provider-c", "native_session_id": "opaque-session-55zz"}
        rows = _execution_session_rows(self._history(payload))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "session")
        self.assertEqual(rows[0].resolve, ResolveCommand.none())

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
        self.assertEqual(rows[0].resolve.display, "git -C /abs/repo show abc123 --stat")
        self.assertEqual(rows[0].resolve.argv, ("git", "-C", "/abs/repo", "show", "abc123", "--stat"))

    def test_head_sha_without_repo_path_has_no_resolve(self) -> None:
        rows = _candidate_rows(self._history({"head_sha": "abc123"}))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].resolve, ResolveCommand.none())

    def test_candidate_branch_is_preserved_when_present(self) -> None:
        rows = _candidate_rows(self._history({"head_sha": "abc123", "branch": "feature/verdict"}))
        self.assertEqual(json.loads(rows[0].value), {"head_sha": "abc123", "branch": "feature/verdict"})

    def test_pr_alone_yields_gh_resolve_display_but_not_executable(self) -> None:
        # issue #94 folded item / PR #104 verifier recommendation:
        # `gh pr view <pr>` is surfaced whenever the candidate carries `pr`,
        # with no same-`subject_identity` repo/URL sibling-field gate --
        # matching orc_werk.cli.affordances._candidate_pr's own
        # unconditional precedent for the ACCEPTED-state next: block. `gh`
        # is not in TASK-M3C-002's execution allowlist, so the display
        # command is unchanged but argv is refused (see _vet_read_only).
        rows = _candidate_rows(self._history({"pr": 42}))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "candidate-pr")
        self.assertEqual(rows[0].resolve.display, "gh pr view 42")
        self.assertIsNone(rows[0].resolve.argv)
        self.assertIsNotNone(rows[0].resolve.refusal)

    def test_pr_with_repo_context_field_yields_gh_resolve(self) -> None:
        rows = _candidate_rows(self._history({"pr": 42, "repo_path": "/abs/repo"}))
        pr_row = next(r for r in rows if r.kind == "candidate-pr")
        self.assertEqual(pr_row.resolve.display, "gh pr view 42")

    def test_no_candidate_effect_yields_no_rows(self) -> None:
        self.assertEqual(_candidate_rows([]), [])


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
                row.resolve.display,
                "bd --json -C /abs/bd-workspace list --label run:run-1 --status all",
            )
            self.assertEqual(
                row.resolve.argv,
                ("bd", "--json", "-C", "/abs/bd-workspace", "list", "--label", "run:run-1", "--status", "all"),
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
            self.assertIn("verdict=accepted", out)
            self.assertIn("(resolve: -)", out)  # the plain-string evidence row
            self.assertIn("no-mistakes axi logs --run r1 --step review --full", out)
            self.assertIn("git -C /abs/some-repo show abc123def456 --stat", out)
            self.assertIn("gh pr view 42", out)


class RefsExecutionSessionCraftedJournalTest(unittest.TestCase):
    """`execution-session/v1` fixture crafted directly through the
    Orchestrator + a real `JSONLJournal`."""

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
            self.assertIn(
                f"bd --json -C {workspace} list --label run:refs-mirror --status all",
                result.stdout,
            )

    def test_resolve_accepted_mirror_includes_closed_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            mirror_stub = install_stub(tmp_dir)
            workspace = tmp_dir / "bd-workspace"
            (workspace / ".beads").mkdir(parents=True)
            config = {
                "mirror": {"adapter": "beads", "workspace": str(workspace), "bd_bin": str(mirror_stub)},
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"label": "m1"},
                            "assurance": {"verdict": "accepted"},
                        }
                    ]
                },
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(
                tmp_dir,
                "dispatch",
                "accepted mirror resolve demo",
                "--config",
                str(config_path),
                "--run-id",
                "refs-mirror-accepted",
                env={"ORC_BEADS_STUB_LOG": str(tmp_dir / "bd-stub.log")},
            )
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            bin_dir = tmp_dir / "bin"
            bin_dir.mkdir()
            bd = bin_dir / "bd"
            bd.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "issue = {'id': 'refs-mirror-accepted--work-1', 'status': 'closed'}\n"
                "print(json.dumps([issue] if '--status' in sys.argv and sys.argv[sys.argv.index('--status') + 1] == 'all' else []))\n",
                encoding="utf-8",
            )
            bd.chmod(0o755)
            result = _run_cli(
                tmp_dir,
                "refs",
                "refs-mirror-accepted",
                "--resolve",
                "mirror",
                env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertNotIn("REFUSED", result.stdout)
            self.assertIn("refs-mirror-accepted--work-1", result.stdout)
            self.assertNotIn("\n[]\n", result.stdout)


# ---------------------------------------------------------------------------
# TASK-M3C-002: ResolveCommand single-source, allowlist vetting, selector,
# execution (success/refusal/failure/truncation)
# ---------------------------------------------------------------------------


class ResolveCommandSingleSourceUnitTest(unittest.TestCase):
    """Mutation-honest single-source guarantee: `ResolveCommand.of`'s
    `display` is mechanically DERIVED from `argv` (`" ".join`), never a
    second hand-maintained copy -- changing the argv given to `of` changes
    the display it returns, every time, with no way to construct a
    `ResolveCommand` whose vetted `argv` and `display` name different
    commands."""

    def test_display_is_derived_from_argv_changing_argv_changes_display(self) -> None:
        first = ResolveCommand.of(["cat", "/abs/one.log"])
        second = ResolveCommand.of(["cat", "/abs/two.log"])
        self.assertEqual(first.display, "cat /abs/one.log")
        self.assertEqual(second.display, "cat /abs/two.log")
        self.assertNotEqual(first.display, second.display)
        self.assertEqual(first.display, " ".join(first.argv))
        self.assertEqual(second.display, " ".join(second.argv))

    def test_refused_argv_still_derives_display_from_the_same_argv(self) -> None:
        # A refused command (tool/subcommand outside the allowlist) has no
        # executable argv, but its display is still exactly the argv that
        # was vetted and rejected -- never a different, manually-typed
        # string -- so the listing never claims a command was runnable
        # that in fact differs from what was checked.
        refused = ResolveCommand.of(["git", "push", "origin", "main"])
        self.assertIsNone(refused.argv)
        self.assertEqual(refused.display, "git push origin main")

    def test_from_raw_text_display_is_rederived_from_parsed_argv(self) -> None:
        # A journal-carried command string round-trips through shlex
        # parse -> vet -> " ".join, not preserved verbatim -- so its
        # display can never silently diverge from the argv --resolve would
        # actually execute.
        resolved = ResolveCommand.from_raw_text("cat   /abs/spaced.log")
        self.assertEqual(resolved.argv, ("cat", "/abs/spaced.log"))
        self.assertEqual(resolved.display, "cat /abs/spaced.log")


class VetReadOnlyUnitTest(unittest.TestCase):
    """The read-only allowlist itself (TASK-M3C-002's per-tool vetting):
    cat; git show/--stat forms; acpx sessions history/show; bd list/show;
    no-mistakes axi status/logs -- nothing else."""

    def test_vetted_forms_pass(self) -> None:
        vetted = [
            ["cat", "/abs/transcript.log"],
            ["git", "show", "abc123", "--stat"],
            ["git", "-C", "/abs/repo", "show", "abc123", "--stat"],
            ["acpx", "pi", "sessions", "history", "sess-1"],
            ["acpx", "pi", "sessions", "show", "sess-1"],
            ["bd", "list", "--label", "run:x"],
            ["bd", "--json", "-C", "/abs/ws", "list", "--label", "run:x", "--status", "all"],
            ["bd", "--json", "-C", "/abs/ws", "show", "bd-1"],
            ["no-mistakes", "axi", "status", "--run", "r1"],
            ["no-mistakes", "axi", "logs", "--run", "r1", "--step", "review", "--full"],
        ]
        for argv in vetted:
            self.assertIsNone(_vet_read_only(argv), msg=argv)

    def test_refused_forms(self) -> None:
        refused = [
            [],
            ["cat"],
            ["cat", "a", "b"],
            ["git", "push", "origin", "main"],
            ["git", "-C", "/abs/repo", "commit", "-m", "x"],
            ["acpx", "pi", "sessions", "delete", "sess-1"],
            ["acpx", "pi", "prompt", "sess-1"],
            ["bd", "create", "--title", "x"],
            ["bd", "--json", "-C", "/abs/ws", "update", "bd-1"],
            ["no-mistakes", "axi", "run"],
            ["no-mistakes", "push"],
            ["gh", "pr", "view", "1"],
            ["rm", "-rf", "/"],
            ["sh", "-c", "echo pwned"],
        ]
        for argv in refused:
            self.assertIsNotNone(_vet_read_only(argv), msg=argv)


class VetFlagDepthUnitTest(unittest.TestCase):
    """TASK-M3C-002 fix round (verifier F-ALLOWLIST-FLAG-DEPTH-GENERAL):
    the vet must constrain post-subcommand FLAGS per tool, not just the
    subcommand -- otherwise `git show --output=<path>` (a write primitive)
    passes because its subcommand is `show`. Every allowlisted tool gets a
    flag policy, not free-form-after-subcommand."""

    def test_git_show_writer_and_exec_flags_are_refused(self) -> None:
        # THE ESCAPE and its whole class: git show's file-writing / external-
        # command-driving options must all be refused even though `show`
        # itself is allowed.
        for argv in [
            ["git", "show", "--output=/tmp/x", "HEAD"],
            ["git", "-C", "/abs/repo", "show", "--output=/tmp/x", "HEAD"],
            ["git", "show", "-o", "/tmp/x", "HEAD"],
            ["git", "show", "-o/tmp/x", "HEAD"],
            ["git", "show", "-O/tmp/orderfile", "HEAD"],
            ["git", "show", "--ext-diff", "HEAD"],
            ["git", "show", "--textconv", "HEAD"],
            ["git", "show", "--unknown-future-flag", "HEAD"],
        ]:
            reason = _vet_read_only(argv)
            self.assertIsNotNone(reason, msg=argv)
            self.assertIn("allowlist", reason, msg=argv)

    def test_git_show_readonly_flags_and_bare_sha_pass(self) -> None:
        for argv in [
            ["git", "show", "HEAD"],
            ["git", "show", "abc123", "--stat"],
            ["git", "show", "--stat", "abc123"],
            ["git", "show", "--numstat", "--name-only", "abc123"],
            ["git", "-C", "/abs/repo", "show", "abc123", "--stat"],
        ]:
            self.assertIsNone(_vet_read_only(argv), msg=argv)

    def test_git_show_value_flag_value_is_not_reparsed_as_flag(self) -> None:
        # -C consumes its path value unparsed; a `-`-leading path can't be
        # read as an option (git errors on the chdir, contained) -- but more
        # importantly it is NOT treated as a flag-injection here.
        self.assertIsNone(_vet_read_only(["git", "-C", "/abs/repo", "show", "abc123"]))

    def test_git_c_config_injection_refused(self) -> None:
        # `git -c <cfg>` (the GIT_EXTERNAL_DIFF config-exec vector) is
        # blocked by the `-C`-only prefix rule: rest[0] != "show".
        self.assertIsNotNone(_vet_read_only(["git", "-c", "core.pager=sh", "show", "HEAD"]))

    def test_no_mistakes_follow_refused_run_step_full_pass(self) -> None:
        self.assertIsNotNone(_vet_read_only(["no-mistakes", "axi", "logs", "--run", "r1", "--follow"]))
        self.assertIsNone(_vet_read_only(["no-mistakes", "axi", "logs", "--run", "r1", "--step", "review", "--full"]))
        self.assertIsNotNone(_vet_read_only(["no-mistakes", "axi", "status", "--output", "/tmp/x"]))

    def test_bd_audited_read_only_flags_pass_for_list_and_show(self) -> None:
        for subcommand, positionals in (("list", []), ("show", ["bd-1"])):
            for flag in ("--json", "--no-pager"):
                argv = ["bd", subcommand, *positionals, flag]
                self.assertIsNone(_vet_read_only(argv), msg=argv)

    def test_bd_dangerous_flags_are_refused_for_list_and_show(self) -> None:
        dangerous = {
            "--watch": [],
            "-w": [],
            "--format": ["{{.Title}}"],
            "--db": ["/tmp/attacker.db"],
            "--actor": ["attacker"],
            "--global": [],
            "--dolt-auto-commit": ["on"],
            "--ignore-schema-skew": [],
        }
        for subcommand, positionals in (("list", []), ("show", ["bd-1"])):
            for flag, values in dangerous.items():
                argv = ["bd", subcommand, *positionals, flag, *values]
                reason = _vet_read_only(argv)
                self.assertIsNotNone(reason, msg=argv)
                self.assertIn("allowlist", reason, msg=argv)

    def test_bd_unknown_novel_flag_remains_fail_closed(self) -> None:
        for argv in (
            ["bd", "list", "--novel-future-flag"],
            ["bd", "show", "bd-1", "--novel-future-flag"],
        ):
            self.assertIsNotNone(_vet_read_only(argv), msg=argv)

    def test_builder_bd_resolve_flags_pass(self) -> None:
        argv = [
            "bd", "--json", "-C", "/abs/ws", "list",
            "--label", "run:x", "--status", "all",
        ]
        self.assertIsNone(_vet_read_only(argv))

    def test_over_block_guard_dangerous_token_as_a_value_still_passes(self) -> None:
        # A security allowlist must be tested for OVER-blocking, not only
        # under-blocking: a legitimately safe read-only command that merely
        # *mentions* a refused token as a value-flag's VALUE (consumed
        # unparsed, never in flag position) must still pass. This is the
        # must-allow half of the policy -- the analog of a shell guard that
        # blocks `git push --force` while letting
        # `git commit -m "no --force here"` through. If any of these ever
        # start refusing, the allowlist has grown a false positive that would
        # silently degrade a real resolve command to the manual fallback.
        must_pass = [
            # `--watch`/`--db`/`--format` appear as the VALUE of `--label`/
            # `--status`, not as flags; value-flags consume their value
            # unparsed, so the dangerous shape is inert here.
            ["bd", "list", "--label", "run:--watch", "--status", "all"],
            ["bd", "list", "--label", "--watch"],
            ["bd", "list", "--status", "all", "--label", "project:--db"],
            ["bd", "show", "--label", "run:--format", "bd-1"],
            # a bare sha positional to `git show` is not a flag and must pass
            ["git", "show", "abc123"],
        ]
        for argv in must_pass:
            self.assertIsNone(_vet_read_only(argv), msg=argv)

    def test_acpx_agent_leading_dash_refused(self) -> None:
        # A crafted provider string `acpx---output` yields agent `--output`,
        # which acpx would parse as an option before `sessions`.
        self.assertIsNotNone(_vet_read_only(["acpx", "--output=/tmp/x", "sessions", "history", "s1"]))
        self.assertIsNotNone(_vet_read_only(["acpx", "pi", "sessions", "history", "--output=/tmp/x"]))
        self.assertIsNone(_vet_read_only(["acpx", "pi", "sessions", "history", "s1"]))


class BuilderFlagInjectionGuardUnitTest(unittest.TestCase):
    """The builder must never MINT a token that could be read as a flag
    (defense in depth beyond the vetter): a journal-derived `head_sha`/
    `repo_path`/acpx-agent/session-ref beginning with `-` is refused at
    BUILD time with a clear reason, argv left None."""

    def test_candidate_head_sha_output_flag_is_refused_at_build(self) -> None:
        history = [
            {
                "kind": "effect",
                "id": "FX-IDENTIFY-CANDIDATE",
                "data": {
                    "work_id": "w1",
                    "dispatch_result": {
                        "candidate": {
                            "id": "c1",
                            "subject_identity": {"head_sha": "--output=/tmp/x", "repo_path": "/abs/repo"},
                            "fingerprint": "fp",
                        }
                    },
                },
            }
        ]
        rows = _candidate_rows(history)
        candidate = next(r for r in rows if r.kind == "candidate")
        self.assertIsNone(candidate.resolve.argv)
        self.assertIsNotNone(candidate.resolve.refusal)
        self.assertIn("begins with '-'", candidate.resolve.refusal)
        # display still shows exactly what would have run (refused).
        self.assertIn("--output=/tmp/x", candidate.resolve.display)

    def test_candidate_repo_path_leading_dash_is_refused_at_build(self) -> None:
        history = [
            {
                "kind": "effect",
                "id": "FX-IDENTIFY-CANDIDATE",
                "data": {
                    "work_id": "w1",
                    "dispatch_result": {
                        "candidate": {
                            "id": "c1",
                            "subject_identity": {"head_sha": "abc123", "repo_path": "--upload-pack=sh"},
                            "fingerprint": "fp",
                        }
                    },
                },
            }
        ]
        rows = _candidate_rows(history)
        candidate = next(r for r in rows if r.kind == "candidate")
        self.assertIsNone(candidate.resolve.argv)
        self.assertIsNotNone(candidate.resolve.refusal)

    def test_acpx_agent_leading_dash_refused_at_build(self) -> None:
        rows = _execution_session_rows(
            [
                {
                    "kind": "fact",
                    "id": "FACT-EXEC-SETTLED",
                    "data": {},
                    "extensions": {
                        "execution-session/v1": {"provider": "acpx---output=/tmp/x", "native_session_id": "s1"}
                    },
                }
            ]
        )
        session = next(r for r in rows if r.kind == "session")
        self.assertIsNone(session.resolve.argv)
        self.assertIsNotNone(session.resolve.refusal)


class SelectRowUnitTest(unittest.TestCase):
    def _rows(self) -> list[RefRow]:
        return [
            RefRow(kind="session", provider="acpx-pi", value="sess-1", resolve=ResolveCommand.none()),
            RefRow(kind="transcript", provider="acpx-pi", value="/abs/t.log", resolve=ResolveCommand.of(["cat", "/abs/t.log"])),
            RefRow(kind="evidence", provider="-", value="ev-a", resolve=ResolveCommand.none()),
            RefRow(kind="evidence", provider="-", value="ev-b", resolve=ResolveCommand.none()),
        ]

    def test_valid_index_selects_the_matching_row(self) -> None:
        rows = self._rows()
        index, row = _select_row(rows, "2")
        self.assertEqual(index, 2)
        self.assertIs(row, rows[1])

    def test_out_of_range_index_is_validation_error_with_next(self) -> None:
        rows = self._rows()
        with self.assertRaises(Exception) as ctx:
            _select_row(rows, "99")
        error = ctx.exception.to_canonical()
        self.assertEqual(error["error"], "ERR-VALIDATION")
        self.assertIn("next", error)
        self.assertTrue(error["next"])

    def test_zero_refs_out_of_range_next_points_at_listing(self) -> None:
        with self.assertRaises(Exception) as ctx:
            _select_row([], "1")
        error = ctx.exception.to_canonical()
        self.assertEqual(error["error"], "ERR-VALIDATION")
        self.assertIn("0 refs", " ".join(error["next"]))

    def test_kind_selector_with_single_match_selects_it(self) -> None:
        rows = self._rows()
        index, row = _select_row(rows, "transcript")
        self.assertEqual(index, 2)
        self.assertIs(row, rows[1])

    def test_kind_selector_with_no_match_is_validation_error_with_next(self) -> None:
        rows = self._rows()
        with self.assertRaises(Exception) as ctx:
            _select_row(rows, "candidate")
        error = ctx.exception.to_canonical()
        self.assertEqual(error["error"], "ERR-VALIDATION")
        self.assertIn("next", error)

    def test_kind_selector_ambiguous_is_validation_error_naming_indices(self) -> None:
        rows = self._rows()
        with self.assertRaises(Exception) as ctx:
            _select_row(rows, "evidence")
        error = ctx.exception.to_canonical()
        self.assertEqual(error["error"], "ERR-VALIDATION")
        self.assertIn("[3]", error["message"])
        self.assertIn("[4]", error["message"])
        self.assertIn("next", error)

    def test_kind_and_substring_selector_narrows_to_one_match(self) -> None:
        rows = self._rows()
        index, row = _select_row(rows, "evidence:ev-b")
        self.assertEqual(index, 4)
        self.assertIs(row, rows[3])


class RenderResolutionUnitTest(unittest.TestCase):
    """`_render_resolution` in isolation, exercising the execution/refusal/
    error/truncation branches directly against `RefRow` fixtures."""

    def test_no_resolve_command_available(self) -> None:
        row = RefRow(kind="resume", provider="acpx-pi", value="resume-ref", resolve=ResolveCommand.none())
        lines = _render_resolution(1, row)
        self.assertIn("no resolve command available for this ref", lines)

    def test_refused_command_prints_reason_and_manual_command(self) -> None:
        row = RefRow(kind="evidence", provider="-", value="ev", resolve=ResolveCommand.of(["git", "push", "origin", "main"]))
        lines = _render_resolution(1, row)
        joined = "\n".join(lines)
        self.assertIn("REFUSED:", joined)
        self.assertIn("manual command: git push origin main", joined)

    def test_successful_cat_execution_prints_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.log"
            path.write_text("hello from the fixture transcript\n", encoding="utf-8")
            row = RefRow(kind="transcript", provider="acpx-pi", value=str(path), resolve=ResolveCommand.of(["cat", str(path)]))
            lines = _render_resolution(1, row)
            joined = "\n".join(lines)
            self.assertIn(f"cat {path}", joined)
            self.assertIn("hello from the fixture transcript", joined)

    def test_missing_binary_degrades_with_manual_command(self) -> None:
        # PATH restricted to a directory with nothing in it, regardless of
        # what happens to be installed on the host running this test suite
        # -- `no-mistakes` (or any other allowlisted tool) is guaranteed
        # absent under this PATH.
        with tempfile.TemporaryDirectory() as empty_bin, unittest.mock.patch.dict(os.environ, {"PATH": empty_bin}):
            row = RefRow(
                kind="evidence",
                provider="-",
                value="ev",
                resolve=ResolveCommand.of(["no-mistakes", "axi", "status", "--run", "r1"]),
            )
            lines = _render_resolution(1, row)
        joined = "\n".join(lines)
        self.assertIn("ERROR:", joined)
        self.assertIn("binary not found on PATH", joined)
        self.assertIn("manual command: no-mistakes axi status --run r1", joined)

    def test_nonzero_exit_degrades_with_manual_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = str(Path(tmp) / "does-not-exist.log")
            row = RefRow(
                kind="transcript",
                provider="acpx-pi",
                value=missing_path,
                resolve=ResolveCommand.of(["cat", missing_path]),
            )
            lines = _render_resolution(1, row)
            joined = "\n".join(lines)
            self.assertIn("ERROR:", joined)
            self.assertIn(f"manual command: cat {missing_path}", joined)

    def test_output_over_cap_is_truncated_with_definitive_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.log"
            total = RESOLVE_OUTPUT_CAP_BYTES * 2
            path.write_text("x" * total, encoding="utf-8")
            row = RefRow(kind="transcript", provider="acpx-pi", value=str(path), resolve=ResolveCommand.of(["cat", str(path)]))
            lines = _render_resolution(1, row)
            joined = "\n".join(lines)
            self.assertIn("x" * RESOLVE_OUTPUT_CAP_BYTES, joined)
            self.assertNotIn("x" * (RESOLVE_OUTPUT_CAP_BYTES + 1), joined)
            self.assertIn(f"... truncated, showing first {RESOLVE_OUTPUT_CAP_BYTES} of {total} bytes", joined)
            self.assertIn(f"run manually for full output: cat {path}", joined)


def _git_fixture_repo(repo_dir: Path) -> str:
    """A real, tiny git repo with one commit -- returns its head sha.
    Used to exercise `--resolve`'s `git show --stat` path against genuine
    `git` output rather than a mock."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "orc-werk-test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "orc-werk-test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
    )
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True, env=env)
    (repo_dir / "widget.txt").write_text("hello widget\n", encoding="utf-8")
    subprocess.run(["git", "add", "widget.txt"], cwd=repo_dir, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "add widget"], cwd=repo_dir, check=True, env=env)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, env=env, capture_output=True, text=True
    )
    return result.stdout.strip()


class RefsResolveCliTest(unittest.TestCase):
    """End-to-end `orc refs <run> --resolve`/`--resolve-all` over the real
    CLI subprocess (`_run_cli`'s restricted `PATH=/usr/bin:/bin`)."""

    def test_resolve_by_index_executes_cat_on_transcript_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            journal_dir = tmp_dir / ".orc"
            drid, work_id = "refs-resolve-transcript", "work-1"
            transcript_path = journal_dir / "transcript.log"

            def build() -> None:
                payload = {
                    "execution-session/v1": {
                        "provider": "acpx-pi",
                        "native_session_id": "sess-1",
                        "transcript_ref": str(transcript_path),
                    }
                }
                journal = JSONLJournal(journal_dir)
                work_graph = MemoryWorkGraph()
                execution = ScriptedExecution(script={work_id: [{"outcome": "completed", "extensions": payload}]})
                candidate_content = {"label": "C1"}
                execution_id = predicted_execution_id(delivery_run_id=drid, work_id=work_id, attempt_number=1)
                candidate = ScriptedCandidate(
                    subjects={execution_id: {"work_id": work_id, "subject_identity": candidate_content}},
                    current_by_work={},
                )
                assurance = ScriptedAssurance(script={fingerprint_of(candidate_content): {"verdict": "accepted"}})
                orchestrator = Orchestrator(
                    delivery_run_id=drid,
                    journal=journal,
                    work_graph=work_graph,
                    execution=execution,
                    candidate=candidate,
                    assurance=assurance,
                    config=RunConfig(max_attempts=3),
                )
                orchestrator.bootstrap(intent_id=drid, text="resolve transcript fixture", plan=default_single_work_plan(work_id))
                orchestrator.run()

            build()
            journal_dir.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("the fixture transcript's exact content\n", encoding="utf-8")

            listing = _run_cli(tmp_dir, "refs", drid, "--journal", str(journal_dir))
            self.assertEqual(listing.returncode, 0, msg=listing.stdout + listing.stderr)
            self.assertIn("[2]", listing.stdout)  # session=[1], transcript=[2]

            result = _run_cli(tmp_dir, "refs", drid, "--journal", str(journal_dir), "--resolve", "2")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn(f"[2] transcript (acpx-pi): cat {transcript_path}", result.stdout)
            self.assertIn("the fixture transcript's exact content", result.stdout)

            by_kind = _run_cli(tmp_dir, "refs", drid, "--journal", str(journal_dir), "--resolve", "transcript")
            self.assertEqual(by_kind.returncode, 0, msg=by_kind.stdout + by_kind.stderr)
            self.assertIn("the fixture transcript's exact content", by_kind.stdout)

    def test_resolve_git_show_against_fixture_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            repo_dir = tmp_dir / "fixture-repo"
            head_sha = _git_fixture_repo(repo_dir)
            config = {
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"head_sha": head_sha, "repo_path": str(repo_dir)},
                            "assurance": {"verdict": "accepted"},
                        }
                    ]
                }
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "resolve candidate demo", "--config", str(config_path), "--run-id", "refs-resolve-candidate")
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "refs", "refs-resolve-candidate", "--resolve", "candidate")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn(f"git -C {repo_dir} show {head_sha} --stat", result.stdout)
            self.assertIn("widget.txt", result.stdout)
            self.assertIn("add widget", result.stdout)

    def test_git_show_output_write_escape_evidence_path_writes_nothing(self) -> None:
        """PERMANENT REGRESSION for the verifier's proven escape (fix
        round, FINDING 1): a crafted journal whose evidence command is
        `git show --output=<target> ...` (a git file-write primitive)
        MUST refuse and write NOTHING. Reverting the per-tool flag guard
        makes this red (the file would be written, exit 0, rendered as
        normal output -- exactly the escape)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            repo_dir = tmp_dir / "fixture-repo"
            head_sha = _git_fixture_repo(repo_dir)
            target = tmp_dir / "PWNED_EVIDENCE"
            self.assertFalse(target.exists())
            config = {
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"label": "m1"},
                            "assurance": {
                                "verdict": "accepted",
                                "evidence_refs": [
                                    {"command": f"git -C {repo_dir} show --output={target} {head_sha}"}
                                ],
                            },
                        }
                    ]
                }
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "escape evidence", "--config", str(config_path), "--run-id", "esc-ev")
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "refs", "esc-ev", "--resolve-all")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("REFUSED:", result.stdout)
            self.assertIn("read-only flag allowlist", result.stdout)
            # THE assertion: nothing was written.
            self.assertFalse(target.exists(), msg=f"ESCAPE: {target} was written")

    def test_git_show_output_write_escape_builder_head_sha_path_writes_nothing(self) -> None:
        """PERMANENT REGRESSION for the builder reach path (fix round,
        FINDING 1): a crafted candidate `subject_identity.head_sha` of
        `--output=<target>` gets interpolated into the trusted git-show
        builder -- git would parse it as the write flag. The build-time
        guard MUST refuse and write NOTHING. Reverting the guard makes
        this red."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            repo_dir = tmp_dir / "fixture-repo"
            _git_fixture_repo(repo_dir)
            target = tmp_dir / "PWNED_BUILDER"
            self.assertFalse(target.exists())
            config = {
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"head_sha": f"--output={target}", "repo_path": str(repo_dir)},
                            "assurance": {"verdict": "accepted"},
                        }
                    ]
                }
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "escape builder", "--config", str(config_path), "--run-id", "esc-build")
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "refs", "esc-build", "--resolve-all")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("REFUSED:", result.stdout)
            self.assertIn("begins with '-'", result.stdout)
            # THE assertion: nothing was written.
            self.assertFalse(target.exists(), msg=f"ESCAPE: {target} was written")

    def test_resolve_refused_mutating_evidence_command_degrades_honestly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"label": "m1"},
                            "assurance": {
                                "verdict": "accepted",
                                "evidence_refs": [{"command": "git push origin main"}],
                            },
                        }
                    ]
                }
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "resolve refused demo", "--config", str(config_path), "--run-id", "refs-resolve-refused")
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "refs", "refs-resolve-refused", "--resolve", "1")
            # Refusal is not a run failure -- exit stays honest/0 (the ref
            # itself remains valid; only its resolution was refused).
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("REFUSED:", result.stdout)
            self.assertIn("manual command: git push origin main", result.stdout)

    def test_resolve_missing_binary_degrades_with_manual_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"label": "m1"},
                            "assurance": {
                                "verdict": "accepted",
                                "evidence_refs": [{"command": "no-mistakes axi status --run r1"}],
                            },
                        }
                    ]
                }
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "resolve missing binary demo", "--config", str(config_path), "--run-id", "refs-resolve-missing")
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "refs", "refs-resolve-missing", "--resolve", "1")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("ERROR: binary not found on PATH: 'no-mistakes'", result.stdout)
            self.assertIn("manual command: no-mistakes axi status --run r1", result.stdout)

    def test_resolve_selector_out_of_range_is_err_validation_with_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"label": "m1"},
                            "assurance": {"verdict": "accepted", "evidence_refs": ["plain-evidence"]},
                        }
                    ]
                }
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "resolve oob demo", "--config", str(config_path), "--run-id", "refs-resolve-oob")
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "refs", "refs-resolve-oob", "--resolve", "99")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("next", error)
            self.assertTrue(error["next"])

    def test_resolve_all_headers_every_row_with_a_resolve_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "attempts": {
                    "work-1": [
                        {
                            "outcome": "completed",
                            "candidate": {"label": "m1"},
                            "assurance": {
                                "verdict": "accepted",
                                "evidence_refs": [
                                    "no-resolve-plain-string",
                                    {"command": "no-mistakes axi status --run r1"},
                                ],
                            },
                        }
                    ]
                }
            }
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "resolve all demo", "--config", str(config_path), "--run-id", "refs-resolve-all")
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            result = _run_cli(tmp_dir, "refs", "refs-resolve-all", "--resolve-all")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            # Row [1] (the plain string, resolve "-") is skipped -- nothing
            # to resolve; row [2] (the no-mistakes command) gets a header
            # and its honest missing-binary degrade.
            self.assertNotIn("[1]", result.stdout)
            self.assertIn("[2] evidence (-): no-mistakes axi status --run r1", result.stdout)
            self.assertIn("ERROR: binary not found on PATH", result.stdout)

    def test_resolve_and_resolve_all_are_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "refs", "some-run", "--resolve", "1", "--resolve-all")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertIn("not allowed with argument", result.stderr)


if __name__ == "__main__":
    unittest.main()
