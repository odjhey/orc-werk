"""`MemoryJournal`: dependency-free in-memory `JournalPort` (`PORT-JOURNAL`)
implementation.

Records live only in process memory (`dict[delivery_run_id, list[envelope]]`)
-- there is no disk persistence, so a process restart loses history; use
`orc_werk.adapters.jsonl.journal.JSONLJournal` when durability across
restarts is required. `MemoryJournal` exists for tests/scenarios and as the
`CONF-JOURNAL-*` reference behavior every other `JournalPort` adapter
(including `JSONLJournal`) must match.

`seq` is assigned per `delivery_run_id`, starting at 1, in append order
(`PORT-JOURNAL-ENVELOPE`); `load_projection` folds the run's `FACT-*`
records (only) through `orc_werk.core.reducer.reduce` (`PORT-JOURNAL-005`),
under the run's own recorded retry budget (`FX-CREATE-WORK`'s effect
`data.max_attempts`, issue #52, `orc_werk.adapters.journal_support.
effective_max_attempts`) rather than the reducer's schema default.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from orc_werk.adapters.journal_support import (
    build_effect_envelope,
    deep_copy_portable,
    effective_max_assurance_attempts,
    effective_max_attempts,
)
from orc_werk.core.decisions import Decision
from orc_werk.core.effects import Effect
from orc_werk.core.facts import Fact
from orc_werk.core.reducer import reduce
from orc_werk.core.serialization import (
    KIND_FACT,
    decision_to_envelope,
    fact_from_envelope,
    fact_to_envelope,
)
from orc_werk.core.state import DeliveryProjection
from orc_werk.ports.journal import JournalPort


class MemoryJournal(JournalPort):
    def __init__(self) -> None:
        self._records: Dict[str, List[Dict[str, Any]]] = {}

    def capabilities(self) -> frozenset[str]:
        return frozenset()

    # -- internal helpers --------------------------------------------------

    def _next_seq(self, delivery_run_id: str) -> int:
        # PORT-JOURNAL-ENVELOPE: seq starts at 1 and increases monotonically
        # per delivery_run_id, in append order.
        return len(self._records.get(delivery_run_id, ())) + 1

    def _append(self, delivery_run_id: str, envelope: Mapping[str, Any]) -> Mapping[str, Any]:
        # Store (and return) defensive copies so neither a caller mutating a
        # prior return value, nor a caller mutating history(), can reach
        # back into the journal's own store (CONF-JOURNAL-002).
        stored = deep_copy_portable(dict(envelope))
        self._records.setdefault(delivery_run_id, []).append(stored)
        return deep_copy_portable(stored)

    # -- PORT-JOURNAL --------------------------------------------------------

    def append_fact(self, fact: Fact) -> Mapping[str, Any]:
        envelope = fact_to_envelope(fact, seq=self._next_seq(fact.delivery_run_id))
        return self._append(fact.delivery_run_id, envelope)

    def append_decision(self, decision: Decision) -> Mapping[str, Any]:
        envelope = decision_to_envelope(decision, seq=self._next_seq(decision.delivery_run_id))
        return self._append(decision.delivery_run_id, envelope)

    def append_effect_record(
        self, effect: Effect, *, dispatch_result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        envelope = build_effect_envelope(
            effect, seq=self._next_seq(effect.delivery_run_id), dispatch_result=dispatch_result
        )
        return self._append(effect.delivery_run_id, envelope)

    def history(self, *, delivery_run_id: str) -> Sequence[Mapping[str, Any]]:
        records = self._records.get(delivery_run_id, ())
        # already stored in append (== seq) order; sort defensively so the
        # ordering guarantee is explicit rather than incidental.
        ordered = sorted(records, key=lambda record: record["seq"])
        return tuple(deep_copy_portable(record) for record in ordered)

    def load_projection(self, *, delivery_run_id: str) -> DeliveryProjection:
        history = self.history(delivery_run_id=delivery_run_id)
        facts = [
            fact_from_envelope(record) for record in history if record["kind"] == KIND_FACT
        ]
        # issue #52: same effective-retry-budget fold as JSONLJournal --
        # both adapters must agree for CONF-JOURNAL-003.
        max_attempts = effective_max_attempts(history)
        # INV-021/ADR-0006: the same single-authority fold for the
        # assurance budget -- absent from a legacy journal means `1`.
        max_assurance_attempts = effective_max_assurance_attempts(history)
        return reduce(
            facts,
            delivery_run_id=delivery_run_id,
            max_attempts=max_attempts,
            max_assurance_attempts=max_assurance_attempts,
        )


__all__ = ["MemoryJournal"]
