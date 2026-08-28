"""Extension lossless-transport at the orchestrator boundary
(`CONTRACT-EXTENSIONS`, `CONF-EXT-003`, `CONF-EXT-006`).

`ExecutionObservation.extensions`/`AssuranceObservation.extensions` are
opaque, portable baggage a provider may attach to a settled observation
(`PORT-EXECUTION`, `PORT-ASSURANCE`). `CONF-EXT-003` requires this baggage
survive transport losslessly; `CONF-EXT-006` requires the generic core
(and, by the same principle, the orchestrator interpreting it) never
inspect/branch on it. This scenario drives a scripted execution and
assurance carrying an *unregistered* extension key end-to-end through
`orc_werk.app.Orchestrator` and a durable `JSONLJournal`, and asserts:

1. the journaled `FACT-EXEC-SETTLED`/`FACT-ASSURE-SETTLED` envelope
   `extensions` fields are byte-identical (round-tripped through disk/JSON)
   to what the scripted adapters produced;
2. the run's terminal outcome is completely unaffected by their presence
   (core-ignorance, `CONF-EXT-006`);
3. Work acceptance still only happens after assurance acceptance, never
   merely because an Execution "completed" (`INV-003`) -- an unregistered
   extension payload riding along on the settlement must not change that.
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
from orc_werk.core.state import STATE_ACCEPTED

from tests.scenarios.support import predicted_execution_id

DRID = "ext-transport"
WORK_ID = "work-1"

EXEC_EXTENSION_PAYLOAD = {
    "some-ext/v1": {"nested": {"value": 42, "list": [1, 2, 3]}, "note": "unregistered"}
}
ASSURE_EXTENSION_PAYLOAD = {"some-ext/v1": {"finding_count": 3, "severities": ["low", "high"]}}


class ExtensionLosslessTransportTest(unittest.TestCase):
    def test_unregistered_extensions_survive_jsonl_round_trip_and_outcome_is_unaffected(self) -> None:
        candidate_content = {"label": "C1"}
        fingerprint = fingerprint_of(candidate_content)
        execution_id = predicted_execution_id(delivery_run_id=DRID, work_id=WORK_ID, attempt_number=1)

        with tempfile.TemporaryDirectory() as tmp:
            journal = JSONLJournal(Path(tmp))
            work_graph = MemoryWorkGraph()
            execution = ScriptedExecution(
                script={
                    WORK_ID: [
                        {"outcome": "completed", "extensions": EXEC_EXTENSION_PAYLOAD},
                    ]
                }
            )
            candidate = ScriptedCandidate(
                subjects={execution_id: {"work_id": WORK_ID, "subject_identity": candidate_content}},
                current_by_work={},
            )
            assurance = ScriptedAssurance(
                script={
                    fingerprint: {"verdict": "accepted", "extensions": ASSURE_EXTENSION_PAYLOAD},
                }
            )

            orchestrator = Orchestrator(
                delivery_run_id=DRID,
                journal=journal,
                work_graph=work_graph,
                execution=execution,
                candidate=candidate,
                assurance=assurance,
                config=RunConfig(max_attempts=3),
            )
            orchestrator.bootstrap(intent_id=DRID, text="extension transport", plan=default_single_work_plan(WORK_ID))
            projection = orchestrator.run()

            # Outcome is unaffected by the presence of an unregistered
            # extension payload (CONF-EXT-006 core-ignorance).
            wp = projection.works[WORK_ID]
            self.assertEqual(wp.state, STATE_ACCEPTED)
            self.assertTrue(wp.completed_confirmed)

            history = journal.history(delivery_run_id=DRID)

            exec_settled = next(
                r for r in history if r["kind"] == "fact" and r["id"] == "FACT-EXEC-SETTLED"
            )
            self.assertEqual(exec_settled["extensions"], EXEC_EXTENSION_PAYLOAD)

            assure_settled = next(
                r for r in history if r["kind"] == "fact" and r["id"] == "FACT-ASSURE-SETTLED"
            )
            self.assertEqual(assure_settled["extensions"], ASSURE_EXTENSION_PAYLOAD)

            # INV-003: Work acceptance happened only after assurance
            # acceptance -- FACT-EXEC-SETTLED(completed) alone (carrying its
            # extension payload) never journals FACT-WORK-COMPLETED by
            # itself. Confirm ordering: settlement -> candidate -> assurance
            # request -> assurance settled(accepted) -> DEC-ACCEPT -> completed.
            ordered_ids = [r["id"] for r in history if r["kind"] in ("fact", "decision")]
            exec_settled_pos = ordered_ids.index("FACT-EXEC-SETTLED")
            assure_settled_pos = ordered_ids.index("FACT-ASSURE-SETTLED")
            accept_pos = ordered_ids.index("DEC-ACCEPT")
            completed_pos = ordered_ids.index("FACT-WORK-COMPLETED")
            self.assertLess(exec_settled_pos, assure_settled_pos)
            self.assertLess(assure_settled_pos, accept_pos)
            self.assertLess(accept_pos, completed_pos)
            # No FACT-WORK-COMPLETED could have been journaled between the
            # (completed) execution settlement and the (accepted) assurance
            # settlement -- reconfirms INV-003 is not merely coincidental
            # for this run.
            self.assertNotIn(
                "FACT-WORK-COMPLETED", ordered_ids[exec_settled_pos + 1 : assure_settled_pos]
            )


if __name__ == "__main__":
    unittest.main()
