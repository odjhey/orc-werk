"""Regression pin for the CONTRACT-DURABILITY ownership-matrix row "Run
topology (create plan: works + dependency edges)" (operator ruling, issue
#41): the `FX-CREATE-WORK` effect record's journaled `data.plan`
(`PORT-WORK-001` plan shape) is the durable owner of a run's topology. A
journal from which the run's topology cannot be reconstructed is
non-conformant.

This test drives a multi-work fan-in plan (the SCN-005 a,b->c shape,
`tests/scenarios/test_scn_005_fanin.py`) through the `Orchestrator` with
scripted adapters and a real file-backed `JSONLJournal`, then reconstructs
the topology from the JOURNAL ALONE -- reading history records back out,
never touching the `PLAN` object the run was built from -- and asserts it
against an independently authored expected structure (not a tautology
against whatever the orchestrator happened to emit). It also asserts the
reconstruction survives a JSONL round-trip: closing and reopening a fresh
`JSONLJournal` instance over the same on-disk file.
"""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.core.effects import FX_CREATE_WORK
from orc_werk.core.serialization import KIND_EFFECT

from tests.scenarios.support import build_run

DRID = "topology-durability-run"

PLAN = {
    "works": [
        {"work_id": "a", "deps": []},
        {"work_id": "b", "deps": []},
        {
            "work_id": "c",
            "deps": [{"work_id": "a", "condition": "accepted"}, {"work_id": "b", "condition": "accepted"}],
        },
    ]
}

# Independently authored expectation -- deliberately NOT the same object as
# PLAN above (a deep copy), so the assertion below cannot degrade into
# "the journal echoes back whatever object identity it was given."
EXPECTED_PLAN = copy.deepcopy(PLAN)

ATTEMPTS = {
    "a": [{"outcome": "completed", "candidate": {"label": "A1"}, "verdict": "accepted"}],
    "b": [{"outcome": "completed", "candidate": {"label": "B1"}, "verdict": "accepted"}],
    "c": [{"outcome": "completed", "candidate": {"label": "C1"}, "verdict": "accepted"}],
}


def _find_create_work_plan(history: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """Reconstruct the run topology from journal history records ALONE --
    no access to the `PLAN`/config object the run was originally built
    from. Mirrors the replay path `Orchestrator._replay_effect_record`
    itself uses to rebuild `WorkGraphPort` state after a restart."""
    for record in history:
        if record.get("kind") != KIND_EFFECT:
            continue
        if record.get("id") != FX_CREATE_WORK:
            continue
        return record["data"]["plan"]
    return None


class TopologyDurabilityTest(unittest.TestCase):
    def test_fanin_topology_reconstructable_from_journal_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp) / ".orc"
            journal = JSONLJournal(journal_dir)

            orchestrator, journal, _work_graph = build_run(
                delivery_run_id=DRID,
                plan=PLAN,
                attempts_by_work=ATTEMPTS,
                journal=journal,
            )
            projection = orchestrator.run()
            for work_id in ("a", "b", "c"):
                self.assertTrue(projection.works[work_id].completed_confirmed)

            # -- from the journal alone --------------------------------------
            history = journal.history(delivery_run_id=DRID)
            reconstructed_plan = _find_create_work_plan(history)
            self.assertIsNotNone(reconstructed_plan)

            self.assertEqual(reconstructed_plan, EXPECTED_PLAN)
            self.assertEqual(
                {w["work_id"] for w in reconstructed_plan["works"]}, {"a", "b", "c"}
            )
            c_entry = next(w for w in reconstructed_plan["works"] if w["work_id"] == "c")
            self.assertEqual(
                sorted(c_entry["deps"], key=lambda d: d["work_id"]),
                [
                    {"work_id": "a", "condition": "accepted"},
                    {"work_id": "b", "condition": "accepted"},
                ],
            )

            # -- survives a JSONL round-trip: reopen and re-read -------------
            reopened = JSONLJournal(journal_dir)
            reopened_history = reopened.history(delivery_run_id=DRID)
            reopened_plan = _find_create_work_plan(reopened_history)
            self.assertEqual(reopened_plan, EXPECTED_PLAN)


if __name__ == "__main__":
    unittest.main()
