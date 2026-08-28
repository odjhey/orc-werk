"""JournalPort (`PORT-JOURNAL`): persist what the orchestration kernel
observed, decided, and attempted, independently from provider-native logs.
Not a general artifact store; does not duplicate provider-native transcripts.

Journal records use the canonical `PORT-JOURNAL-ENVELOPE` shape
(`{schema_version, seq, delivery_run_id, kind, id, data, extensions}`).
That envelope's (de)serialization already lives in `orc_werk.core.
serialization` (`fact_to_envelope`/`decision_to_envelope`/`effect_to_envelope`
and their `*_from_envelope` counterparts, plus `to_envelope`/`from_envelope`)
-- this is the "shared serialization foundation" the port operations below
build on; `JournalPort` implementations are expected to call those helpers
rather than reimplement the envelope shape. `seq` is assigned by the
JournalPort implementation on append -- append order is authoritative for
ordering, and callers never supply `seq` (`PORT-JOURNAL-ENVELOPE`).
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Mapping, Sequence

from orc_werk.core.decisions import Decision
from orc_werk.core.effects import Effect
from orc_werk.core.facts import Fact
from orc_werk.ports.base import Port


class JournalPort(Port):
    """`PORT-JOURNAL`: append_fact / append_decision / append_effect_record
    / history / load_projection."""

    @abstractmethod
    def append_fact(self, fact: Fact) -> Mapping[str, Any]:
        """`PORT-JOURNAL-001`. Append an immutable canonical Fact. Returns
        the persisted `PORT-JOURNAL-ENVELOPE` (with its assigned `seq`)."""
        raise NotImplementedError

    @abstractmethod
    def append_decision(self, decision: Decision) -> Mapping[str, Any]:
        """`PORT-JOURNAL-002`. Append an immutable Decision including its
        basis (`INV-012`). Returns the persisted envelope."""
        raise NotImplementedError

    @abstractmethod
    def append_effect_record(
        self, effect: Effect, *, dispatch_result: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """`PORT-JOURNAL-003`. Record requested effect identity, dispatch
        result, and canonical error/result. `dispatch_result` is an opaque
        portable mapping carrying whatever the dispatch actually produced
        (canonical error value or canonical result) -- `Effect` itself only
        carries the *requested* effect (identity + idempotency key +
        payload); the app/port layer supplies the settled outcome. Returns
        the persisted envelope."""
        raise NotImplementedError

    @abstractmethod
    def history(self, *, delivery_run_id: str) -> Sequence[Mapping[str, Any]]:
        """`PORT-JOURNAL-004`. Read ordered canonical history (by `seq`)
        for one DeliveryRun, as a sequence of `PORT-JOURNAL-ENVELOPE`
        mappings."""
        raise NotImplementedError

    @abstractmethod
    def load_projection(self, *, delivery_run_id: str) -> Any:
        """`PORT-JOURNAL-005`. Load/rebuild canonical state from history or
        an equivalent durable projection -- typically by replaying
        `history()` through `orc_werk.core.reducer.reduce`."""
        raise NotImplementedError


__all__ = ["JournalPort"]
