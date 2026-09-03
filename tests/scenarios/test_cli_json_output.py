"""`orc status --json` / bare `orc --json` (issue #53, `docs/delivery/
M4-cockpit-and-clarity.md`'s dormant registry entry, pulled per the
follow-on #65 lane trigger): the versioned `orc-status/v1`/`orc-index/v1`
machine projections `orc_werk.cli.jsonview` builds.

Subprocess-driven for real end-to-end coverage (matching `test_cli_ux_
batch.py`/`test_cli_refs.py`'s pattern), covering the ship brief's
design rulings:

- R1 versioned shape: `schema` field on every document.
- R2 content: per-work fields on `orc-status/v1`; `refs` matching `orc
  refs`'s own row builder (`collect_refs`) field for field; `next`
  structured entries mirroring the text `next:` bullets; `orc-index/v1`
  ordering identical to the text index (the `TASK-M4B-001` unified-
  ordering invariant, now proven across text AND json).
- R3 byte-discipline: exactly one JSON document on stdout, unchanged exit
  codes, canonical error JSON on stderr with EMPTY stdout on error.
- R4 determinism: byte-stable across repeated invocations of an unchanged
  journal.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.cli.refs import collect_refs

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


ACCEPTED_CONFIG = {
    "run_id": "j53-accepted",
    "attempts": {
        "work-1": [
            {
                "outcome": "completed",
                "candidate": {"label": "hello", "head_sha": "abc123def", "repo_path": "/tmp/j53-fixture-repo"},
                "assurance": {"verdict": "accepted"},
            }
        ]
    },
}

PENDING_CONFIG = {"run_id": "j53-pending"}

BLOCKED_CONFIG = {
    "run_id": "j53-blocked",
    "max_attempts": 1,
    "attempts": {"work-1": [{"outcome": "failed"}]},
}


def _write_config(tmp_dir: Path, name: str, config: dict) -> Path:
    path = tmp_dir / name
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _dispatch_fixtures(tmp_dir: Path) -> None:
    accepted_cfg = _write_config(tmp_dir, "accepted-cfg.json", ACCEPTED_CONFIG)
    pending_cfg = _write_config(tmp_dir, "pending-cfg.json", PENDING_CONFIG)
    blocked_cfg = _write_config(tmp_dir, "blocked-cfg.json", BLOCKED_CONFIG)

    accepted = _run_cli(tmp_dir, "dispatch", "ship the widget", "--config", str(accepted_cfg))
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    pending = _run_cli(tmp_dir, "dispatch", "pending demo", "--config", str(pending_cfg))
    assert pending.returncode == 3, pending.stdout + pending.stderr
    blocked = _run_cli(tmp_dir, "dispatch", "blocked demo", "--config", str(blocked_cfg))
    assert blocked.returncode == 1, blocked.stdout + blocked.stderr


class StatusJsonShapeTest(unittest.TestCase):
    """R1/R2: `orc status --json` on each of the three run shapes the
    brief names -- pending, ACCEPTED, BLOCKED."""

    def test_accepted_run_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_fixtures(tmp_dir)

            result = _run_cli(tmp_dir, "status", "j53-accepted", "--json")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            doc = json.loads(result.stdout)

            self.assertEqual(doc["schema"], "orc-status/v1")
            self.assertEqual(doc["run_id"], "j53-accepted")
            self.assertEqual(doc["intent"], "ship the widget")
            self.assertEqual(
                doc["works"],
                [
                    {
                        "work_id": "work-1",
                        "state": "ACCEPTED",
                        "attempts": 1,
                        "attempt": None,
                        "pending": False,
                        "awaiting": None,
                        "candidate_fingerprint": doc["works"][0]["candidate_fingerprint"],
                        "blocked_reason": None,
                    }
                ],
            )
            self.assertIsNotNone(doc["works"][0]["candidate_fingerprint"])

            # next: mirrors the text next: block -- every structured
            # description (and, when present, command) appears verbatim in
            # the text rendering of the exact same run.
            text = _run_cli(tmp_dir, "status", "j53-accepted")
            self.assertEqual(text.returncode, 0)
            self.assertTrue(doc["next"], "an ACCEPTED run must carry an affordance")
            for entry in doc["next"]:
                self.assertIn(entry["description"], text.stdout)
                if entry["command"] is not None:
                    self.assertIn(entry["command"], text.stdout)
            self.assertEqual(doc["next"][0]["command"], "orc report j53-accepted")

            # refs: exactly what `orc refs` enumerates, field for field
            # (collect_refs is the single row-builder both surfaces share).
            journal = JSONLJournal(tmp_dir / ".orc")
            history = journal.history(delivery_run_id="j53-accepted")
            expected_refs = collect_refs(tmp_dir / ".orc", "j53-accepted", history)
            self.assertEqual(len(doc["refs"]), len(expected_refs))
            for actual, row in zip(doc["refs"], expected_refs):
                self.assertEqual(actual["kind"], row.kind)
                self.assertEqual(actual["provider"], row.provider)
                self.assertEqual(actual["value"], row.value)
                self.assertEqual(actual["resolve_command"], row.resolve.display)
                self.assertEqual(actual["verdict"], row.verdict)
            self.assertTrue(any(row["kind"] == "candidate" for row in doc["refs"]))

    def test_pending_run_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_fixtures(tmp_dir)

            result = _run_cli(tmp_dir, "status", "j53-pending", "--json")
            # R3: exit code identical to the text surface's own pending
            # exit code (3), not silently normalized to 0.
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            doc = json.loads(result.stdout)

            self.assertEqual(doc["schema"], "orc-status/v1")
            work = doc["works"][0]
            self.assertEqual(work["state"], "EXECUTING")
            self.assertTrue(work["pending"])
            self.assertEqual(work["awaiting"], "execution-outcome")
            self.assertEqual(work["attempt"], 1)
            self.assertEqual(work["attempts"], 1)
            self.assertIsNone(work["candidate_fingerprint"])

            descriptions = [entry["description"] for entry in doc["next"]]
            self.assertIn("record the execution outcome for work(s): work-1", descriptions)
            self.assertTrue(any(entry["command"] is not None for entry in doc["next"]))

    def test_blocked_run_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_fixtures(tmp_dir)

            result = _run_cli(tmp_dir, "status", "j53-blocked", "--json")
            self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
            doc = json.loads(result.stdout)

            work = doc["works"][0]
            self.assertEqual(work["state"], "BLOCKED")
            self.assertEqual(work["blocked_reason"], "retry-budget-exhausted")
            self.assertFalse(work["pending"])
            self.assertIsNone(work["awaiting"])

            self.assertEqual(len(doc["next"]), 1)
            self.assertEqual(doc["next"][0]["command"], "orc history j53-blocked")
            self.assertIn("BLOCKED", doc["next"][0]["description"])


class StatusJsonByteDisciplineTest(unittest.TestCase):
    """R3: stdout is exactly one JSON document; on error it is empty and
    the canonical error still lands on stderr, unchanged."""

    def test_stdout_is_single_json_line_no_prose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_fixtures(tmp_dir)
            result = _run_cli(tmp_dir, "status", "j53-accepted", "--json")
            lines = result.stdout.splitlines()
            self.assertEqual(len(lines), 1, msg=repr(result.stdout))
            json.loads(lines[0])  # must parse as exactly one document

    def test_unknown_run_json_stdout_empty_error_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            json_result = _run_cli(tmp_dir, "status", "nope-run", "--json")
            self.assertEqual(json_result.returncode, 2)
            self.assertEqual(json_result.stdout, "")
            error = json.loads(json_result.stderr)
            self.assertEqual(error["error"], "ERR-NOT-FOUND")

            # Same canonical error the ordinary (non-json) invocation
            # raises -- --json changes byte-discipline, never the error
            # semantics.
            text_result = _run_cli(tmp_dir, "status", "nope-run")
            self.assertEqual(text_result.returncode, 2)
            text_error = json.loads(text_result.stderr)
            self.assertEqual(text_error["error"], error["error"])
            self.assertEqual(text_error["message"], error["message"])

    def test_byte_stable_across_repeated_invocations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_fixtures(tmp_dir)
            first = _run_cli(tmp_dir, "status", "j53-accepted", "--json")
            second = _run_cli(tmp_dir, "status", "j53-accepted", "--json")
            self.assertEqual(first.stdout, second.stdout)
            self.assertNotEqual(first.stdout, "")


class IndexJsonShapeTest(unittest.TestCase):
    """R2 index/v1 + the `TASK-M4B-001` unified-ordering invariant, now
    proven to hold across text AND json (both built from the exact same
    ordered `window_entries` sequence in `cmd_index`)."""

    def test_index_json_shape_and_ordering_matches_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_fixtures(tmp_dir)

            text = _run_cli(tmp_dir, "--limit", "0")
            self.assertEqual(text.returncode, 0, msg=text.stdout + text.stderr)
            json_result = _run_cli(tmp_dir, "--limit", "0", "--json")
            self.assertEqual(json_result.returncode, 0, msg=json_result.stdout + json_result.stderr)

            lines = json_result.stdout.splitlines()
            self.assertEqual(len(lines), 1, msg=repr(json_result.stdout))
            doc = json.loads(lines[0])
            self.assertEqual(doc["schema"], "orc-index/v1")
            self.assertEqual(doc["total"], 3)
            self.assertFalse(doc["truncated"])
            self.assertIsNone(doc["next_page_command"])

            json_order = [entry["run_id"] for entry in doc["runs"]]
            self.assertEqual(set(json_order), {"j53-accepted", "j53-pending", "j53-blocked"})

            # Text order: one "<run_id>: states=..." line per run, in the
            # order the text index prints them.
            text_order = [
                line.split(":", 1)[0]
                for line in text.stdout.splitlines()
                if ": states=" in line
            ]
            self.assertEqual(text_order, json_order)

            by_id = {entry["run_id"]: entry for entry in doc["runs"]}
            self.assertEqual(by_id["j53-accepted"]["states"], {"ACCEPTED": 1})
            self.assertEqual(by_id["j53-accepted"]["flags"], [])
            self.assertEqual(by_id["j53-pending"]["flags"], ["pending"])
            self.assertEqual(by_id["j53-blocked"]["flags"], ["blocked"])
            self.assertEqual(
                by_id["j53-pending"]["works"][0],
                {
                    "work_id": "work-1",
                    "state": "EXECUTING",
                    "attempts": 1,
                    "pending": True,
                    "awaiting": "execution-outcome",
                    "blocked_reason": None,
                },
            )

    def test_index_json_truncation_pagination_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_fixtures(tmp_dir)

            result = _run_cli(tmp_dir, "--limit", "1", "--json")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            doc = json.loads(result.stdout)
            self.assertTrue(doc["truncated"])
            self.assertEqual(doc["total"], 3)
            self.assertEqual(len(doc["runs"]), 1)
            self.assertIsNotNone(doc["next_page_command"])
            self.assertTrue(doc["next_page_command"].startswith("orc --limit 1 --before "))

    def test_empty_journal_dir_index_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            result = _run_cli(tmp_dir, "--json")
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            doc = json.loads(result.stdout)
            self.assertEqual(doc["schema"], "orc-index/v1")
            self.assertEqual(doc["total"], 0)
            self.assertEqual(doc["runs"], [])
            self.assertFalse(doc["truncated"])

    def test_byte_stable_across_repeated_invocations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _dispatch_fixtures(tmp_dir)
            first = _run_cli(tmp_dir, "--limit", "0", "--json")
            second = _run_cli(tmp_dir, "--limit", "0", "--json")
            self.assertEqual(first.stdout, second.stdout)


if __name__ == "__main__":
    unittest.main()
