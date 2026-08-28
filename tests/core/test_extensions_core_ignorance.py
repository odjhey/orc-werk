"""CONF-EXT-006 (core ignorance): changing an extension payload while
keeping canonical facts identical MUST NOT change reducer/policy transitions
or decisions under v0 policy, which does not consume any extension."""

from __future__ import annotations

import unittest
from dataclasses import replace

from orc_werk.core.policy import decide
from orc_werk.core.reducer import reduce

from tests.core import fixtures

DRID = "dr-ext"


def _with_extension(facts, index: int, extensions: dict):
    fact = facts[index]
    facts = list(facts)
    facts[index] = replace(fact, extensions=extensions)
    return facts


class CoreIgnoranceTest(unittest.TestCase):
    def test_reducer_ignores_extension_payload_changes(self) -> None:
        facts = fixtures.settled_completed_with_candidate(
            delivery_run_id=DRID, work_id="w1", execution_id="e1", candidate_id="c1", fingerprint="fp1"
        )
        baseline = reduce(facts, delivery_run_id=DRID).works["w1"]

        variant_a = _with_extension(facts, -1, {"review-findings/v1": {"findings": []}})
        variant_b = _with_extension(
            facts, -1, {"review-findings/v1": {"findings": [{"path": "x.py"}]}, "unknown/v9": {"z": 1}}
        )

        proj_a = reduce(variant_a, delivery_run_id=DRID).works["w1"]
        proj_b = reduce(variant_b, delivery_run_id=DRID).works["w1"]

        for candidate in (proj_a, proj_b):
            self.assertEqual(candidate.state, baseline.state)
            self.assertEqual(candidate.current_candidate_id, baseline.current_candidate_id)
            self.assertEqual(candidate.attempt_number, baseline.attempt_number)

    def test_policy_decision_and_effects_unaffected_by_extension_payload(self) -> None:
        facts = fixtures.settled_completed_with_candidate(
            delivery_run_id=DRID, work_id="w1", execution_id="e1", candidate_id="c1", fingerprint="fp1"
        )
        baseline_wp = reduce(facts, delivery_run_id=DRID).works["w1"]
        baseline_outcome = decide(baseline_wp)
        assert baseline_outcome is not None

        variant = _with_extension(
            facts, -1, {"review-findings/v1": {"findings": [{"path": "x.py", "severity": "high"}]}}
        )
        variant_wp = reduce(variant, delivery_run_id=DRID).works["w1"]
        variant_outcome = decide(variant_wp)
        assert variant_outcome is not None

        self.assertEqual(variant_outcome.decision.id, baseline_outcome.decision.id)
        self.assertEqual(
            [e.id for e in variant_outcome.effects], [e.id for e in baseline_outcome.effects]
        )
        self.assertEqual(
            [e.idempotency_key for e in variant_outcome.effects],
            [e.idempotency_key for e in baseline_outcome.effects],
        )


if __name__ == "__main__":
    unittest.main()
