"""Regression tests for `orc report` (`TASK-M1-008`), subprocess pattern
matching `test_cli_ux_batch.py`/`test_cli_dogfood_fixes.py`. Fixtures here
are constructed fresh through `orc dispatch`/`orc crew-report append`
inside a temp directory -- never by reading the repo's live `.orc/`
journals -- so these tests never depend on that live delivery-ledger
content changing shape over time.

Covers the task card's acceptance/regression list:

- a missing run is canonical `ERR-NOT-FOUND`, exit `2`, no side effects
  (no output file, no stray `.orc/` directory);
- rendering a reject -> retry -> accept run (mirroring the shape of the
  real `.orc/task-m1-007.jsonl` acceptance fixture, but built fresh here)
  produces output containing both candidate fingerprints, the rejected and
  accepted verdicts, `DEC-RETRY`, and HTML-escaped content (a synthetic
  `<script>`-bearing intent renders escaped, never as live markup);
- crew-report claims render in visually distinct (`class="claim"`) markup
  that never appears on a canonical state/verdict chip;
- a pending run renders the "awaiting ..." callout;
- a blocked run renders its `blocked_reason`/root cause;
- `--index` is read-only apart from its own announced output file.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl import layout

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run_cli(tmp_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=tmp_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _dir_snapshot(directory: Path) -> set[str]:
    if not directory.exists():
        return set()
    return {str(p.relative_to(directory)) for p in directory.rglob("*")}


class MissingRunTest(unittest.TestCase):
    def test_missing_run_is_err_not_found_no_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "report", "totally-nonexistent-run-id")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")
            self.assertIn("totally-nonexistent-run-id", error["message"])
            self.assertFalse((tmp_dir / ".orc").exists())
            # issue #43's ERR-NOT-FOUND(run) affordance: stdout is no longer
            # empty on this path -- a definitive "0 runs in <dir>" (no
            # journal directory exists yet, so no *other* run to suggest)
            # plus the dispatch affordance, printed before the canonical
            # error (stderr JSON, exit 2, both unchanged above) propagates.
            self.assertIn("0 runs in", result.stdout)
            self.assertIn("next:", result.stdout)
            self.assertIn("orc dispatch", result.stdout)


class RejectRetryAcceptTest(unittest.TestCase):
    """Mirrors the shape of `.orc/task-m1-007.jsonl` (the reject -> retry
    -> accept acceptance fixture) but built fresh via a scripted dispatch
    config, and adds a `<script>` payload in the intent text to prove
    escaping."""

    RUN_ID = "report-retry-accept"
    INTENT = 'render me <script>alert(1)</script> safely'

    def _build_run(self, tmp_dir: Path) -> None:
        config = {
            "run_id": self.RUN_ID,
            "attempts": {
                "work-1": [
                    {"outcome": "completed", "candidate": {"label": "C1"}, "assurance": {"verdict": "rejected"}},
                    {"outcome": "completed", "candidate": {"label": "C2"}, "assurance": {"verdict": "accepted"}},
                ]
            },
        }
        config_path = tmp_dir / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        dispatch = _run_cli(tmp_dir, "dispatch", self.INTENT, "--config", str(config_path))
        self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

    def _journal_data(self, tmp_dir: Path) -> list[dict]:
        path = layout.journal_path(tmp_dir / ".orc", self.RUN_ID)
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_report_contains_full_story_and_escapes_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_run(tmp_dir)

            report = _run_cli(tmp_dir, "report", self.RUN_ID)
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            out_path = layout.report_html_path(tmp_dir / ".orc", self.RUN_ID)
            # #40 comment: the printed `report:` line is the RESOLVED
            # ABSOLUTE path, not a relative one.
            self.assertIn(f"report: {out_path.resolve()}", report.stdout)
            self.assertTrue(Path(report.stdout.strip().split("report: ", 1)[1]).is_absolute())
            self.assertTrue(out_path.exists())
            html_text = out_path.read_text(encoding="utf-8")

            # Two distinct candidate fingerprints.
            records = self._journal_data(tmp_dir)
            fingerprints = sorted(
                {
                    r["data"]["fingerprint"]
                    for r in records
                    if r["kind"] == "fact" and r["id"] == "FACT-CANDIDATE-OBSERVED"
                }
            )
            self.assertEqual(len(fingerprints), 2)
            for fp in fingerprints:
                self.assertIn(fp, html_text)

            # Rejected and accepted verdicts, and the retry decision.
            self.assertIn('class="chip chip-critical"', html_text)
            self.assertIn(">rejected<", html_text)
            self.assertIn('class="chip chip-good"', html_text)
            self.assertIn(">accepted<", html_text)
            self.assertIn("DEC-RETRY", html_text)
            self.assertIn("cites", html_text)  # basis citation of the rejected verdict

            # HTML-escaped intent -- never live markup.
            self.assertNotIn("<script>alert(1)</script>", html_text)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_text)

            # Self-contained: no external requests, dark mode deliberately styled.
            self.assertNotIn("http://", html_text)
            self.assertNotIn("https://", html_text)
            self.assertIn("prefers-color-scheme: dark", html_text)

    def test_report_is_read_only_except_its_own_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_run(tmp_dir)
            before = _dir_snapshot(tmp_dir / ".orc")

            report = _run_cli(tmp_dir, "report", self.RUN_ID)
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)

            after = _dir_snapshot(tmp_dir / ".orc")
            created = after - before
            # issue #55 H1: this run's directory already exists (created by
            # dispatch, per _build_run above) -- the only NEW entry `orc
            # report` creates is the report.html file inside it.
            self.assertEqual(created, {f"{self.RUN_ID}/report.html"})


class ClaimsQuarantineTest(unittest.TestCase):
    """Crew-report claims must render in visually distinct markup
    (`class="claim"`), and that class must never coincide with a canonical
    state/verdict chip (`class="chip ..."`) -- the task card's claim-vs-fact
    visual quarantine."""

    RUN_ID = "report-claims-quarantine"

    def test_claim_markup_distinct_from_canonical_chips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": self.RUN_ID,
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "accepted"}}]
                },
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "claims quarantine fixture", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            journal_path = layout.journal_path(tmp_dir / ".orc", self.RUN_ID)
            records = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
            (execution_id,) = {
                r["data"]["execution_id"]
                for r in records
                if r["kind"] == "fact" and r["id"] == "FACT-EXEC-STARTED"
            }

            append = _run_cli(
                tmp_dir,
                "crew-report",
                "append",
                self.RUN_ID,
                "--execution-id",
                execution_id,
                "--payload",
                json.dumps(
                    {
                        "turn": 1,
                        "claimed_verdict": "done",
                        "reason": "looked <b>done</b> to me",
                    }
                ),
            )
            self.assertEqual(append.returncode, 0, msg=append.stdout + append.stderr)

            report = _run_cli(tmp_dir, "report", self.RUN_ID)
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", self.RUN_ID).read_text(encoding="utf-8")

            # The claim renders, labeled, and its free-text field is escaped.
            self.assertIn('<li class="claim">', html_text)
            self.assertIn("claim, not a canonical verdict", html_text)
            self.assertIn("claimed_verdict:", html_text)
            self.assertIn("&lt;b&gt;done&lt;/b&gt;", html_text)

            # No chip (canonical state/verdict/outcome marker) ever carries
            # the claim class, and the claim block never carries the chip
            # class -- the two are structurally distinct markup.
            chip_spans = re.findall(r'<span class="chip[^"]*"', html_text)
            self.assertTrue(chip_spans, "expected at least one canonical chip in the report")
            for span in chip_spans:
                self.assertNotIn("claim", span)
            claim_items = re.findall(r'<li class="[^"]*"', html_text)
            claim_only = [item for item in claim_items if "claim" in item]
            self.assertTrue(claim_only)
            for item in claim_only:
                self.assertNotIn("chip", item)


class PendingCalloutTest(unittest.TestCase):
    def test_pending_run_renders_awaiting_callout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {"run_id": "report-pending"}
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "pending fixture", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 3, msg=dispatch.stdout + dispatch.stderr)

            report = _run_cli(tmp_dir, "report", "report-pending")
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", "report-pending").read_text(encoding="utf-8")

            self.assertIn('class="callout callout-warning"', html_text)
            self.assertIn("awaiting execution-outcome, attempt 1", html_text)


class BlockedRootCauseTest(unittest.TestCase):
    def test_blocked_run_renders_blocked_reason_and_root_cause(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "report-blocked",
                "max_attempts": 3,
                "resume_capability": "CAP-EXEC-RESUME-EXACT",
                "execution_capabilities": ["CAP-EXEC-RESUME-BEST-EFFORT"],
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"label": "Z"}, "assurance": {"verdict": "accepted"}}]
                },
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "blocked fixture", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 1, msg=dispatch.stdout + dispatch.stderr)

            report = _run_cli(tmp_dir, "report", "report-blocked")
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", "report-blocked").read_text(encoding="utf-8")

            self.assertIn('class="callout callout-critical"', html_text)
            self.assertIn("blocked_reason=retry-budget-exhausted", html_text)
            self.assertIn("root_cause=ERR-UNSUPPORTED-CAPABILITY", html_text)


class IndexReadOnlyTest(unittest.TestCase):
    def test_index_lists_runs_and_writes_only_its_own_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for run_id in ("idx-run-a", "idx-run-b"):
                config = {
                    "run_id": run_id,
                    "attempts": {
                        "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]
                    },
                }
                config_path = tmp_dir / f"{run_id}.config.json"
                config_path.write_text(json.dumps(config), encoding="utf-8")
                dispatch = _run_cli(tmp_dir, "dispatch", f"intent for {run_id}", "--config", str(config_path))
                self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            before = _dir_snapshot(tmp_dir / ".orc")
            index = _run_cli(tmp_dir, "report", "--index")
            self.assertEqual(index.returncode, 0, msg=index.stdout + index.stderr)
            after = _dir_snapshot(tmp_dir / ".orc")

            self.assertEqual(after - before, {"index.html"})
            index_html = (tmp_dir / ".orc" / "index.html").read_text(encoding="utf-8")
            self.assertIn("idx-run-a", index_html)
            self.assertIn("idx-run-b", index_html)
            # issue #55 H1: plain `--index`'s hrefs are layout-aware -- a
            # new-layout run's link is relative into its own subdirectory.
            self.assertIn("idx-run-a/report.html", index_html)
            self.assertIn("idx-run-b/report.html", index_html)

    def test_index_with_positional_run_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "report", "some-run", "--index")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")

    def test_index_line_prints_resolved_absolute_path(self) -> None:
        # #40 comment sweep: the index output line is absolute too.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "idx-abs",
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]
                },
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "idx-abs fixture", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            index = _run_cli(tmp_dir, "report", "--index")
            self.assertEqual(index.returncode, 0, msg=index.stdout + index.stderr)
            expected = (tmp_dir / ".orc" / "index.html").resolve()
            self.assertIn(f"report: {expected}", index.stdout)


class TimesSidecarRenderingTest(unittest.TestCase):
    """Issue #39: `orc report` joins the observed-at time sidecar by
    `seq` into the timeline and header when present, renders cleanly
    without it when absent, and degrades gracefully (skip-with-note, not
    a crash) when a sidecar line is corrupt."""

    RUN_ID = "report-times"

    def _build_run(self, tmp_dir: Path) -> None:
        config = {
            "run_id": self.RUN_ID,
            "attempts": {
                "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]
            },
        }
        config_path = tmp_dir / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        dispatch = _run_cli(tmp_dir, "dispatch", "times sidecar fixture", "--config", str(config_path))
        self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

    def test_times_render_in_timeline_and_header_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_run(tmp_dir)
            times_path = layout.times_path(tmp_dir / ".orc", self.RUN_ID)
            self.assertTrue(times_path.exists())

            report = _run_cli(tmp_dir, "report", self.RUN_ID)
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", self.RUN_ID).read_text(encoding="utf-8")

            self.assertIn('class="record-time"', html_text)
            self.assertIn("observed: started", html_text)
            self.assertIn("last activity", html_text)

    def test_report_renders_cleanly_without_times_when_sidecar_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_run(tmp_dir)
            times_path = layout.times_path(tmp_dir / ".orc", self.RUN_ID)
            times_path.unlink()

            report = _run_cli(tmp_dir, "report", self.RUN_ID)
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", self.RUN_ID).read_text(encoding="utf-8")

            self.assertNotIn('class="record-time"', html_text)
            self.assertNotIn("observed: started", html_text)

    def test_corrupt_sidecar_line_does_not_break_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_run(tmp_dir)
            times_path = layout.times_path(tmp_dir / ".orc", self.RUN_ID)
            good_lines = times_path.read_text(encoding="utf-8").splitlines()
            # Corrupt one line, keep the rest valid.
            good_lines[0] = "not valid json at all"
            times_path.write_text("\n".join(good_lines) + "\n", encoding="utf-8")

            report = _run_cli(tmp_dir, "report", self.RUN_ID)
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            html_text = layout.report_html_path(tmp_dir / ".orc", self.RUN_ID).read_text(encoding="utf-8")

            self.assertIn("1 corrupt sidecar record(s) skipped", html_text)
            # The remaining (valid) times still render.
            self.assertIn('class="record-time"', html_text)

    def test_history_and_status_byte_identical_with_sidecar_present_vs_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_run(tmp_dir)

            history_before = _run_cli(tmp_dir, "history", self.RUN_ID)
            status_before = _run_cli(tmp_dir, "status", self.RUN_ID)

            layout.times_path(tmp_dir / ".orc", self.RUN_ID).unlink()

            history_after = _run_cli(tmp_dir, "history", self.RUN_ID)
            status_after = _run_cli(tmp_dir, "status", self.RUN_ID)

            self.assertEqual(history_before.stdout, history_after.stdout)
            self.assertEqual(status_before.stdout, status_after.stdout)


class WildcardAllRenderingTest(unittest.TestCase):
    """Issue #40: `orc report --all [--match GLOB] [--out-dir DIR]`
    renders every run whose run_id fnmatches `--match` (default `'*'`)
    to its own file plus a scoped index."""

    def _build_run(self, tmp_dir: Path, run_id: str) -> None:
        config = {
            "run_id": run_id,
            "attempts": {
                "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]
            },
        }
        config_path = tmp_dir / f"{run_id}.config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        dispatch = _run_cli(tmp_dir, "dispatch", f"intent for {run_id}", "--config", str(config_path))
        self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

    def test_match_selects_correct_subset_and_scoped_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for run_id in ("m1.task-005", "m1.task-006", "m2.task-001"):
                self._build_run(tmp_dir, run_id)

            before = _dir_snapshot(tmp_dir / ".orc")
            result = _run_cli(tmp_dir, "report", "--all", "--match", "m1.*")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            after = _dir_snapshot(tmp_dir / ".orc")

            created = after - before
            self.assertEqual(
                created, {"m1.task-005.report.html", "m1.task-006.report.html", "index.html"}
            )

            index_html = (tmp_dir / ".orc" / "index.html").read_text(encoding="utf-8")
            self.assertIn("m1.task-005", index_html)
            self.assertIn("m1.task-006", index_html)
            self.assertNotIn("m2.task-001", index_html)

            # Absolute clickable paths for every announced output.
            for line in result.stdout.splitlines():
                self.assertTrue(line.startswith("report: "))
                printed_path = Path(line[len("report: ") :])
                self.assertTrue(printed_path.is_absolute())

    def test_all_with_default_match_renders_every_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for run_id in ("run-a", "run-b"):
                self._build_run(tmp_dir, run_id)

            result = _run_cli(tmp_dir, "report", "--all")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue((tmp_dir / ".orc" / "run-a.report.html").exists())
            self.assertTrue((tmp_dir / ".orc" / "run-b.report.html").exists())

    def test_all_writes_only_announced_outputs_under_out_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_run(tmp_dir, "run-only")
            out_dir = tmp_dir / "reports-out"

            before = _dir_snapshot(tmp_dir / ".orc")
            result = _run_cli(tmp_dir, "report", "--all", "--out-dir", str(out_dir))
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            after = _dir_snapshot(tmp_dir / ".orc")

            # Journal directory itself is untouched -- outputs land only
            # under the announced --out-dir.
            self.assertEqual(after, before)
            self.assertEqual(
                _dir_snapshot(out_dir), {"run-only.report.html", "index.html"}
            )

    def test_missing_journal_directory_is_err_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "report", "--all", "--journal", str(tmp_dir / "nope"))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")

    def test_all_rejects_positional_run_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "report", "some-run", "--all")
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")


class SidecarSeparatorCollisionRegressionTest(unittest.TestCase):
    """Attempt-2 watchtower ruling on PR #46: the sidecar separator is
    `+`, outside the safe run-id charset, so a legal dot-namespaced run id
    whose last segment is `times` or `reports` (e.g. `m1.times`,
    `foo.reports` -- which under the rejected dot-suffix scheme yielded
    `m1.times.jsonl` and were misclassified as sidecars, vanishing from
    `--all`/`--index` and bare-directory resolution) is fully visible
    everywhere, alongside its own `+`-suffixed sidecars."""

    def _build_run(self, tmp_dir: Path, run_id: str) -> None:
        config = {
            "run_id": run_id,
            "attempts": {
                "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]
            },
        }
        config_path = tmp_dir / f"{run_id}.config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        dispatch = _run_cli(tmp_dir, "dispatch", f"intent for {run_id}", "--config", str(config_path))
        self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

    def test_collision_prone_run_ids_fully_visible_everywhere(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for run_id in ("m1.times", "foo.reports"):
                self._build_run(tmp_dir, run_id)
                # issue #55 H1: fresh runs use the new per-run-dir layout,
                # where this collision is structurally impossible for a
                # different reason (directory scope, not a `+` separator) --
                # both artifacts resolve inside this run's own directory.
                self.assertTrue(layout.times_path(tmp_dir / ".orc", run_id).exists())
                self.assertTrue(layout.journal_path(tmp_dir / ".orc", run_id).exists())

            # --all sees both runs.
            result = _run_cli(tmp_dir, "report", "--all")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue((tmp_dir / ".orc" / "m1.times.report.html").exists())
            self.assertTrue((tmp_dir / ".orc" / "foo.reports.report.html").exists())

            # --match selects them by namespace.
            match = _run_cli(tmp_dir, "report", "--all", "--match", "m1.*")
            self.assertEqual(match.returncode, 0, msg=match.stdout + match.stderr)
            self.assertIn("m1.times.report.html", match.stdout)
            self.assertNotIn("foo.reports.report.html", match.stdout)

            # The index lists both.
            index_html = (tmp_dir / ".orc" / "index.html").read_text(encoding="utf-8")
            self.assertIn("m1.times", index_html)

            # Direct report by run id works (no hard ERR-NOT-FOUND).
            single = _run_cli(tmp_dir, "report", "m1.times")
            self.assertEqual(single.returncode, 0, msg=single.stdout + single.stderr)

    def test_bare_directory_resolution_sees_a_collision_prone_run(self) -> None:
        # Exactly one run in the directory, named `m1.times`, with its own
        # `+`-suffixed sidecar beside it: bare-directory resolution must
        # find exactly one journal (the rejected dot-suffix scheme made
        # this run invisible -> hard ERR-NOT-FOUND).
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_run(tmp_dir, "m1.times")
            self.assertTrue(layout.times_path(tmp_dir / ".orc", "m1.times").exists())

            status = _run_cli(tmp_dir, "status", ".orc")
            self.assertEqual(status.returncode, 0, msg=status.stdout + status.stderr)
            self.assertIn("run: m1.times", status.stdout)

    def test_crew_report_round_trips_with_new_suffix_for_collision_prone_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            self._build_run(tmp_dir, "foo.reports")
            journal_path = layout.journal_path(tmp_dir / ".orc", "foo.reports")
            records = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
            (execution_id,) = {
                r["data"]["execution_id"]
                for r in records
                if r["kind"] == "fact" and r["id"] == "FACT-EXEC-STARTED"
            }
            append = _run_cli(
                tmp_dir, "crew-report", "append", "foo.reports",
                "--execution-id", execution_id,
                "--payload", json.dumps({"turn": 1, "claimed_verdict": "done"}),
            )
            self.assertEqual(append.returncode, 0, msg=append.stdout + append.stderr)
            self.assertTrue(layout.reports_path(tmp_dir / ".orc", "foo.reports").exists())

            listed = _run_cli(tmp_dir, "crew-report", "list", "foo.reports")
            self.assertEqual(listed.returncode, 0, msg=listed.stdout + listed.stderr)
            self.assertIn("claimed_verdict", listed.stdout)

            # And the run journal itself is still resolvable/reportable.
            report = _run_cli(tmp_dir, "report", "foo.reports")
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)


class AbsolutePathSweepTest(unittest.TestCase):
    """Issue #40 comment: every printed filesystem path is the RESOLVED
    ABSOLUTE path, clickable in a terminal regardless of cwd -- swept
    across `dispatch`'s `journal:` line and `report`'s `report:` line."""

    def test_dispatch_journal_line_is_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "abs-journal",
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]
                },
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "abs journal fixture", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            journal_line = next(l for l in dispatch.stdout.splitlines() if l.startswith("journal: "))
            printed_path = Path(journal_line[len("journal: ") :])
            self.assertTrue(printed_path.is_absolute())
            self.assertEqual(printed_path, layout.journal_path(tmp_dir / ".orc", "abs-journal").resolve())

    def test_report_line_is_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config = {
                "run_id": "abs-report",
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"x": 1}, "assurance": {"verdict": "accepted"}}]
                },
            }
            config_path = tmp_dir / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch = _run_cli(tmp_dir, "dispatch", "abs report fixture", "--config", str(config_path))
            self.assertEqual(dispatch.returncode, 0, msg=dispatch.stdout + dispatch.stderr)

            report = _run_cli(tmp_dir, "report", "abs-report")
            self.assertEqual(report.returncode, 0, msg=report.stdout + report.stderr)
            report_line = next(l for l in report.stdout.splitlines() if l.startswith("report: "))
            printed_path = Path(report_line[len("report: ") :])
            self.assertTrue(printed_path.is_absolute())
            self.assertEqual(printed_path, layout.report_html_path(tmp_dir / ".orc", "abs-report").resolve())


if __name__ == "__main__":
    unittest.main()
