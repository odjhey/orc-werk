"""SCN-008 -- replay under the run's own retry budget
(`docs/scenarios/SCN-008-replay-budget.md`, issue #52): a run dispatched
with a non-default `max_attempts` that exhausts its budget to `BLOCKED`
must replay cleanly through `Orchestrator`/`JournalPort.load_projection`
alike -- a fresh replay reads the run's own recorded budget back out of
the `FX-CREATE-WORK` effect record (`data.max_attempts`, mirroring the
ratified topology-durability precedent for `data.plan`, issue #41) rather
than folding under the reducer's schema default. Verifies `PORT-JOURNAL-005`,
`CONF-JOURNAL-003`, `INV-018`, `INV-019`.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.core.effects import FX_CREATE_WORK
from orc_werk.core.reducer import DEFAULT_MAX_ATTEMPTS
from orc_werk.core.serialization import KIND_EFFECT
from orc_werk.core.state import STATE_BLOCKED

from tests.scenarios.support import build_run

DRID = "scn008-replay-budget"
WORK_ID = "work-1"
NON_DEFAULT_BUDGET = 2


class Scn008ReplayBudgetTest(unittest.TestCase):
    def test_blocked_run_under_non_default_budget_replays_cleanly(self) -> None:
        self.assertNotEqual(NON_DEFAULT_BUDGET, DEFAULT_MAX_ATTEMPTS)
        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp) / ".orc"
            journal = JSONLJournal(journal_dir)

            orchestrator, journal, _work_graph = build_run(
                delivery_run_id=DRID,
                attempts_by_work={WORK_ID: [{"outcome": "failed"} for _ in range(NON_DEFAULT_BUDGET)]},
                max_attempts=NON_DEFAULT_BUDGET,
                journal=journal,
            )
            projection = orchestrator.run()
            wp = projection.works[WORK_ID]
            self.assertEqual(wp.state, STATE_BLOCKED)
            self.assertTrue(wp.blocked_confirmed)

            # -- the effective budget is durable, alongside the plan -----
            history = journal.history(delivery_run_id=DRID)
            create_work = next(
                r for r in history if r["kind"] == KIND_EFFECT and r["id"] == FX_CREATE_WORK
            )
            self.assertEqual(create_work["data"]["max_attempts"], NON_DEFAULT_BUDGET)
            self.assertIn("plan", create_work["data"])

            # -- a FRESH reader, with no access to the original dispatch
            # config/RunConfig, replays this BLOCKED run cleanly rather
            # than raising ERR-CONFLICT ("FACT-WORK-BLOCKED illegal from
            # state 'READY'") from folding under the wrong (higher,
            # default) budget. --------------------------------------------
            reopened = JSONLJournal(journal_dir)
            replayed = reopened.load_projection(delivery_run_id=DRID)
            replayed_wp = replayed.works[WORK_ID]
            self.assertEqual(replayed_wp.state, STATE_BLOCKED)
            self.assertTrue(replayed_wp.blocked_confirmed)
            self.assertEqual(replayed_wp.attempt_number, NON_DEFAULT_BUDGET)
            self.assertEqual(replayed.to_dict(), projection.to_dict())

    def test_legacy_journal_without_recorded_budget_falls_back_to_schema_default(self) -> None:
        # A journal written before this fix has FX-CREATE-WORK's data.plan
        # but no data.max_attempts -- simulate that by dispatching at the
        # schema default and then stripping the field from the persisted
        # record, exactly like a pre-fix journal would look on disk.
        with tempfile.TemporaryDirectory() as tmp:
            journal_dir = Path(tmp) / ".orc"
            journal = JSONLJournal(journal_dir)

            orchestrator, journal, _work_graph = build_run(
                delivery_run_id=DRID,
                attempts_by_work={
                    WORK_ID: [{"outcome": "completed", "candidate": {"label": "A"}, "verdict": "accepted"}]
                },
                max_attempts=DEFAULT_MAX_ATTEMPTS,
                journal=journal,
            )
            orchestrator.run()

            journal_path = journal_dir / DRID / "journal.jsonl"
            lines = journal_path.read_text(encoding="utf-8").splitlines()
            rewritten = []
            for line in lines:
                record = json.loads(line)
                if record.get("id") == FX_CREATE_WORK:
                    del record["data"]["max_attempts"]
                rewritten.append(json.dumps(record, sort_keys=True))
            journal_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")

            reopened = JSONLJournal(journal_dir)
            replayed = reopened.load_projection(delivery_run_id=DRID)
            self.assertTrue(replayed.works[WORK_ID].completed_confirmed)


if __name__ == "__main__":
    unittest.main()
