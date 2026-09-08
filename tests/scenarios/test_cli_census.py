"""`orc census` (`TASK-FIX-285`, issue #285): executable coverage for
`SCN-022`/`CONF-CLI-CENSUS-001` through `-006`.

Subprocess-driven, matching `test_cli_json_output.py`'s replacement-env
convention (never `dict(os.environ)`, never a globally exported
`ORC_JOURNAL_DIR` -- issue #303's live defect). Every fixture journal
lives in a fresh `TemporaryDirectory`; legacy-layout and undated/corrupt
shapes are built the same way `test_cli_housekeeping_55.py`/
`test_cli_show.py` already do (transplant real dispatched bytes, then
hand-edit the times sidecar for exact controlled instants -- never
hand-authoring journal envelope bytes from scratch).
"""

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


def _accepted_config(**overrides) -> dict:
    config = {
        "attempts": {
            "work-1": [{"outcome": "completed", "candidate": {"label": "x"}, "assurance": {"verdict": "accepted"}}]
        }
    }
    config.update(overrides)
    return config


def _settled_seq(journal_path: Path) -> int:
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("kind") == "fact" and record.get("id") == "FACT-ASSURE-SETTLED":
            return record["seq"]
    raise AssertionError(f"no FACT-ASSURE-SETTLED in {journal_path}")


def _set_observed_at(times_path: Path, seq: int, observed_at: str) -> None:
    records = []
    if times_path.exists():
        records = [json.loads(line) for line in times_path.read_text(encoding="utf-8").splitlines()]
    records = [r for r in records if r.get("seq") != seq]
    records.append({"seq": seq, "observed_at": observed_at})
    times_path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _delete_observed_at(times_path: Path, seq: int) -> None:
    if not times_path.exists():
        return
    records = [json.loads(line) for line in times_path.read_text(encoding="utf-8").splitlines() if json.loads(line).get("seq") != seq]
    times_path.write_text(("\n".join(json.dumps(r) for r in records) + "\n") if records else "", encoding="utf-8")


def _seed_legacy(journal_dir: Path, run_id: str) -> None:
    """Transplant an already-dispatched new-layout run's journal+times to
    the legacy flat filenames and delete the per-run directory (mirrors
    `test_cli_housekeeping_55.LegacyLayoutReadFallbackTest._seed_legacy_run`)."""
    run_directory = layout.run_dir(journal_dir, run_id)
    (journal_dir / f"{run_id}.jsonl").write_bytes((run_directory / layout.JOURNAL_FILENAME).read_bytes())
    times_file = run_directory / layout.TIMES_FILENAME
    if times_file.exists():
        (journal_dir / f"{run_id}+times.jsonl").write_bytes(times_file.read_bytes())
    shutil.rmtree(run_directory)


class MixedLayoutDatedTallyTest(unittest.TestCase):
    """`CONF-CLI-CENSUS-001`, `-003`, `-006` (`SCN-022` items 1-3)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.journal_dir = self.root / ".orc"

    def _dispatch(self, run_id: str, config: dict) -> None:
        config_path = self.root / f"{run_id}.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        result = _run_cli(
            self.root, "dispatch", f"census fixture {run_id}", "--config", str(config_path),
            "--journal", str(self.journal_dir), "--run-id", run_id,
        )
        # 0 (terminal ACCEPTED) or 3 (non-terminal: a rejected/inconclusive
        # verdict opens a retry attempt) -- either way the settlement Fact
        # is already durably journaled by the time this call returns.
        self.assertIn(result.returncode, (0, 3), msg=result.stdout + result.stderr)

    def test_legacy_layout_counted_and_as_of_cutoff_is_inclusive_and_deterministic(self) -> None:
        self._dispatch("census-a", _accepted_config())
        self._dispatch("census-b", {"attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "x"}, "assurance": {"verdict": "rejected"}}]}})
        self._dispatch("census-c", {"attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "x"}, "assurance": {"verdict": "inconclusive"}}]}})

        seq_a = _settled_seq(layout.journal_path(self.journal_dir, "census-a"))
        _set_observed_at(layout.times_path(self.journal_dir, "census-a"), seq_a, "2026-09-01T00:00:00.000000Z")
        seq_b = _settled_seq(layout.journal_path(self.journal_dir, "census-b"))
        _set_observed_at(layout.times_path(self.journal_dir, "census-b"), seq_b, "2026-09-02T00:00:00.000000Z")
        seq_c = _settled_seq(layout.journal_path(self.journal_dir, "census-c"))
        _set_observed_at(layout.times_path(self.journal_dir, "census-c"), seq_c, "2026-09-01T12:00:00.000000Z")
        _seed_legacy(self.journal_dir, "census-c")  # CONF-CLI-CENSUS-001: legacy AFTER dating

        # Item 1: legacy-layout run counted like any new-layout run.
        result = _run_cli(self.root, "census", "--as-of", "2026-09-02T00:00:00Z", "--journal", str(self.journal_dir), "--json")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["totals"], {"accepted": 1, "rejected": 1, "inconclusive": 1, "settled": 3})

        # Item 2: inclusive cutoff at T1 excludes T2 (later) and T3 (later than T1).
        cut = _run_cli(self.root, "census", "--as-of", "2026-09-01T00:00:00Z", "--journal", str(self.journal_dir), "--json")
        self.assertEqual(cut.returncode, 0, msg=cut.stdout + cut.stderr)
        cut_doc = json.loads(cut.stdout)
        self.assertEqual(cut_doc["totals"], {"accepted": 1, "rejected": 0, "inconclusive": 0, "settled": 1})

        # Item 3: byte-identical reissue against the unchanged directory.
        again = _run_cli(self.root, "census", "--as-of", "2026-09-02T00:00:00Z", "--journal", str(self.journal_dir), "--json")
        self.assertEqual(again.stdout, result.stdout)


class UndatedAndUnreadableTest(unittest.TestCase):
    """`CONF-CLI-CENSUS-003`, `-005` (`SCN-022` items 4-5)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.journal_dir = self.root / ".orc"

    def _dispatch(self, run_id: str, config: dict) -> None:
        config_path = self.root / f"{run_id}.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        result = _run_cli(
            self.root, "dispatch", f"census fixture {run_id}", "--config", str(config_path),
            "--journal", str(self.journal_dir), "--run-id", run_id,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

    def test_undated_settlement_excluded_and_disclosed(self) -> None:
        self._dispatch("census-d", _accepted_config())
        seq_d = _settled_seq(layout.journal_path(self.journal_dir, "census-d"))
        _delete_observed_at(layout.times_path(self.journal_dir, "census-d"), seq_d)

        result = _run_cli(self.root, "census", "--journal", str(self.journal_dir), "--json")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["totals"], {"accepted": 0, "rejected": 0, "inconclusive": 0, "settled": 0})
        self.assertEqual(doc["undated"], 1)
        self.assertEqual(doc["as_of"], None)
        self.assertEqual(doc["as_of_source"], "none")

    def test_unreadable_run_degrades_per_run_not_per_ledger(self) -> None:
        self._dispatch("census-good", _accepted_config())
        self._dispatch("census-e", _accepted_config())
        journal_e = layout.journal_path(self.journal_dir, "census-e")
        lines = journal_e.read_text(encoding="utf-8").splitlines()
        lines.insert(2, "{not valid json")
        journal_e.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = _run_cli(self.root, "census", "--journal", str(self.journal_dir), "--json")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["totals"]["settled"], 1)  # census-good counted fully
        self.assertEqual([r["run_id"] for r in doc["unreadable_runs"]], ["census-e"])
        self.assertEqual(doc["unreadable_runs"][0]["error"], "ERR-VALIDATION")


class InheritedVerdictTest(unittest.TestCase):
    """`CONF-CLI-CENSUS-002` (`SCN-022` items 6): a genuine
    `candidate_id` re-observation (real `git`-candidate adapter, unchanged
    worktree) inherits its prior verdict and journals no second
    `FACT-ASSURE-SETTLED` -- census must not double-count it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.journal_dir = self.root / ".orc"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "census-test@example.invalid"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Census Test"], cwd=self.repo, check=True, capture_output=True)
        (self.repo / "a.txt").write_text("x")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.repo, check=True, capture_output=True)
        self.config_path = self.root / "cfg.json"

    def _write_config(self, attempts: list) -> None:
        data = {
            "candidate": {"adapter": "git", "repo_path": str(self.repo)},
            "max_attempts": 3,
            "attempts": {"work-1": attempts},
        }
        self.config_path.write_text(json.dumps(data), encoding="utf-8")

    def _dispatch(self) -> subprocess.CompletedProcess:
        return _run_cli(
            self.root, "dispatch", "inherit demo", "--config", str(self.config_path),
            "--journal", str(self.journal_dir), "--run-id", "census-f",
        )

    def test_inherited_verdict_not_double_counted(self) -> None:
        self._write_config([{"outcome": "completed"}])
        d1 = self._dispatch()
        self.assertEqual(d1.returncode, 3, msg=d1.stdout + d1.stderr)

        self._write_config([{"outcome": "completed", "assurance": {"verdict": "rejected"}}])
        d2 = self._dispatch()
        self.assertEqual(d2.returncode, 3, msg=d2.stdout + d2.stderr)
        self.assertIn("attempts=2", d2.stdout)

        # NO worktree change: attempt 2 re-observes the identical
        # candidate_id and mechanically inherits `rejected` -- no fresh
        # assurance is requested or settled (STATE-DELIVERY item 8).
        self._write_config(
            [
                {"outcome": "completed", "assurance": {"verdict": "rejected"}},
                {"outcome": "completed"},
            ]
        )
        d3 = self._dispatch()
        self.assertEqual(d3.returncode, 3, msg=d3.stdout + d3.stderr)
        self.assertIn("attempts=3", d3.stdout)
        self.assertIn("awaiting=execution-outcome", d3.stdout)

        journal = layout.journal_path(self.journal_dir, "census-f")
        settled_count = sum(
            1 for line in journal.read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("id") == "FACT-ASSURE-SETTLED"
        )
        self.assertEqual(settled_count, 1, "inheritance must not journal a second FACT-ASSURE-SETTLED")

        result = _run_cli(self.root, "census", "--journal", str(self.journal_dir), "--json")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["totals"], {"accepted": 0, "rejected": 1, "inconclusive": 0, "settled": 1})


class RawModelGroupingTest(unittest.TestCase):
    """`CONF-CLI-CENSUS-004` (`SCN-022` item 7): exact model string,
    "no extension" vs "extension present, no model field" stay
    distinguishable, never collapsed onto a fabricated placeholder."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.journal_dir = self.root / ".orc"

    def _dispatch_pending(self, run_id: str) -> None:
        config_path = self.root / f"{run_id}.json"
        config_path.write_text(json.dumps({"attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "x"}}]}}), encoding="utf-8")
        result = _run_cli(
            self.root, "dispatch", f"model fixture {run_id}", "--config", str(config_path),
            "--journal", str(self.journal_dir), "--run-id", run_id,
        )
        self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)

    def _record_and_fold(self, run_id: str, *extra: str) -> None:
        record = _run_cli(self.root, "record", run_id, "--work", "work-1", "--verdict", "accepted", "--journal", str(self.journal_dir), *extra)
        self.assertEqual(record.returncode, 0, msg=record.stdout + record.stderr)
        config_path = layout.config_path(self.journal_dir, run_id)
        fold = _run_cli(self.root, "dispatch", "--run-id", run_id, "--config", str(config_path), "--journal", str(self.journal_dir))
        self.assertEqual(fold.returncode, 0, msg=fold.stdout + fold.stderr)

    def test_three_model_shapes_stay_distinguishable(self) -> None:
        self._dispatch_pending("census-g1")
        self._record_and_fold("census-g1", "--model", "claude-sonnet-5", "--session-ref", "sess1", "--seat-ref", "seat1")

        self._dispatch_pending("census-g2")
        self._record_and_fold("census-g2", "--session-ref", "sess2")  # payload present, no model

        config_path = self.root / "census-g3.json"
        config_path.write_text(json.dumps(_accepted_config()), encoding="utf-8")  # no extension at all
        result = _run_cli(
            self.root, "dispatch", "no-extension fixture", "--config", str(config_path),
            "--journal", str(self.journal_dir), "--run-id", "census-g3",
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

        census = _run_cli(self.root, "census", "--journal", str(self.journal_dir), "--json")
        self.assertEqual(census.returncode, 0, msg=census.stdout + census.stderr)
        doc = json.loads(census.stdout)
        rows = {(g["model"], g["identity_extension"]) for g in doc["groups"]}
        self.assertEqual(
            rows,
            {("claude-sonnet-5", True), (None, True), (None, False)},
        )
        self.assertEqual(doc["totals"]["settled"], 3)


class DefaultAsOfAndEmptyLedgerTest(unittest.TestCase):
    """`CONF-CLI-CENSUS-006` (`SCN-022` items 8-9): the omitted-`--as-of`
    default derives only from ledger data, never wall-clock `now()`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.journal_dir = self.root / ".orc"

    def test_empty_ledger_reports_null_as_of_and_zero_totals(self) -> None:
        result = _run_cli(self.root, "census", "--journal", str(self.journal_dir), "--json")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        doc = json.loads(result.stdout)
        self.assertEqual(doc["as_of"], None)
        self.assertEqual(doc["as_of_source"], "none")
        self.assertEqual(doc["totals"], {"accepted": 0, "rejected": 0, "inconclusive": 0, "settled": 0})
        self.assertEqual(doc["undated"], 0)

    def test_default_as_of_pins_to_ledger_high_water_mark_and_explicit_cutoff_is_stable(self) -> None:
        config_path = self.root / "cfg.json"
        config_path.write_text(json.dumps(_accepted_config()), encoding="utf-8")
        d1 = _run_cli(self.root, "dispatch", "default fixture", "--config", str(config_path), "--journal", str(self.journal_dir), "--run-id", "census-h1")
        self.assertEqual(d1.returncode, 0, msg=d1.stdout + d1.stderr)
        seq1 = _settled_seq(layout.journal_path(self.journal_dir, "census-h1"))
        _set_observed_at(layout.times_path(self.journal_dir, "census-h1"), seq1, "2026-09-01T00:00:00.000000Z")

        first = _run_cli(self.root, "census", "--journal", str(self.journal_dir), "--json")
        self.assertEqual(first.returncode, 0, msg=first.stdout + first.stderr)
        first_doc = json.loads(first.stdout)
        self.assertEqual(first_doc["as_of"], "2026-09-01T00:00:00.000000Z")
        self.assertEqual(first_doc["as_of_source"], "latest-settlement")
        self.assertEqual(first_doc["totals"]["settled"], 1)

        # A later, later-dated settlement is added; the explicit cutoff
        # from before is unaffected, but a bare re-run advances.
        d2 = _run_cli(self.root, "dispatch", "default fixture 2", "--config", str(config_path), "--journal", str(self.journal_dir), "--run-id", "census-h2")
        self.assertEqual(d2.returncode, 0, msg=d2.stdout + d2.stderr)
        seq2 = _settled_seq(layout.journal_path(self.journal_dir, "census-h2"))
        _set_observed_at(layout.times_path(self.journal_dir, "census-h2"), seq2, "2026-09-05T00:00:00.000000Z")

        stable = _run_cli(self.root, "census", "--as-of", "2026-09-01T00:00:00Z", "--journal", str(self.journal_dir), "--json")
        self.assertEqual(json.loads(stable.stdout)["totals"]["settled"], 1)

        advanced = _run_cli(self.root, "census", "--journal", str(self.journal_dir), "--json")
        advanced_doc = json.loads(advanced.stdout)
        self.assertEqual(advanced_doc["as_of"], "2026-09-05T00:00:00.000000Z")
        self.assertEqual(advanced_doc["totals"]["settled"], 2)


class AsOfValidationTest(unittest.TestCase):
    """Byte-discipline: an unparseable `--as-of` is `ERR-VALIDATION` on
    stderr with empty stdout, exit 2 -- never guessed toward a timezone."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_naive_offset_and_date_only_are_all_rejected(self) -> None:
        for bad in ("2026-09-07", "2026-09-07T12:00:00", "2026-09-07T12:00:00+02:00"):
            result = _run_cli(self.root, "census", "--as-of", bad, "--journal", str(self.root / ".orc"))
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            self.assertEqual(result.stdout, "")
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")

    def test_fractional_and_bare_z_are_accepted(self) -> None:
        for good in ("2026-09-07T12:00:00Z", "2026-09-07T12:00:00.123456Z"):
            result = _run_cli(self.root, "census", "--as-of", good, "--journal", str(self.root / ".orc"))
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)


class CensusRegisteredInHelpTest(unittest.TestCase):
    def test_census_is_registered_in_top_level_help(self) -> None:
        result = _run_cli(Path.cwd(), "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("census", result.stdout)


if __name__ == "__main__":
    unittest.main()
