"""PORT-JOURNAL-ENVELOPE round-trip tests: lossless (incl. unknown
extensions keys, EXT-005/CONF-EXT-003), and no Python class names/pickle
anywhere in canonical output (ARCH-REPOSITORY-STRUCTURE portability rules)."""

from __future__ import annotations

import json
import unittest

from orc_werk.core.decisions import DEC_DISPATCH, make_decision
from orc_werk.core.effects import FX_START_EXECUTION, make_effect
from orc_werk.core.facts import FACT_CANDIDATE_OBSERVED, make_fact
from orc_werk.core.portable import is_portable
from orc_werk.core.serialization import (
    decision_from_envelope,
    decision_to_envelope,
    effect_from_envelope,
    effect_to_envelope,
    fact_from_envelope,
    fact_to_envelope,
    from_envelope,
    to_envelope,
)

DRID = "dr-ser"


class EnvelopeShapeTest(unittest.TestCase):
    def test_fact_envelope_has_required_keys(self) -> None:
        fact = make_fact(FACT_CANDIDATE_OBSERVED, delivery_run_id=DRID, work_id="w1", candidate_id="c1", fingerprint="fp1", execution_id="e1")
        envelope = fact_to_envelope(fact, seq=7)
        self.assertEqual(envelope["schema_version"], 1)
        self.assertEqual(envelope["seq"], 7)
        self.assertEqual(envelope["delivery_run_id"], DRID)
        self.assertEqual(envelope["kind"], "fact")
        self.assertEqual(envelope["id"], FACT_CANDIDATE_OBSERVED)
        self.assertEqual(envelope["data"]["fingerprint"], "fp1")

    def test_seq_is_transported_not_invented(self) -> None:
        # core accepts/emits whatever seq the caller supplies; it never
        # invents a "real" sequence number (that is the JournalPort's job).
        fact = make_fact(FACT_CANDIDATE_OBSERVED, delivery_run_id=DRID, work_id="w1", candidate_id="c1", fingerprint="fp1", execution_id="e1")
        for seq in (0, 1, 42, 999):
            envelope = fact_to_envelope(fact, seq=seq)
            self.assertEqual(envelope["seq"], seq)
            round_tripped = fact_from_envelope(envelope)
            self.assertEqual(round_tripped, fact)


class RoundTripTest(unittest.TestCase):
    def test_fact_round_trip(self) -> None:
        fact = make_fact(
            FACT_CANDIDATE_OBSERVED,
            delivery_run_id=DRID,
            work_id="w1",
            candidate_id="c1",
            fingerprint="fp1",
            execution_id="e1",
        )
        envelope = fact_to_envelope(fact, seq=1)
        self.assertEqual(fact_from_envelope(envelope), fact)
        self.assertEqual(from_envelope(envelope), fact)

    def test_decision_round_trip(self) -> None:
        decision = make_decision(
            DEC_DISPATCH,
            delivery_run_id=DRID,
            work_id="w1",
            basis=[{"id": "FACT-WORK-READY", "delivery_run_id": DRID, "data": {"work_id": "w1"}, "extensions": {}}],
            data={"attempt_number": 1},
        )
        envelope = decision_to_envelope(decision, seq=2)
        self.assertEqual(decision_from_envelope(envelope), decision)
        self.assertEqual(from_envelope(envelope), decision)

    def test_effect_round_trip(self) -> None:
        effect = make_effect(
            FX_START_EXECUTION,
            delivery_run_id=DRID,
            work_id="w1",
            idempotency_key="dr-ser|w1|1|FX-START-EXECUTION",
            data={"attempt_number": 1},
        )
        envelope = effect_to_envelope(effect, seq=3)
        self.assertEqual(effect_from_envelope(envelope), effect)
        self.assertEqual(from_envelope(envelope), effect)

    def test_round_trip_preserves_unknown_extension_keys_losslessly(self) -> None:
        # EXT-005 / CONF-EXT-003: a component promising lossless round-trip
        # preserves extension identifiers/payloads unchanged, even ones it
        # does not understand.
        fact = make_fact(
            FACT_CANDIDATE_OBSERVED,
            delivery_run_id=DRID,
            work_id="w1",
            candidate_id="c1",
            fingerprint="fp1",
            execution_id="e1",
            extensions={
                "review-findings/v1": {"findings": [{"path": "a.py", "note": "unused import"}]},
                "some-unregistered-extension/v7": {"anything": [1, 2, {"nested": True, "n": None}]},
            },
        )
        envelope = fact_to_envelope(fact, seq=1)
        round_tripped = fact_from_envelope(envelope)
        self.assertEqual(round_tripped.extensions, fact.extensions)
        # bytewise/structurally identical after a JSON hop too.
        json_round_trip = json.loads(json.dumps(envelope))
        self.assertEqual(json_round_trip["extensions"], envelope["extensions"])


class PortabilityTest(unittest.TestCase):
    """No Python class names/pickle/exception objects anywhere in canonical output."""

    def test_envelopes_are_json_compatible_only(self) -> None:
        fact = make_fact(FACT_CANDIDATE_OBSERVED, delivery_run_id=DRID, work_id="w1", candidate_id="c1", fingerprint="fp1", execution_id="e1")
        decision = make_decision(
            DEC_DISPATCH,
            delivery_run_id=DRID,
            work_id="w1",
            basis=[fact.to_dict()],
        )
        effect = make_effect(
            FX_START_EXECUTION,
            delivery_run_id=DRID,
            work_id="w1",
            idempotency_key="k",
        )
        for record, seq in ((fact, 1), (decision, 2), (effect, 3)):
            envelope = to_envelope(record, seq=seq)
            self.assertTrue(is_portable(envelope), f"not portable: {envelope!r}")
            # round-trips through real JSON with no custom encoder/decoder.
            self.assertEqual(json.loads(json.dumps(envelope)), envelope)

    def test_envelope_contains_no_python_type_names(self) -> None:
        fact = make_fact(FACT_CANDIDATE_OBSERVED, delivery_run_id=DRID, work_id="w1", candidate_id="c1", fingerprint="fp1", execution_id="e1")
        envelope = fact_to_envelope(fact, seq=1)
        rendered = json.dumps(envelope)
        for forbidden in ("orc_werk.core", "<class", "object at 0x", "Traceback"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
