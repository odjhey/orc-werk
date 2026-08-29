"""CLI coverage for the `--abandon-work`/`--abandon-reason`/`--abandon-by`
operator surface (`TASK-M3B-001`, issues #76/#95; `docs/playbooks/
cli-usage.md`), subprocess pattern matching `test_cli_ux_round2.py`.

The unsettleable-assurance shape (`SCN-010`'s second half) is exercised
end-to-end through the real CLI/scripted-config path below. The
candidate-observation-conflict shape's `next:` affordance is exercised
directly against `orc_werk.cli.affordances.render_next_block` (unit-level,
mirroring `AffordanceTest` in `test_cli_ux_round2.py`) -- reproducing a
genuine candidate_id collision through the scripted config's
execution-id-keyed `ScriptedCandidate` is not possible (see
`tests/core/test_verdict_inheritance_and_abandon.py` and
`test_scn_009_scn_010_real_specimens.py` for that shape's full coverage
at the reducer/orchestrator layer)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.cli.affordances import render_next_block
from orc_werk.core.decisions import DEC_ABANDON_ATTEMPT
from orc_werk.core.facts import FACT_ATTEMPT_ABANDONED
from orc_werk.core.state import STATE_EXECUTING, WorkProjection, replace_projection

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


class AbandonUnsettleableAssuranceCliTest(unittest.TestCase):
    def test_abandon_from_pending_assurance_journals_decision_and_fact_then_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "cfg.json"
            config = {
                "run_id": "abandon-cli",
                "max_attempts": 3,
                "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "A"}}]},
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")

            # Get the Work to ASSURING, pending (no verdict recorded).
            dispatch1 = _run_cli(tmp_dir, "dispatch", "abandon me", "--config", str(config_path))
            self.assertEqual(dispatch1.returncode, 3, msg=dispatch1.stdout + dispatch1.stderr)
            self.assertIn("state=ASSURING", dispatch1.stdout)
            self.assertIn("awaiting=assurance-verdict", dispatch1.stdout)

            # Operator abandons it -- out-of-band knowledge it will never settle.
            dispatch2 = _run_cli(
                tmp_dir,
                "dispatch",
                "--run-id",
                "abandon-cli",
                "--abandon-work",
                "work-1",
                "--abandon-reason",
                "adapter session orphaned",
                "--abandon-by",
                "test-operator",
            )
            # Attempt 1 of 3 abandoned -- budget remains: back to EXECUTING
            # pending for attempt 2 (a fresh dispatch was journaled in the
            # same invocation), so this still exits pending (3), not an error.
            self.assertEqual(dispatch2.returncode, 3, msg=dispatch2.stdout + dispatch2.stderr)

            journal = JSONLJournal(tmp_dir / ".orc")
            history = journal.history(delivery_run_id="abandon-cli")
            decisions = [r for r in history if r["kind"] == "decision" and r["id"] == DEC_ABANDON_ATTEMPT]
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["data"]["attribution"]["operator"], "test-operator")
            self.assertEqual(decisions[0]["data"]["reason"], "adapter session orphaned")
            facts = [r for r in history if r["kind"] == "fact" and r["id"] == FACT_ATTEMPT_ABANDONED]
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0]["data"]["reason"], "adapter session orphaned")
            # No verdict was ever fabricated for attempt 1's candidate (INV-003).
            settled = [r for r in history if r["kind"] == "fact" and r["id"] == "FACT-ASSURE-SETTLED"]
            self.assertEqual(settled, [])

            # Attempt 2 proceeds honestly to acceptance once recorded.
            config["attempts"]["work-1"].append(
                {"outcome": "completed", "candidate": {"label": "B"}, "assurance": {"verdict": "accepted"}}
            )
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch3 = _run_cli(tmp_dir, "dispatch", "--run-id", "abandon-cli", "--config", str(config_path))
            self.assertEqual(dispatch3.returncode, 0, msg=dispatch3.stdout + dispatch3.stderr)
            self.assertIn("state=ACCEPTED", dispatch3.stdout)


class AbandonIllegalCliTest(unittest.TestCase):
    def test_missing_abandon_reason_is_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps({"run_id": "abandon-noreason"}), encoding="utf-8")
            _run_cli(tmp_dir, "dispatch", "x", "--config", str(config_path))
            result = _run_cli(
                tmp_dir, "dispatch", "--run-id", "abandon-noreason", "--abandon-work", "work-1"
            )
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            payload = json.loads(result.stderr)
            self.assertEqual(payload["error"], "ERR-VALIDATION")
            self.assertIn("--abandon-reason", payload["message"])
            self.assertIn("next", payload)

    def test_abandon_illegal_when_work_not_conflicted_or_unsettleable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "cfg.json"
            # Fully scripted, resolves cleanly to ACCEPTED on first dispatch.
            config = {
                "run_id": "abandon-illegal",
                "attempts": {
                    "work-1": [{"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "accepted"}}]
                },
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")
            dispatch1 = _run_cli(tmp_dir, "dispatch", "x", "--config", str(config_path))
            self.assertEqual(dispatch1.returncode, 0, msg=dispatch1.stdout + dispatch1.stderr)

            result = _run_cli(
                tmp_dir,
                "dispatch",
                "--run-id",
                "abandon-illegal",
                "--abandon-work",
                "work-1",
                "--abandon-reason",
                "nope",
            )
            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            payload = json.loads(result.stderr)
            self.assertEqual(payload["error"], "ERR-VALIDATION")
            self.assertIn("FACT-ATTEMPT-ABANDONED illegal", payload["message"])


class CandidateConflictAffordanceTest(unittest.TestCase):
    """`render_next_block` surfaces the operator-only abandon affordance
    for a Work resting at a candidate-observation conflict."""

    def test_candidate_conflict_next_block_names_operator_only_abandon(self) -> None:
        drid = "affordance-conflict"
        wp = WorkProjection(work_id="work-1", delivery_run_id=drid, state=STATE_EXECUTING)
        wp = replace_projection(
            wp,
            candidate_conflict={
                "candidate_id": "c1",
                "fact": {"id": "FACT-CANDIDATE-OBSERVED", "data": {"work_id": "work-1"}},
                "reason": "no-inheritable-verdict",
            },
        )

        class _Proj:
            works = {"work-1": wp}

        lines = render_next_block(
            _Proj(),
            history=(),
            run_id=drid,
            journal_dir=Path("/tmp/.orc"),
            config_path=None,
            intent_text=None,
        )
        text = "\n".join(lines)
        self.assertIn("candidate-observation conflict", text)
        self.assertIn("operator-only", text)
        self.assertIn(f"--abandon-work work-1", text)
        self.assertIn("--abandon-reason", text)


if __name__ == "__main__":
    unittest.main()
