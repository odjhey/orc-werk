"""SCN-002 -- assurance rejection followed by retry: two distinct
Executions, C1/C2 have different fingerprints, evidence for C1 stays bound
only to C1, rejection of C1 does not complete Work A, acceptance of C2
does, decision history contains exactly one `DEC-RETRY`
(`docs/scenarios/SCN-002-assurance-retry.md`). Verifies INV-004, INV-007,
INV-008, INV-010, INV-018.

Also includes the M0 crash-resume acceptance test (task-card TASK-M0-005):
stop mid-run right after attempt 1's rejection (a durable `JSONLJournal`
snapshot), construct a *fresh* `Orchestrator` -- fresh `MemoryWorkGraph`
and fresh scripted ports, same journal directory -- and assert the resumed
run reaches the identical terminal outcome with no duplicated effect
records (by idempotency key).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate, fingerprint_of
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app import Orchestrator, RunConfig, default_single_work_plan
from orc_werk.core.decisions import DEC_RETRY
from orc_werk.core.state import STATE_ACCEPTED, STATE_READY

from tests.scenarios.support import build_run, predicted_execution_id

DRID = "scn002"
WORK_ID = "A"

ATTEMPTS = [
    {"outcome": "completed", "candidate": {"label": "C1"}, "verdict": "rejected"},
    {"outcome": "completed", "candidate": {"label": "C2"}, "verdict": "accepted"},
]


class Scn002AssuranceRetryTest(unittest.TestCase):
    def test_retry_produces_new_execution_and_candidate(self) -> None:
        orchestrator, journal, _work_graph = build_run(
            delivery_run_id=DRID, attempts_by_work={WORK_ID: ATTEMPTS}
        )
        projection = orchestrator.run()
        wp = projection.works[WORK_ID]
        history = journal.history(delivery_run_id=DRID)

        # 1. Two distinct Executions exist.
        self.assertEqual(len(wp.executions), 2)
        self.assertNotEqual(wp.executions[0]["execution_id"], wp.executions[1]["execution_id"])

        # 2. C1 and C2 have different fingerprints.
        fingerprints = [entry["fingerprint"] for entry in wp.candidates.values()]
        self.assertEqual(len(fingerprints), 2)
        self.assertEqual(len(set(fingerprints)), 2)

        # 3. Evidence for C1 remains bound only to C1.
        assure_settled = [r for r in history if r["kind"] == "fact" and r["id"] == "FACT-ASSURE-SETTLED"]
        self.assertEqual(len(assure_settled), 2)
        self.assertEqual(assure_settled[0]["data"]["candidate_fingerprint"], fingerprints[0])
        self.assertEqual(assure_settled[0]["data"]["verdict"], "rejected")
        self.assertEqual(assure_settled[1]["data"]["candidate_fingerprint"], fingerprints[1])
        self.assertEqual(assure_settled[1]["data"]["verdict"], "accepted")

        # 4. Rejection of C1 does not complete Work A / 5. Acceptance of C2 completes Work A.
        self.assertEqual(wp.state, STATE_ACCEPTED)
        self.assertTrue(wp.completed_confirmed)
        completed_facts = [r for r in history if r["kind"] == "fact" and r["id"] == "FACT-WORK-COMPLETED"]
        self.assertEqual(len(completed_facts), 1)

        # 6. Decision history contains one DEC-RETRY.
        retry_decisions = [r for r in history if r["kind"] == "decision" and r["id"] == DEC_RETRY]
        self.assertEqual(len(retry_decisions), 1)

    def test_crash_resume_reaches_identical_terminal_outcome_without_duplicate_effects(self) -> None:
        def build_ports():
            return (
                ScriptedExecution(script={WORK_ID: [{"outcome": "completed"}, {"outcome": "completed"}]}),
                ScriptedCandidate(
                    subjects={
                        predicted_execution_id(delivery_run_id=DRID, work_id=WORK_ID, attempt_number=1): {
                            "work_id": WORK_ID,
                            "subject_identity": {"label": "C1"},
                        },
                        predicted_execution_id(delivery_run_id=DRID, work_id=WORK_ID, attempt_number=2): {
                            "work_id": WORK_ID,
                            "subject_identity": {"label": "C2"},
                        },
                    },
                    current_by_work={},
                ),
                ScriptedAssurance(
                    script={
                        fingerprint_of({"label": "C1"}): {"verdict": "rejected"},
                        fingerprint_of({"label": "C2"}): {"verdict": "accepted"},
                    }
                ),
            )

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)

            journal = JSONLJournal(directory)
            work_graph = MemoryWorkGraph()
            execution, candidate, assurance = build_ports()
            orchestrator = Orchestrator(
                delivery_run_id=DRID,
                journal=journal,
                work_graph=work_graph,
                execution=execution,
                candidate=candidate,
                assurance=assurance,
                config=RunConfig(max_attempts=3),
            )
            orchestrator.bootstrap(intent_id=DRID, text="scn002 crash resume", plan=default_single_work_plan(WORK_ID))

            # Advance until attempt 1's rejection has put the Work back to
            # READY for retry, then stop -- simulating a crash right at that
            # fact-level checkpoint.
            for _ in range(100):
                wp = orchestrator.projection().works[WORK_ID]
                if wp.state == STATE_READY and wp.attempt_number == 1:
                    break
                if not orchestrator.step():
                    break
            partial_history = journal.history(delivery_run_id=DRID)
            self.assertGreater(len(partial_history), 0)
            self.assertEqual(orchestrator.projection().works[WORK_ID].state, STATE_READY)

            # "Crash": construct a brand-new Orchestrator over the same
            # journal directory, with fresh (state-losing) ports.
            journal2 = JSONLJournal(directory)
            work_graph2 = MemoryWorkGraph()
            execution2, candidate2, assurance2 = build_ports()
            resumed = Orchestrator(
                delivery_run_id=DRID,
                journal=journal2,
                work_graph=work_graph2,
                execution=execution2,
                candidate=candidate2,
                assurance=assurance2,
                config=RunConfig(max_attempts=3),
            )
            projection = resumed.run()
            wp = projection.works[WORK_ID]
            self.assertEqual(wp.state, STATE_ACCEPTED)
            self.assertTrue(wp.completed_confirmed)
            self.assertEqual(wp.attempt_number, 2)

            # No duplicated effects by idempotency key.
            final_history = journal2.history(delivery_run_id=DRID)
            effect_keys = [
                r["data"]["idempotency_key"] for r in final_history if r["kind"] == "effect"
            ]
            self.assertEqual(len(effect_keys), len(set(effect_keys)))

            # Identical terminal outcome to an uninterrupted clean run.
            with tempfile.TemporaryDirectory() as clean_tmp:
                clean_journal = JSONLJournal(Path(clean_tmp))
                clean_work_graph = MemoryWorkGraph()
                clean_execution, clean_candidate, clean_assurance = build_ports()
                clean_orchestrator = Orchestrator(
                    delivery_run_id=DRID,
                    journal=clean_journal,
                    work_graph=clean_work_graph,
                    execution=clean_execution,
                    candidate=clean_candidate,
                    assurance=clean_assurance,
                    config=RunConfig(max_attempts=3),
                )
                clean_orchestrator.bootstrap(
                    intent_id=DRID, text="scn002 crash resume", plan=default_single_work_plan(WORK_ID)
                )
                clean_projection = clean_orchestrator.run()
                self.assertEqual(
                    clean_projection.works[WORK_ID].to_dict(), wp.to_dict()
                )
                self.assertEqual(
                    len(clean_journal.history(delivery_run_id=DRID)), len(final_history)
                )


if __name__ == "__main__":
    unittest.main()
