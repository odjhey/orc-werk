"""SCN-006 -- unsupported capability: policy requires exact resume, the
selected Execution adapter advertises only best-effort resume, the kernel
does not silently start a fresh conversation, the operation fails with
`ERR-UNSUPPORTED-CAPABILITY`, and the Decision and failure are journaled
(`docs/scenarios/SCN-006-capability-failure.md`). Verifies INV-013.
"""

from __future__ import annotations

import unittest

from orc_werk.adapters.memory.journal import MemoryJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app import Orchestrator, RunConfig, default_single_work_plan
from orc_werk.core.decisions import DEC_DISPATCH
from orc_werk.core.effects import FX_START_EXECUTION
from orc_werk.core.errors import ERR_UNSUPPORTED_CAPABILITY
from orc_werk.core.state import STATE_BLOCKED
from orc_werk.ports.capabilities import CAP_EXEC_RESUME_BEST_EFFORT, CAP_EXEC_RESUME_EXACT

DRID = "scn006"
WORK_ID = "A"


class Scn006CapabilityFailureTest(unittest.TestCase):
    def test_exact_resume_required_but_only_best_effort_advertised(self) -> None:
        journal = MemoryJournal()
        work_graph = MemoryWorkGraph()
        # Would happily "complete" if ever actually started -- proving the
        # kernel never falls through to a fresh start()/conversation.
        execution = ScriptedExecution(
            script={WORK_ID: [{"outcome": "completed"}]},
            capabilities=[CAP_EXEC_RESUME_BEST_EFFORT],
        )
        candidate = ScriptedCandidate()
        assurance = ScriptedAssurance(script={})

        orchestrator = Orchestrator(
            delivery_run_id=DRID,
            journal=journal,
            work_graph=work_graph,
            execution=execution,
            candidate=candidate,
            assurance=assurance,
            # Policy requires exact resume; max_attempts=1 so the resulting
            # single failed attempt exhausts the retry budget deterministically.
            config=RunConfig(max_attempts=1, resume_capability=CAP_EXEC_RESUME_EXACT),
        )
        orchestrator.bootstrap(intent_id=DRID, text="scn006", plan=default_single_work_plan(WORK_ID))
        projection = orchestrator.run()
        wp = projection.works[WORK_ID]

        # The kernel does not silently start a fresh conversation: no
        # Execution was ever actually started against the port.
        self.assertEqual(execution._by_idempotency_key, {})

        # The operation fails with ERR-UNSUPPORTED-CAPABILITY, and the
        # failure is journaled in the effect record.
        history = journal.history(delivery_run_id=DRID)
        start_effects = [r for r in history if r["kind"] == "effect" and r["id"] == FX_START_EXECUTION]
        self.assertEqual(len(start_effects), 1)
        dispatch_result = start_effects[0]["data"]["dispatch_result"]
        self.assertEqual(dispatch_result["error"], ERR_UNSUPPORTED_CAPABILITY)
        self.assertEqual(dispatch_result["details"]["capability"], CAP_EXEC_RESUME_EXACT)

        # The Decision (DEC-DISPATCH) that led to the failed dispatch is journaled.
        decisions = [r for r in history if r["kind"] == "decision"]
        self.assertEqual(decisions[0]["id"], DEC_DISPATCH)

        # Policy blocks the Work rather than silently proceeding.
        self.assertEqual(wp.state, STATE_BLOCKED)
        self.assertTrue(wp.blocked_confirmed)


if __name__ == "__main__":
    unittest.main()
