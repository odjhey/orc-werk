"""SCN-014: null candidate identification recovery (issue #191)."""

from __future__ import annotations

import unittest
from typing import Any, Mapping, Optional

from orc_werk.adapters.memory.journal import MemoryJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate, fingerprint_of
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app import Orchestrator, RunConfig, default_single_work_plan
from orc_werk.core.effects import FX_IDENTIFY_CANDIDATE
from orc_werk.core.models import Candidate
from orc_werk.core.state import STATE_ACCEPTED, STATE_EXECUTING, STATE_READY


class SequencedCandidate(ScriptedCandidate):
    def __init__(self, observations: list[Optional[Mapping[str, Any]]]) -> None:
        super().__init__()
        self.observations = list(observations)
        self.calls: list[str] = []

    def identify(self, *, execution_id: str, artifact_refs=None) -> Optional[Candidate]:
        self.calls.append(execution_id)
        subject = self.observations.pop(0) if self.observations else None
        if subject is None:
            return None
        fingerprint = fingerprint_of(subject)
        return Candidate(
            id=f"cand-{fingerprint}", work_id="work-1", execution_id=execution_id,
            subject_identity=dict(subject), fingerprint=fingerprint,
        )


def build(candidate: SequencedCandidate, *, run_id: str) -> tuple[Orchestrator, MemoryJournal]:
    journal = MemoryJournal()
    orchestrator = Orchestrator(
        delivery_run_id=run_id,
        journal=journal,
        work_graph=MemoryWorkGraph(),
        execution=ScriptedExecution(script={"work-1": [{"outcome": "completed"}]}),
        candidate=candidate,
        assurance=ScriptedAssurance(script={fingerprint_of({"commit": "now-present"}): {"verdict": "accepted"}}),
        config=RunConfig(max_attempts=3),
    )
    orchestrator.bootstrap(intent_id=run_id, text="SCN-014", plan=default_single_work_plan("work-1"))
    return orchestrator, journal


class NullCandidateRecoveryScenarioTest(unittest.TestCase):
    def test_null_then_present_redispatch_reidentifies_with_stable_key_and_heals(self) -> None:
        candidate = SequencedCandidate([None, {"commit": "now-present"}])
        orchestrator, journal = build(candidate, run_id="scn014-heal")

        pending = orchestrator.run()
        wp = pending.works["work-1"]
        self.assertEqual(wp.state, STATE_EXECUTING)
        self.assertEqual(wp.attempt_number, 1)
        self.assertIsNone(wp.current_candidate_id)

        healed = orchestrator.run()
        self.assertEqual(healed.works["work-1"].state, STATE_ACCEPTED)
        self.assertEqual(len(candidate.calls), 2)
        records = [r for r in journal.history(delivery_run_id="scn014-heal") if r["id"] == FX_IDENTIFY_CANDIDATE]
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(len({r["data"]["idempotency_key"] for r in records}), 1)
        self.assertEqual(sum(r["id"] == "FACT-EXEC-STARTED" for r in journal.history(delivery_run_id="scn014-heal")), 1)
        self.assertEqual(orchestrator.projection().to_dict(), healed.to_dict())

    def test_null_persists_can_be_abandoned_to_post_abandon_rest_without_autostart(self) -> None:
        candidate = SequencedCandidate([None, None])
        orchestrator, journal = build(candidate, run_id="scn014-abandon")
        pending = orchestrator.run()
        self.assertEqual(pending.works["work-1"].state, STATE_EXECUTING)
        orchestrator.run()

        orchestrator.abandon_attempt(work_id="work-1", reason="subject still absent", by="operator")
        abandoned = orchestrator.projection()
        self.assertEqual(abandoned.works["work-1"].state, STATE_READY)
        self.assertEqual(abandoned.works["work-1"].attempt_number, 1)
        self.assertEqual(sum(r["id"] == "FACT-EXEC-STARTED" for r in journal.history(delivery_run_id="scn014-abandon")), 1)
        self.assertEqual(orchestrator.projection().to_dict(), abandoned.to_dict())

    def test_normal_first_identification_is_unchanged(self) -> None:
        candidate = SequencedCandidate([{"commit": "now-present"}])
        orchestrator, journal = build(candidate, run_id="scn014-regression")
        result = orchestrator.run()
        self.assertEqual(result.works["work-1"].state, STATE_ACCEPTED)
        self.assertEqual(len(candidate.calls), 1)
        self.assertEqual(sum(r["id"] == "FACT-CANDIDATE-OBSERVED" for r in journal.history(delivery_run_id="scn014-regression")), 1)


if __name__ == "__main__":
    unittest.main()
