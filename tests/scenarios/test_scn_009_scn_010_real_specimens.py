"""REAL-SPECIMEN regression fixtures for `SCN-009`/`SCN-010` (`TASK-M3B-001`,
issues #76/#95): `.orc/fix-69-status-resolver` (issue #76's live specimen,
legacy flat-era `FX-CREATE-WORK` with no journaled `max_attempts` -- the
`SCN-008` legacy read-fallback applies) and `.orc/trivia-sweep` (the
per-run-dir-era shape with the same candidate-reuse wedge, `max_attempts`
journaled explicitly). Both journals are copied here as static fixtures
(`tests/scenarios/specimens/`) -- this test NEVER touches the real ledger
under the repo's own `.orc/`.

Both specimens' journals end mid-attempt-2 with a `FACT-CANDIDATE-OBSERVED`
reusing attempt 1's exact candidate identity after a `rejected` verdict --
pre-`TASK-M3B-001`, replaying either journal raised `ERR-CONFLICT` on that
final record, permanently (the append-only journal cannot un-observe it;
this is issue #76's PERMANENCE escalation). Verdict inheritance (item 8)
resolves both cleanly to `READY` with the inherited rejection cited as
basis -- no abandon is needed for the real specimens as recorded (nothing
irrecoverable remains once inheritance applies: see the PR body's
Ambiguities section for why the real ledger itself is never given a
fabricated abandon). The abandon mechanism (item 9) is additionally
demonstrated end-to-end here against a run built from each specimen's own
work id / candidate identity / fingerprint (extracted from the fixture,
not hand-invented) but with attempt 1's assurance left unsettled -- the
"no prior verdict to inherit" conflict shape `SCN-010` specifies -- so
`DEC-ABANDON-ATTEMPT` is proven to settle a run carrying either specimen's
own identity values, per the task card's acceptance note.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.core.errors import CoreError
from orc_werk.core.facts import FACT_ATTEMPT_ABANDONED, FACT_EXEC_STARTED, make_fact
from orc_werk.core.policy import decide
from orc_werk.core.reducer import apply_fact, reduce
from orc_werk.core.state import STATE_BLOCKED, STATE_EXECUTING, STATE_READY

from tests.core import fixtures

FIXTURES = Path(__file__).parent / "specimens"
SPECIMENS = ("fix-69-status-resolver", "trivia-sweep")
# Both specimens use a single-work plan; the one work id differs per run.
WORK_IDS = {"fix-69-status-resolver": "resolver-fix", "trivia-sweep": "sweep"}


def _load(tmp: Path, run_id: str) -> JSONLJournal:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / run_id / "journal.jsonl", run_dir / "journal.jsonl")
    return JSONLJournal(tmp)


def _specimen_candidate_identity(run_id: str) -> tuple[str, str]:
    """`(candidate_id, fingerprint)` from the specimen fixture's own first
    `FACT-CANDIDATE-OBSERVED` record -- real values, not hand-invented."""
    lines = (FIXTURES / run_id / "journal.jsonl").read_text().splitlines()
    for line in lines:
        record = json.loads(line)
        if record["id"] == "FACT-CANDIDATE-OBSERVED":
            return record["data"]["candidate_id"], record["data"]["fingerprint"]
    raise AssertionError(f"specimen fixture {run_id!r} carries no FACT-CANDIDATE-OBSERVED")


class RealSpecimenReplayTest(unittest.TestCase):
    """`SCN-009`: both specimens replay to a stable projection, no
    `ERR-CONFLICT`, deterministic across repeated reads (`INV-020` spirit)."""

    def test_both_specimens_replay_without_conflict_and_stably(self) -> None:
        for run_id in SPECIMENS:
            with self.subTest(run_id=run_id):
                with tempfile.TemporaryDirectory() as tmp:
                    journal = _load(Path(tmp), run_id)
                    proj1 = journal.load_projection(delivery_run_id=run_id)  # must not raise.
                    proj2 = journal.load_projection(delivery_run_id=run_id)
                    self.assertEqual(proj1.to_dict(), proj2.to_dict())

                    wp = proj1.works[WORK_IDS[run_id]]
                    self.assertIsNone(wp.candidate_conflict)
                    # Attempt 2's re-observed candidate inherited attempt
                    # 1's rejection; budget (3, default-fallback or
                    # journaled) leaves attempt 3 available -> READY.
                    self.assertEqual(wp.state, STATE_READY)
                    self.assertEqual(wp.attempt_number, 2)
                    settled = [a for a in wp.assurances if a.get("verdict") is not None]
                    self.assertEqual(len(settled), 1, "no second settlement was fabricated (INV-003)")

                    # Every read-side consumer built on load_projection
                    # renders this run without a canonical error (SCN-008's
                    # "every read-side consumer" clause, mirrored here).
                    history = journal.history(delivery_run_id=run_id)
                    self.assertTrue(history)


class RealSpecimenAbandonTest(unittest.TestCase):
    """`SCN-010` candidate-observation-conflict shape, built from each
    specimen's own work id / candidate id / fingerprint: attempt 1's
    Assurance never settles (nothing to inherit), attempt 2 re-observes
    the exact same real candidate identity, rests conflicted, and
    `DEC-ABANDON-ATTEMPT`/`FACT-ATTEMPT-ABANDONED` settles it end to end."""

    def test_abandon_settles_a_run_carrying_each_specimens_candidate_identity(self) -> None:
        for run_id in SPECIMENS:
            with self.subTest(run_id=run_id):
                work_id = WORK_IDS[run_id]
                candidate_id, fingerprint = _specimen_candidate_identity(run_id)

                # Attempt 1: the specimen's own candidate identity observed;
                # assurance started but never settled (nothing to inherit).
                facts = fixtures.assuring(
                    delivery_run_id=run_id,
                    work_id=work_id,
                    execution_id="e1",
                    candidate_id=candidate_id,
                    fingerprint=fingerprint,
                    assurance_id="a1",
                )
                wp = reduce(facts, delivery_run_id=run_id, max_attempts=2).works[work_id]
                self.assertEqual(wp.state, "ASSURING")

                # Operator abandons the unsettleable assurance -> READY.
                wp = apply_fact(
                    wp,
                    make_fact(FACT_ATTEMPT_ABANDONED, delivery_run_id=run_id, work_id=work_id, reason="unsettleable"),
                    max_attempts=2,
                )
                self.assertEqual(wp.state, STATE_READY)

                # Attempt 2 re-produces the exact same specimen candidate
                # (an unchanged worktree re-executed -- the real specimens'
                # own shape) -- but nothing settled remains to inherit from.
                wp = apply_fact(
                    wp, make_fact(FACT_EXEC_STARTED, delivery_run_id=run_id, work_id=work_id, execution_id="e2"),
                    max_attempts=2,
                )
                wp = apply_fact(
                    wp,
                    make_fact(
                        "FACT-EXEC-SETTLED", delivery_run_id=run_id, work_id=work_id, execution_id="e2",
                        outcome="completed",
                    ),
                    max_attempts=2,
                )
                wp = apply_fact(
                    wp,
                    make_fact(
                        "FACT-CANDIDATE-OBSERVED",
                        delivery_run_id=run_id,
                        work_id=work_id,
                        candidate_id=candidate_id,
                        fingerprint=fingerprint,
                        execution_id="e2",
                    ),
                    max_attempts=2,
                )  # must not raise ERR-CONFLICT.
                self.assertEqual(wp.state, STATE_EXECUTING)
                self.assertIsNotNone(wp.candidate_conflict)
                self.assertEqual(wp.candidate_conflict["candidate_id"], candidate_id)

                # Nothing but abandon is a legal continuation from this
                # conflicted rest.
                with self.assertRaises(CoreError):
                    apply_fact(
                        wp,
                        make_fact("FACT-WORK-BLOCKED", delivery_run_id=run_id, work_id=work_id, reason="x"),
                        max_attempts=2,
                    )

                # Second abandon settles the run end to end: attempt 2 of 2
                # exhausted -> BLOCKED, reason attempt-abandoned.
                wp = apply_fact(
                    wp,
                    make_fact(
                        FACT_ATTEMPT_ABANDONED, delivery_run_id=run_id, work_id=work_id, reason="identity collision"
                    ),
                    max_attempts=2,
                )
                self.assertIsNone(wp.candidate_conflict)
                self.assertEqual(wp.state, STATE_BLOCKED)
                outcome = decide(wp, max_attempts=2)
                assert outcome is not None
                self.assertEqual(outcome.decision.data["reason"], "attempt-abandoned")


if __name__ == "__main__":
    unittest.main()
