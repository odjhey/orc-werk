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
            # Attempt 1 of 3 abandoned -- budget remains, but this journal-only
            # invocation stops at READY. The real-config dispatch below owns
            # opening attempt 2.
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
            starts = [r for r in history if r["kind"] == "effect" and r["id"] == "FX-START-EXECUTION"]
            self.assertEqual(len(starts), 1, "abandon must not mint attempt 2 through stub ports")
            self.assertIn("now READY", dispatch2.stdout)
            self.assertIn("next attempt starts on the next dispatch", dispatch2.stdout)
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
            resumed = journal.history(delivery_run_id="abandon-cli")
            starts = [r for r in resumed if r["kind"] == "effect" and r["id"] == "FX-START-EXECUTION"]
            self.assertEqual(len(starts), 2)

    def test_budget_exhausted_abandon_rests_blocked_without_next_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "cfg.json"
            config_path.write_text(json.dumps({
                "run_id": "abandon-exhausted",
                "max_attempts": 1,
                "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "A"}}]},
            }), encoding="utf-8")
            initial = _run_cli(root, "dispatch", "exhaust abandon", "--config", str(config_path))
            self.assertEqual(initial.returncode, 3, msg=initial.stdout + initial.stderr)
            abandoned = _run_cli(
                root, "dispatch", "--run-id", "abandon-exhausted",
                "--abandon-work", "work-1", "--abandon-reason", "unsettleable",
            )
            self.assertEqual(abandoned.returncode, 1, msg=abandoned.stdout + abandoned.stderr)
            self.assertIn("now BLOCKED", abandoned.stdout)
            history = JSONLJournal(root / ".orc").history(delivery_run_id="abandon-exhausted")
            starts = [r for r in history if r["kind"] == "effect" and r["id"] == "FX-START-EXECUTION"]
            self.assertEqual(len(starts), 1)

    def test_abandon_briefed_acp_run_does_not_construct_provider_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(
                json.dumps(
                    {
                        "run_id": "abandon-acp",
                        "max_attempts": 2,
                        "attempts": {"work-1": [{"outcome": "completed", "candidate": {"label": "A"}}]},
                    }
                ),
                encoding="utf-8",
            )
            initial = _run_cli(tmp_dir, "dispatch", "abandon me", "--config", str(config_path))
            self.assertEqual(initial.returncode, 3, msg=initial.stdout + initial.stderr)
            config_path.write_text(
                json.dumps(
                    {
                        "execution": {"adapter": "acp", "cwd": str(tmp_dir)},
                        "candidate": {"adapter": "git", "repo_path": str(tmp_dir)},
                        "briefs": {"work-1": "provider-only brief"},
                        "attempts": {"work-1": []},
                    }
                ),
                encoding="utf-8",
            )

            result = _run_cli(
                tmp_dir,
                "dispatch",
                "--run-id",
                "abandon-acp",
                "--config",
                str(config_path),
                "--abandon-work",
                "work-1",
                "--abandon-reason",
                "adapter session orphaned",
            )

            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            self.assertNotIn("note: work", result.stderr)
            history = JSONLJournal(tmp_dir / ".orc").history(delivery_run_id="abandon-acp")
            self.assertTrue(any(r["kind"] == "decision" and r["id"] == DEC_ABANDON_ATTEMPT for r in history))
            self.assertTrue(any(r["kind"] == "fact" and r["id"] == FACT_ATTEMPT_ABANDONED for r in history))


class AbandonIllegalCliTest(unittest.TestCase):
    def test_unknown_abandon_work_is_canonical_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            config_path = tmp_dir / "cfg.json"
            config_path.write_text(json.dumps({"run_id": "abandon-unknown"}), encoding="utf-8")
            _run_cli(tmp_dir, "dispatch", "x", "--config", str(config_path))

            result = _run_cli(
                tmp_dir,
                "dispatch",
                "--run-id",
                "abandon-unknown",
                "--abandon-work",
                "mistyped-work",
                "--abandon-reason",
                "unsettleable",
            )

            self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)
            payload = json.loads(result.stderr)
            self.assertEqual(payload["error"], "ERR-NOT-FOUND")
            self.assertEqual(
                payload["message"],
                "no such work in run 'abandon-unknown': 'mistyped-work'",
            )
            self.assertEqual(payload["next"], ["orc status abandon-unknown"])
            self.assertNotIn("KeyError", result.stderr)
            self.assertNotIn("ERR-PERMANENT", result.stderr)

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
        self.assertIn("--config /tmp/.orc/affordance-conflict/config.json", text)


class CandidateDivergenceWarningTest(unittest.TestCase):
    def _dispatch_bound(self, root: Path, candidate: dict) -> tuple[Path, subprocess.CompletedProcess]:
        path = root / "cfg.json"
        path.write_text(json.dumps({
            "run_id": "divergence-run",
            "attempts": {"work-1": [{"outcome": "completed", "candidate": candidate}]},
        }), encoding="utf-8")
        result = _run_cli(root, "dispatch", "bind candidate", "--config", str(path))
        self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
        return path, result

    def test_changed_bound_candidate_warns_without_changing_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, _ = self._dispatch_bound(root, {"head_sha": "sha-A"})
            path.write_text(json.dumps({
                "run_id": "divergence-run",
                "attempts": {"work-1": [{"outcome": "completed", "candidate": {"head_sha": "sha-B"}}]},
            }), encoding="utf-8")
            result = _run_cli(root, "dispatch", "--run-id", "divergence-run", "--config", str(path))
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            self.assertIn("warning: config candidate (sha-B)", result.stderr)
            self.assertIn("bound attempt-1 candidate (sha-A)", result.stderr)
            self.assertIn("--abandon-work work-1", result.stderr)
            self.assertIn('--abandon-reason "<why>"', result.stderr)

    def test_matching_candidate_and_unbound_candidate_do_not_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, _ = self._dispatch_bound(root, {"head_sha": "sha-A"})
            matching = _run_cli(root, "dispatch", "--run-id", "divergence-run", "--config", str(path))
            self.assertNotIn("warning: config candidate", matching.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "cfg.json"
            path.write_text(json.dumps({
                "run_id": "unbound-run",
                "attempts": {"work-1": [{"candidate": {"head_sha": "sha-B"}}]},
            }), encoding="utf-8")
            unbound = _run_cli(root, "dispatch", "unbound candidate", "--config", str(path))
            self.assertEqual(unbound.returncode, 3, msg=unbound.stdout + unbound.stderr)
            self.assertNotIn("warning: config candidate", unbound.stderr)


if __name__ == "__main__":
    unittest.main()
