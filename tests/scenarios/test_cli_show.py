"""`orc show <run> [work]` (`TASK-M3C-001`): tests for `orc_werk.cli.show`.

Mirrors `test_cli_refs.py`'s mixed shape -- unit-level coverage of the pure
derivation helpers (prompt provenance, attempt segmentation, duration,
findings summarization) plus subprocess-driven CLI wiring/regression
coverage matching `test_cli_report.py`/`test_cli_acp_wiring.py`'s pattern.
Fixtures are built fresh inside temp directories -- never by reading this
repo's live `.orc/` journals -- so these tests never depend on that live
delivery-ledger content changing shape over time. Real reject-arc and
verdict-inheritance shapes are driven through `execution.adapter:
"scripted"` + `candidate.adapter: "git"` (`orc_werk.cli.config`'s
documented "lesser combination useful for testing the git-candidate wiring
without a live agent") against a real temporary git repository -- no ACP/
`acpx` dependency needed for either, since `GitDiffCandidate`'s
`candidate_id` is a pure function of worktree content (never of
execution/attempt identity, `src/orc_werk/adapters/git/candidate.py`),
exactly what makes an unchanged worktree re-observe the same candidate
across attempts. The one ACP-briefs scenario uses the existing `acpx` stub
harness (`tests/conformance/support_acpx_stub.py`), matching
`test_cli_acp_wiring.py`'s own no-live-Pi pattern.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orc_werk.adapters.acp.execution import session_name_for_idempotency_key
from orc_werk.cli.config import _IntentPromptExecution
from orc_werk.cli.show import (
    _duration_text,
    _finding_id,
    _finding_severity,
    _finding_summary,
    _segment_attempts,
    _truncate,
    prompt_provenance,
)
from orc_werk.core.effects import FX_START_EXECUTION
from orc_werk.core.idempotency import idempotency_key
from tests.conformance.support_acpx_stub import AcpxStubWorld

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


def _git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], cwd=path)
    _git(["config", "user.email", "show-test@example.invalid"], cwd=path)
    _git(["config", "user.name", "Show Test Fixture"], cwd=path)
    (path / "a.txt").write_text("x")
    _git(["add", "."], cwd=path)
    _git(["commit", "-q", "-m", "init"], cwd=path)


# ---------------------------------------------------------------------------
# Unit-level coverage of the pure derivation helpers
# ---------------------------------------------------------------------------


class PromptProvenanceUnitTest(unittest.TestCase):
    def test_no_config_is_unavailable(self) -> None:
        self.assertEqual(prompt_provenance(None, "work-1", "intent"), {"kind": "unavailable"})

    def test_scripted_default_is_no_prompt(self) -> None:
        self.assertEqual(prompt_provenance({}, "work-1", "intent"), {"kind": "no-prompt", "adapter": "scripted"})

    def test_explicit_non_acp_adapter_is_no_prompt(self) -> None:
        config = {"execution": {"adapter": "scripted"}}
        self.assertEqual(prompt_provenance(config, "work-1", "intent")["kind"], "no-prompt")

    def test_acp_with_brief_wins_over_intent(self) -> None:
        config = {"execution": {"adapter": "acp"}, "briefs": {"work-1": "the brief text"}}
        self.assertEqual(
            prompt_provenance(config, "work-1", "the intent text"),
            {"kind": "brief", "text": "the brief text"},
        )

    def test_acp_without_brief_entry_falls_back_to_intent(self) -> None:
        config = {"execution": {"adapter": "acp"}, "briefs": {"other-work": "irrelevant"}}
        self.assertEqual(
            prompt_provenance(config, "work-1", "the intent text"),
            {"kind": "intent", "text": "the intent text"},
        )

    def test_acp_with_no_briefs_at_all_falls_back_to_intent(self) -> None:
        config = {"execution": {"adapter": "acp"}}
        self.assertEqual(prompt_provenance(config, "work-1", "x")["kind"], "intent")

    def test_empty_string_brief_still_wins_present_key_semantics(self) -> None:
        # dict.get(key, default) semantics: a PRESENT key wins even when its
        # value is falsy -- this is the issue #111 "stub brief" shape (a
        # short, non-empty brief also wins the same way; the empty-string
        # edge case is the sharpest version of the same rule).
        config = {"execution": {"adapter": "acp"}, "briefs": {"work-1": ""}}
        self.assertEqual(prompt_provenance(config, "work-1", "intent")["kind"], "brief")


class PromptProvenanceAgreesWithDispatchWrapperTest(unittest.TestCase):
    """Composition-level regression: `show.prompt_provenance`'s derived
    text must never drift from what `_IntentPromptExecution._filled_request`
    (the code that ACTUALLY fills a real ACP execution's prompt at dispatch
    time, issue #82/#83) would have sent. If either derivation's precedence
    rule changes without the other, this test fails -- the two must always
    agree, since `show` claims to display the derived prompt provenance
    honestly, never a guess independent of what dispatch really does."""

    class _NeverCalledInner:
        def capabilities(self):
            return frozenset()

        def start(self, **_kwargs):
            raise AssertionError("not exercised by this test")

        def inspect(self, **_kwargs):
            raise AssertionError("not exercised by this test")

        def send(self, **_kwargs):
            raise AssertionError("not exercised by this test")

        def cancel(self, **_kwargs):
            raise AssertionError("not exercised by this test")

        def resume(self, **_kwargs):
            raise AssertionError("not exercised by this test")

    def test_brief_and_intent_fallback_agree_for_a_multi_work_config(self) -> None:
        briefs = {"a": "brief for a", "c": "brief for c"}
        config = {"execution": {"adapter": "acp", "cwd": "/tmp"}, "briefs": briefs}
        intent_text = "the run's own intent text"
        wrapper = _IntentPromptExecution(self._NeverCalledInner(), intent_text=intent_text, briefs=briefs)

        for work_id in ("a", "b", "c"):
            derived = prompt_provenance(config, work_id, intent_text)
            actual_prompt = wrapper._filled_request({}, work_id=work_id)["prompt"]
            self.assertEqual(
                derived["text"],
                actual_prompt,
                msg=f"show's derived prompt for {work_id!r} disagrees with the real dispatch wrapper",
            )
        # And the *kind* matches which works actually have a brief entry.
        self.assertEqual(prompt_provenance(config, "a", intent_text)["kind"], "brief")
        self.assertEqual(prompt_provenance(config, "b", intent_text)["kind"], "intent")
        self.assertEqual(prompt_provenance(config, "c", intent_text)["kind"], "brief")


class TruncateUnitTest(unittest.TestCase):
    def test_short_text_not_truncated(self) -> None:
        shown, truncated, total = _truncate("hello", limit=10)
        self.assertEqual((shown, truncated, total), ("hello", False, 5))

    def test_long_text_truncated_with_definitive_counts(self) -> None:
        shown, truncated, total = _truncate("x" * 500, limit=200)
        self.assertTrue(truncated)
        self.assertEqual(len(shown), 200)
        self.assertEqual(total, 500)


class SegmentAttemptsUnitTest(unittest.TestCase):
    def test_splits_at_each_fx_start_execution(self) -> None:
        records = [
            {"kind": "fact", "id": "FACT-WORK-CREATED", "data": {"work_id": "w1"}},
            {"kind": "effect", "id": "FX-START-EXECUTION", "data": {"work_id": "w1", "attempt_number": 1}},
            {"kind": "fact", "id": "FACT-EXEC-STARTED", "data": {"work_id": "w1"}},
            {"kind": "effect", "id": "FX-START-EXECUTION", "data": {"work_id": "w1", "attempt_number": 2}},
            {"kind": "fact", "id": "FACT-EXEC-STARTED", "data": {"work_id": "w1"}},
        ]
        attempts = _segment_attempts(records)
        self.assertEqual([n for n, _ in attempts], [1, 2])
        self.assertEqual(len(attempts[0][1]), 2)  # its own FX-START-EXECUTION + FACT-EXEC-STARTED
        self.assertEqual(len(attempts[1][1]), 2)

    def test_no_attempts_yields_empty_list(self) -> None:
        self.assertEqual(_segment_attempts([{"kind": "fact", "id": "FACT-WORK-CREATED", "data": {}}]), [])


class DurationTextUnitTest(unittest.TestCase):
    def test_both_times_present_yields_delta(self) -> None:
        started = {"seq": 1}
        settled = {"seq": 2}
        times = {1: "2026-01-01T00:00:00.000000Z", 2: "2026-01-01T00:00:10.500000Z"}
        text = _duration_text(times, started, settled)
        self.assertIsNotNone(text)
        self.assertIn("10.500s", text)

    def test_missing_times_yields_none_never_fabricated(self) -> None:
        self.assertIsNone(_duration_text({}, {"seq": 1}, {"seq": 2}))

    def test_missing_records_yields_none(self) -> None:
        self.assertIsNone(_duration_text({1: "x"}, None, {"seq": 1}))


class FindingsRenderUnitTest(unittest.TestCase):
    def test_id_falls_back_to_positional_when_absent(self) -> None:
        self.assertEqual(_finding_id({"title": "x"}, 3), "finding-3")
        self.assertEqual(_finding_id({"id": "trivia-noop-1"}, 1), "trivia-noop-1")

    def test_severity_falls_back_to_dash(self) -> None:
        self.assertEqual(_finding_severity({}), "-")
        self.assertEqual(_finding_severity({"severity": "high"}), "high")

    def test_summary_prefers_summary_then_title_then_detail(self) -> None:
        self.assertEqual(_finding_summary({"summary": "s", "title": "t", "detail": "d"}), "s")
        self.assertEqual(_finding_summary({"title": "t", "detail": "d"}), "t")
        self.assertEqual(_finding_summary({"detail": "d"}), "d")
        self.assertEqual(_finding_summary({}), "-")

    def test_summary_collapses_whitespace_and_caps_length(self) -> None:
        text = "line one\nline two   with   spaces " + ("z" * 300)
        summary = _finding_summary({"summary": text})
        self.assertNotIn("\n", summary)
        self.assertLessEqual(len(summary), 145)
        self.assertTrue(summary.endswith("..."))


# ---------------------------------------------------------------------------
# Subprocess CLI wiring
# ---------------------------------------------------------------------------


class ShowCliHelpTest(unittest.TestCase):
    def test_show_registered_in_top_level_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", "--help"],
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("show", result.stdout)

    def test_show_help_is_self_sufficient(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", "show", "--help"],
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("orc show", result.stdout)
        self.assertIn("--journal", result.stdout)


class ShowMissingRunTest(unittest.TestCase):
    def test_missing_run_is_err_not_found_with_next_no_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "show", "totally-nonexistent-run-id")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")
            self.assertTrue(error["next"])
            self.assertFalse((tmp_dir / ".orc").exists())


class ShowScriptedRunTest(unittest.TestCase):
    """Default fully-scripted config (no `execution`/`candidate` block):
    the honest "scripted execution -- no prompt" ASKED line, plus
    EXECUTED/PRODUCED/JUDGED/NEXT-DEEPER rendering and findings summary."""

    def _dispatch(self, tmp_dir: Path) -> str:
        config = {
            "attempts": {
                "work-1": [
                    {
                        "outcome": "completed",
                        "candidate": {"label": "c1"},
                        "assurance": {
                            "verdict": "accepted",
                            "evidence_refs": ["evidence-1"],
                            "extensions": {
                                "review-findings/v1": {
                                    "findings": [
                                        {"id": "f1", "severity": "low", "summary": "a minor note"},
                                        {"title": "no id or summary here", "severity": "info"},
                                    ]
                                }
                            },
                        },
                    }
                ]
            }
        }
        config_path = tmp_dir / "cfg.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        dispatch = _run_cli(tmp_dir, "dispatch", "scripted show demo", "--config", str(config_path), "--run-id", "show-scripted")
        self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)
        return "show-scripted"

    def test_no_prompt_honesty_and_findings_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            run_id = self._dispatch(tmp_dir)

            result = _run_cli(tmp_dir, "show", run_id)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            out = result.stdout
            self.assertIn("scripted execution (scripted) -- no prompt sent to the executor", out)
            self.assertIn("JUDGED: assurance=", out)
            self.assertIn("verdict=accepted", out)
            self.assertIn("evidence_refs: ['evidence-1']", out)
            self.assertIn("findings: 2", out)
            self.assertIn("[low] f1: a minor note", out)
            self.assertIn("[info] finding-2: no id or summary here", out)
            self.assertIn("now at ACCEPTED", out)
            self.assertIn("next:", out)

    def test_non_tty_output_has_zero_escape_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            run_id = self._dispatch(tmp_dir)
            result = _run_cli(tmp_dir, "show", run_id)
            self.assertNotIn("\x1b", result.stdout)

    def test_work_filter_shows_only_named_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            run_id = self._dispatch(tmp_dir)
            result = _run_cli(tmp_dir, "show", run_id, "work-1")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("work work-1:", result.stdout)

    def test_unknown_work_is_err_not_found_with_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            run_id = self._dispatch(tmp_dir)
            result = _run_cli(tmp_dir, "show", run_id, "no-such-work")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")
            self.assertIn("work-1", " ".join(error["next"]))


class ShowRealGitFixtureTest(unittest.TestCase):
    """Reject-arc (two attempts, a genuine worktree change between them)
    and verdict-inheritance (two attempts, an UNCHANGED worktree) real-
    candidate shapes -- `execution.adapter: "scripted"` + `candidate.
    adapter: "git"` against a real temp git repo, no ACP/`acpx` needed
    (`GitDiffCandidate`'s `candidate_id` is pure content, `src/orc_werk/
    adapters/git/candidate.py`)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        _init_repo(self.repo)
        self.config_path = self.root / "cfg.json"

    def _write_config(self, *, attempts: list) -> None:
        data = {
            "candidate": {"adapter": "git", "repo_path": str(self.repo)},
            "max_attempts": 3,
            "attempts": {"work-1": attempts},
        }
        self.config_path.write_text(json.dumps(data), encoding="utf-8")

    def _dispatch(self, run_id: str) -> subprocess.CompletedProcess:
        return _run_cli(
            self.root, "dispatch", "arc demo", "--config", str(self.config_path), "--journal", "./.orc", "--run-id", run_id
        )

    def test_reject_then_accept_arc_renders_both_verdicts_and_findings(self) -> None:
        run_id = "show-reject-arc"
        # 1) Attempt 1 starts+settles execution and observes a real
        # candidate synchronously (no `assurance` scripted yet -- nothing
        # to bind against, since `build_real_assurance_script` reads
        # history as it stood at THIS call's start, before this call's own
        # candidate observation). Assurance is requested but rests unbound.
        self._write_config(attempts=[{"outcome": "completed"}])
        d1 = self._dispatch(run_id)
        self.assertEqual(d1.returncode, 3, msg=d1.stdout + d1.stderr)
        self.assertIn("awaiting=assurance-verdict", d1.stdout)

        # 2) Same attempt-1 script entry, now WITH a verdict + findings: a
        # later, different (verification-agent) dispatch call now sees
        # attempt 1's real fingerprint already in history and binds it --
        # settles rejected, retries to attempt 2, starts its execution.
        self._write_config(
            attempts=[
                {
                    "outcome": "completed",
                    "assurance": {
                        "verdict": "rejected",
                        "extensions": {
                            "review-findings/v1": {
                                "findings": [{"id": "must-fix-1", "severity": "high", "summary": "broken thing"}]
                            }
                        },
                    },
                }
            ]
        )
        d2 = self._dispatch(run_id)
        self.assertEqual(d2.returncode, 3, msg=d2.stdout + d2.stderr)
        self.assertIn("attempts=2", d2.stdout)

        # A REAL worktree change before attempt 2's candidate is observed --
        # attempt 2 must produce a genuinely different fingerprint (a fresh
        # assurance, never inheritance).
        (self.repo / "a.txt").write_text("changed")
        _git(["commit", "-aqm", "fix"], cwd=self.repo)

        self._write_config(
            attempts=[
                {"outcome": "completed", "assurance": {"verdict": "rejected"}},
                {"outcome": "completed"},
            ]
        )
        d3 = self._dispatch(run_id)
        self.assertEqual(d3.returncode, 3, msg=d3.stdout + d3.stderr)
        self.assertIn("awaiting=assurance-verdict", d3.stdout)

        self._write_config(
            attempts=[
                {"outcome": "completed", "assurance": {"verdict": "rejected"}},
                {"outcome": "completed", "assurance": {"verdict": "accepted"}},
            ]
        )
        d4 = self._dispatch(run_id)
        self.assertEqual(d4.returncode, 0, msg=d4.stdout + d4.stderr)
        self.assertIn("state=ACCEPTED", d4.stdout)

        result = _run_cli(self.root, "show", run_id, "--journal", "./.orc")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        out = result.stdout
        self.assertIn("attempt 1:", out)
        self.assertIn("attempt 2:", out)
        self.assertIn("verdict=rejected", out)
        self.assertIn("verdict=accepted", out)
        self.assertIn("[high] must-fix-1: broken thing", out)
        self.assertNotIn("inherited", out)  # a genuinely fresh second verdict, not inheritance
        self.assertIn("now at ACCEPTED", out)
        self.assertNotIn("\x1b", out)

    def test_unchanged_worktree_inherits_verdict_on_reobservation(self) -> None:
        run_id = "show-inherit"
        # 1) Attempt 1 settles + observes a candidate, unbound assurance.
        self._write_config(attempts=[{"outcome": "completed"}])
        d1 = self._dispatch(run_id)
        self.assertEqual(d1.returncode, 3, msg=d1.stdout + d1.stderr)

        # 2) Bind attempt 1's real fingerprint to a rejected verdict with
        # findings -- settles rejected, retries to attempt 2's execution.
        self._write_config(
            attempts=[
                {
                    "outcome": "completed",
                    "assurance": {
                        "verdict": "rejected",
                        "extensions": {
                            "review-findings/v1": {"findings": [{"id": "noop-1", "severity": "high", "summary": "no change made"}]}
                        },
                    },
                }
            ]
        )
        d2 = self._dispatch(run_id)
        self.assertEqual(d2.returncode, 3, msg=d2.stdout + d2.stderr)
        self.assertIn("attempts=2", d2.stdout)

        # NO git change this time -- attempt 2 re-observes the IDENTICAL
        # candidate. Its own script entry carries no `assurance` at all
        # (mirrors the real `trivia-sweep` specimen's config): mechanical
        # verdict inheritance resolves it before any fresh assurance is
        # ever requested, so there is nothing to bind. Inheritance resolves
        # to READY (budget permitting) entirely in-process, so the SAME
        # dispatch call immediately continues on to start attempt 3's
        # execution too (no script entry for it yet) -- resting there,
        # pending, is this call's genuine stopping point (unlike the real
        # ACP-driven `trivia-sweep` specimen, where a live agent turn is
        # never instantaneous, so it rests at the just-inherited READY
        # state instead until a human re-dispatches). Either way, `orc
        # show` must render attempt 2 as inherited.
        self._write_config(
            attempts=[
                {"outcome": "completed", "assurance": {"verdict": "rejected"}},
                {"outcome": "completed"},
            ]
        )
        d3 = self._dispatch(run_id)
        self.assertEqual(d3.returncode, 3, msg=d3.stdout + d3.stderr)
        self.assertIn("attempts=3", d3.stdout)
        self.assertIn("awaiting=execution-outcome", d3.stdout)

        result = _run_cli(self.root, "show", run_id, "--journal", "./.orc")
        self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
        out = result.stdout
        self.assertIn("attempt 3:", out)
        self.assertIn("verdict inherited from attempt 1's settlement", out)
        self.assertIn("STATE-DELIVERY item 8", out)
        self.assertIn("[high] noop-1: no change made", out)  # inherited findings still shown
        self.assertIn("now at EXECUTING (attempts=3)", out)
        self.assertNotIn("\x1b", out)


class ShowAcpBriefsCliTest(unittest.TestCase):
    """Full dispatch cycle through the REAL `AcpExecution` port (stubbed
    `acpx`, no live Pi -- `AcpxStubWorld`, matching `test_cli_acp_wiring.
    py`'s pattern): a two-work run where one work has a `briefs` entry and
    the other falls back to the run's intent text, proving `orc show`'s
    ASKED lines render the real, persisted-config-derived provenance."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo_a = self.root / "repo-a"
        self.repo_b = self.root / "repo-b"
        _init_repo(self.repo_a)
        _init_repo(self.repo_b)
        self.world = AcpxStubWorld(self.root / "acpx_world")
        self.journal_dir = self.root / ".orc"
        self.run_id = "show-acp-briefs"
        self.config_path = self.root / "cfg.json"

    def _env(self) -> dict:
        import os

        env = dict(self.world.env())
        env["PYTHONPATH"] = str(SRC)
        env["PATH"] = f"{self.world.bin_dir}{os.pathsep}/usr/bin:/bin"
        return env

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", *args],
            cwd=self.root,
            env=self._env(),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_briefs_and_intent_fallback_provenance_render_per_work(self) -> None:
        # This scenario asserts the ASKED derivation reads the persisted
        # config honestly -- it does not need the ACP session to ever
        # settle, so no session is seeded (both works simply stay pending
        # at EXECUTING, which is itself a legitimate ASKED-rendering case:
        # provenance is knowable and shown even before EXECUTED/PRODUCED/
        # JUDGED have anything to say).
        # Both works dispatch a real (stubbed) acpx session in the same
        # call (neither declares a dep) -- each needs a seeded script or
        # the stub's own materializing pre-check crashes; "running" forever
        # is enough, since this scenario only asserts ASKED, never a
        # settlement.
        for work_id in ("work-a", "work-b"):
            key = idempotency_key(FX_START_EXECUTION, delivery_run_id=self.run_id, work_id=work_id, attempt_number=1)
            self.world.seed_script(session_name_for_idempotency_key(key), [{"states": ["running"], "outcome": "completed"}])

        long_brief = "In this git worktree, do a very specific and detailed thing: " + ("x" * 250)
        config = {
            "execution": {"adapter": "acp", "cwd": str(self.repo_a)},
            "candidate": {"adapter": "git", "repo_path": str(self.repo_a)},
            "briefs": {"work-a": long_brief},
            "plan": {"works": [{"work_id": "work-a", "deps": []}, {"work_id": "work-b", "deps": []}]},
        }
        self.config_path.write_text(json.dumps(config), encoding="utf-8")

        long_intent = "the run's own fallback intent text, made deliberately long so its own " + ("y" * 250)
        dispatch = self._run(
            "dispatch", long_intent,
            "--config", str(self.config_path), "--journal", str(self.journal_dir), "--run-id", self.run_id,
        )
        self.assertEqual(dispatch.returncode, 3, msg=dispatch.stdout + dispatch.stderr)

        result = self._run("show", self.run_id, "--journal", str(self.journal_dir))
        self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
        out = result.stdout

        self.assertIn("prompt = briefs.work-a (persisted config)", out)
        self.assertIn("truncated, showing 200 of", out)
        self.assertIn(f"full text: {(self.journal_dir / self.run_id / 'config.json').resolve()} (key: briefs.work-a)", out)

        self.assertIn("prompt = run intent (fallback)", out)
        self.assertIn("the run's own fallback intent text", out)
        self.assertIn(f"full text: orc status {self.run_id}", out)
        self.assertNotIn("\x1b", out)


if __name__ == "__main__":
    unittest.main()
