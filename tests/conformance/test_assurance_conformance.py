"""`CONF-ASSURE-*` conformance suite (`PORT-ASSURANCE`).

`AssurancePortConformance` is a reusable mixin (not itself a `TestCase`):
any current or future `AssurancePort` implementation runs the same suite
by subclassing it alongside `unittest.TestCase` and implementing
`make_assurance()`.

`CONF-ASSURE-003` ("evidence from a different fingerprint is rejected by
the kernel") is deliberately NOT an `AssurancePort` adapter-level test: the
task card is explicit that this is core's job (`orc_werk.core.reducer`,
`INV-008`/`INV-010`). The adapter's only obligation is to faithfully report
the fingerprint it actually evaluated (`INV-007`) so the kernel check has
something honest to check. `Conf003ForeignFingerprintRejectedByKernelTest`
below proves that end-to-end: it uses `ScriptedCandidate`/`ScriptedAssurance`
to produce two real, differently-fingerprinted candidates, then folds a
`FACT-ASSURE-SETTLED` carrying the *other* candidate's (adapter-reported)
fingerprint through `orc_werk.core.reducer.reduce` and asserts the kernel
rejects it.
"""

from __future__ import annotations

import unittest
from typing import Any, Iterable, Mapping, Optional

from orc_werk.adapters.scripted import ScriptedAssurance, ScriptedCandidate
from orc_werk.core.errors import CoreError
from orc_werk.core.facts import FACT_ASSURE_SETTLED, make_fact
from orc_werk.core.models import Candidate
from orc_werk.core.reducer import reduce
from orc_werk.ports.assurance import AssurancePort
from orc_werk.ports.base import LIFECYCLE_STATE_SETTLED
from orc_werk.ports.capabilities import CAP_ASSURE_CANDIDATE_BOUND, CAP_ASSURE_MAY_MUTATE_CANDIDATE

from tests.core import fixtures

DRID = "dr-assure-conformance"


def _candidate(work_id: str, execution_id: str, content: Any) -> Candidate:
    """Build one real, adapter-derived Candidate via `ScriptedCandidate` so
    every test below exercises actual adapter fingerprint derivation rather
    than hand-picked fingerprint strings."""
    provider = ScriptedCandidate(
        subjects={execution_id: {"work_id": work_id, "subject_identity": content}}
    )
    candidate = provider.identify(execution_id=execution_id)
    assert candidate is not None
    return candidate


class AssurancePortConformance:
    def make_assurance(
        self,
        *,
        script: Mapping[str, Mapping[str, Any]],
        capabilities: Optional[Iterable[str]] = None,
    ) -> AssurancePort:
        raise NotImplementedError

    # -- CONF-ASSURE-001: settled evidence names the candidate fingerprint. --

    def test_conf_assure_001_settled_evidence_names_candidate_fingerprint(self) -> None:
        candidate = _candidate("w1", "e1", {"a": 1})
        adapter = self.make_assurance(
            script={candidate.fingerprint: {"verdict": "accepted", "evidence_refs": ["report-1"]}}
        )
        run = adapter.request(candidate=candidate, requirements={}, idempotency_key="k1")
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(observed.candidate_fingerprint, candidate.fingerprint)
        self.assertIn("report-1", observed.evidence_refs)

    # -- CONF-ASSURE-002: rejected never normalizes to accepted (immutable settled verdicts). --

    def test_conf_assure_002_rejected_never_normalizes_to_accepted(self) -> None:
        candidate = _candidate("w1", "e1", {"a": 1})
        adapter = self.make_assurance(script={candidate.fingerprint: {"verdict": "rejected"}})
        run = adapter.request(candidate=candidate, requirements={}, idempotency_key="k1")
        for _ in range(3):
            observed = adapter.inspect(assurance_id=run.id)
            self.assertEqual(observed.verdict, "rejected")

    # -- CONF-ASSURE-004: inconclusive remains distinct from rejected/accepted. --

    def test_conf_assure_004_inconclusive_distinct_from_rejected_and_accepted(self) -> None:
        candidate = _candidate("w1", "e1", {"a": 1})
        adapter = self.make_assurance(script={candidate.fingerprint: {"verdict": "inconclusive"}})
        run = adapter.request(candidate=candidate, requirements={}, idempotency_key="k1")
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.verdict, "inconclusive")
        self.assertNotIn(observed.verdict, ("rejected", "accepted"))

    # -- request() is idempotent on idempotency_key. --

    def test_request_is_idempotent_on_idempotency_key(self) -> None:
        candidate = _candidate("w1", "e1", {"a": 1})
        adapter = self.make_assurance(script={candidate.fingerprint: {"verdict": "accepted"}})
        first = adapter.request(candidate=candidate, requirements={}, idempotency_key="k1")
        second = adapter.request(candidate=candidate, requirements={}, idempotency_key="k1")
        self.assertEqual(first.id, second.id)

    # -- inspect distinguishes running from terminal settlement. --

    def test_inspect_distinguishes_running_from_settled(self) -> None:
        candidate = _candidate("w1", "e1", {"a": 1})
        adapter = self.make_assurance(
            script={candidate.fingerprint: {"verdict": "accepted", "states": ["running", "settled"]}}
        )
        run = adapter.request(candidate=candidate, requirements={}, idempotency_key="k1")
        first = adapter.inspect(assurance_id=run.id)
        self.assertNotEqual(first.state, LIFECYCLE_STATE_SETTLED)
        self.assertIsNone(first.verdict)
        second = adapter.inspect(assurance_id=run.id)
        self.assertEqual(second.state, LIFECYCLE_STATE_SETTLED)
        self.assertEqual(second.verdict, "accepted")

    # -- Adapter-boundary lossless transport (CONF-EXT-001/CONF-EXT-003):
    # -- scripted extensions read back unchanged via inspect, unknown keys preserved. --

    def test_inspect_transports_scripted_extensions_losslessly(self) -> None:
        candidate = _candidate("w1", "e1", {"a": 1})
        extensions = {
            "review-findings/v1": {"findings": [{"severity": "note", "summary": "ok"}]},
            "some-unregistered-extension/v9": {"nested": {"a": [1, {"b": None}], "flag": True}},
        }
        adapter = self.make_assurance(
            script={
                candidate.fingerprint: {
                    "verdict": "accepted",
                    "evidence_refs": ["report-1"],
                    "extensions": extensions,
                }
            }
        )
        run = adapter.request(candidate=candidate, requirements={}, idempotency_key="k1")
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(dict(observed.extensions), extensions)
        # unknown extension identifiers are preserved verbatim, and the
        # portable to_dict shape round-trips them unchanged too.
        self.assertIn("some-unregistered-extension/v9", observed.extensions)
        self.assertEqual(observed.to_dict()["extensions"], extensions)

    # -- Capability honesty. --

    def test_capability_honesty_candidate_bound_advertised_and_exercised(self) -> None:
        candidate = _candidate("w1", "e1", {"a": 1})
        adapter = self.make_assurance(script={candidate.fingerprint: {"verdict": "accepted"}})
        self.assertTrue(adapter.supports(CAP_ASSURE_CANDIDATE_BOUND))
        run = adapter.request(candidate=candidate, requirements={}, idempotency_key="k1")
        observed = adapter.inspect(assurance_id=run.id)
        # candidate-bound: the settled observation names exactly the
        # candidate this run was requested against.
        self.assertEqual(observed.candidate_fingerprint, candidate.fingerprint)

    def test_capability_honesty_does_not_advertise_may_mutate_candidate(self) -> None:
        adapter = self.make_assurance(script={})
        self.assertFalse(adapter.supports(CAP_ASSURE_MAY_MUTATE_CANDIDATE))


class ScriptedAssuranceConformanceTest(AssurancePortConformance, unittest.TestCase):
    def make_assurance(
        self,
        *,
        script: Mapping[str, Mapping[str, Any]],
        capabilities: Optional[Iterable[str]] = None,
    ) -> AssurancePort:
        if capabilities is None:
            return ScriptedAssurance(script=script)
        return ScriptedAssurance(script=script, capabilities=capabilities)


class Conf003ForeignFingerprintRejectedByKernelTest(unittest.TestCase):
    """CONF-ASSURE-003, exercised through `orc_werk.core.reducer` per the
    task card: the adapter's role ends at faithfully reporting fingerprints;
    the kernel reducer is what actually rejects evidence transplanted from a
    different candidate (INV-008/INV-010)."""

    def test_evidence_from_a_different_candidate_is_rejected_by_the_reducer(self) -> None:
        candidate_a = _candidate("w1", "e1", {"content": "version-a"})
        candidate_b = _candidate("w1", "e2", {"content": "version-b"})
        self.assertNotEqual(candidate_a.fingerprint, candidate_b.fingerprint)

        assurance = ScriptedAssurance(
            script={
                candidate_a.fingerprint: {"verdict": "accepted"},
                candidate_b.fingerprint: {"verdict": "accepted"},
            }
        )
        run_a = assurance.request(candidate=candidate_a, requirements={}, idempotency_key="k-a")
        run_b = assurance.request(candidate=candidate_b, requirements={}, idempotency_key="k-b")
        observed_a = assurance.inspect(assurance_id=run_a.id)
        observed_b = assurance.inspect(assurance_id=run_b.id)

        # Projection is currently ASSURING candidate_a.
        facts = fixtures.assuring(
            delivery_run_id=DRID,
            work_id="w1",
            execution_id="e1",
            candidate_id=candidate_a.id,
            fingerprint=candidate_a.fingerprint,
            assurance_id=run_a.id,
        )

        # Fold in evidence carrying candidate_b's (adapter-reported)
        # fingerprint against the run currently bound to candidate_a --
        # foreign evidence must never satisfy candidate_a's assurance.
        foreign = make_fact(
            FACT_ASSURE_SETTLED,
            delivery_run_id=DRID,
            work_id="w1",
            assurance_id=run_a.id,
            candidate_fingerprint=observed_b.candidate_fingerprint,
            verdict=observed_b.verdict,
        )
        with self.assertRaises(CoreError) as ctx:
            reduce(facts + [foreign], delivery_run_id=DRID)
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-CONFLICT")

        # Sanity check: candidate_a's own (matching) evidence is legal --
        # proves the rejection above is about the foreign fingerprint, not
        # some unrelated defect.
        own = make_fact(
            FACT_ASSURE_SETTLED,
            delivery_run_id=DRID,
            work_id="w1",
            assurance_id=run_a.id,
            candidate_fingerprint=observed_a.candidate_fingerprint,
            verdict=observed_a.verdict,
        )
        reduce(facts + [own], delivery_run_id=DRID)  # does not raise


if __name__ == "__main__":
    unittest.main()
