"""`orc show <run> [work]` (`TASK-M3C-001`): tests for `orc_werk.cli.show`.

Mirrors `test_cli_refs.py`'s mixed shape -- unit-level coverage of the pure
derivation helpers (prompt provenance, attempt segmentation, duration,
findings summarization) plus subprocess-driven CLI wiring/regression
coverage matching `test_cli_report.py`'s pattern. Fixtures are built fresh
inside temp directories -- never by reading this repo's live `.orc/`
journals -- so these tests never depend on that live delivery-ledger
content changing shape over time. Real reject-arc and verdict-inheritance
shapes are driven through `execution.adapter: "scripted"` + `candidate.
adapter: "git"` (`orc_werk.cli.config`'s documented "lesser combination
useful for testing the git-candidate wiring without a live agent") against
a real temporary git repository, since `GitDiffCandidate`'s `candidate_id`
is a pure function of worktree content (never of execution/attempt
identity, `src/orc_werk/adapters/git/candidate.py`), exactly what makes an
unchanged worktree re-observe the same candidate across attempts.

0.5.0/`ADR-0005` removed the `acp` `ExecutionPort` adapter, so
`prompt_provenance` now always renders the generic "no-prompt" kind; one
unit test below covers that a historical run's persisted config naming
`execution.adapter == "acp"` still renders gracefully through that same
generic path (never a dedicated acp-aware renderer, never a crash).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.cli.show import (
    _duration_text,
    _finding_id,
    _finding_severity,
    _finding_summary,
    _render_findings,
    _segment_attempts,
    prompt_provenance,
)

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

    def test_explicit_adapter_is_no_prompt(self) -> None:
        config = {"execution": {"adapter": "scripted"}}
        self.assertEqual(prompt_provenance(config, "work-1", "intent")["kind"], "no-prompt")

    def test_historical_acp_adapter_config_renders_no_prompt_gracefully(self) -> None:
        # 0.5.0/ADR-0005 removed the `acp` ExecutionPort adapter. A run
        # dispatched before 0.5.0 may still have a persisted config naming
        # `execution.adapter == "acp"` (and a now-meaningless `briefs`
        # entry) -- this must render through the same generic "no-prompt"
        # path as any other adapter string, never crash, never revive a
        # dedicated acp-aware rendering.
        config = {"execution": {"adapter": "acp"}, "briefs": {"work-1": "the brief text"}}
        self.assertEqual(
            prompt_provenance(config, "work-1", "the intent text"),
            {"kind": "no-prompt", "adapter": "acp"},
        )


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


class RenderFindingsStringEntriesUnitTest(unittest.TestCase):
    """Issue #256: `review-findings/v1`'s amended schema (issue #249) admits
    a plain string as a COMPLETE finding in its own right
    (`EXT-REVIEW-FINDINGS-V1-SEMANTICS`'s "for display, show the raw
    string" fallback) -- `_render_findings` must render it, not silently
    skip it the way it did before this fix (the pre-fix behavior only
    handled `Mapping` entries)."""

    def test_string_only_list_renders_every_entry(self) -> None:
        lines = _render_findings(["looks good", "nit: rename this variable"], run_id="r1")
        self.assertEqual(lines[0], "    findings: 2")
        self.assertIn("      [-] finding-1: looks good", lines)
        self.assertIn("      [-] finding-2: nit: rename this variable", lines)

    def test_object_only_list_unchanged(self) -> None:
        findings = [{"id": "f1", "severity": "high", "summary": "a real bug"}]
        lines = _render_findings(findings, run_id="r1")
        self.assertIn("      [high] f1: a real bug", lines)

    def test_mixed_list_renders_both_forms_in_order(self) -> None:
        findings = [
            "looks good overall",
            {"id": "finding-9", "severity": "medium", "summary": "naming is inconsistent"},
        ]
        lines = _render_findings(findings, run_id="r1")
        self.assertEqual(lines[0], "    findings: 2")
        self.assertEqual(lines[1], "      [-] finding-1: looks good overall")
        self.assertEqual(lines[2], "      [medium] finding-9: naming is inconsistent")

    def test_empty_list_renders_zero_count_only(self) -> None:
        self.assertEqual(_render_findings([], run_id="r1"), ["    findings: 0"])


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


class ShowMixedFindingsAndLandingCliTest(unittest.TestCase):
    """Issue #256's string-finding rider plus issue #65's landing row,
    exercised together through `orc show` end-to-end: a mixed `findings`
    array (string + structured, the shape issue #249's amendment actually
    produces on the live ledger) and a `gh-pr:N` evidence ref (the landing
    convention) on the SAME attempt."""

    def _dispatch(self, tmp_dir: Path) -> str:
        config = {
            "attempts": {
                "work-1": [
                    {
                        "outcome": "completed",
                        "candidate": {"label": "c1"},
                        "assurance": {
                            "verdict": "accepted",
                            "evidence_refs": ["gh-pr:65"],
                            "extensions": {
                                "review-findings/v1": {
                                    "findings": [
                                        "looks good overall",
                                        {"id": "finding-9", "severity": "medium", "summary": "naming nit"},
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
        dispatch = _run_cli(
            tmp_dir, "dispatch", "mixed findings and landing demo", "--config", str(config_path),
            "--run-id", "show-mixed",
        )
        self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)
        return "show-mixed"

    def test_string_and_structured_findings_and_landing_row_all_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            run_id = self._dispatch(tmp_dir)

            result = _run_cli(tmp_dir, "show", run_id)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            out = result.stdout

            self.assertIn("findings: 2", out)
            self.assertIn("[-] finding-1: looks good overall", out)
            self.assertIn("[medium] finding-9: naming nit", out)
            self.assertIn("landing", out)
            self.assertIn("gh pr view 65 --json state,mergedAt,mergeCommit", out)


class ShowRealGitFixtureTest(unittest.TestCase):
    """Reject-arc (two attempts, a genuine worktree change between them)
    and verdict-inheritance (two attempts, an UNCHANGED worktree) real-
    candidate shapes -- `execution.adapter: "scripted"` + `candidate.
    adapter: "git"` against a real temp git repo (`GitDiffCandidate`'s
    `candidate_id` is pure content, `src/orc_werk/adapters/git/
    candidate.py`)."""

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


if __name__ == "__main__":
    unittest.main()
