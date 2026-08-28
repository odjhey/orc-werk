"""Shared envelope-append helpers for `JournalPort` adapters.

`MemoryJournal` (`orc_werk.adapters.memory.journal`) and `JSONLJournal`
(`orc_werk.adapters.jsonl.journal`) both build the same canonical
`PORT-JOURNAL-ENVELOPE` shape via `orc_werk.core.serialization`; this module
only centralizes the one piece of *adapter* mechanics that is not core's
job and must nonetheless be identical across every `JournalPort`
implementation for `CONF-JOURNAL-*` to hold: how a settled effect's
dispatch result gets merged into the persisted envelope.

`orc_werk.core.serialization.effect_to_envelope` deliberately does not
invent this -- its docstring says a caller appending a settled effect
record "may add [dispatch outcome] to the returned `data` dict before
persisting" -- because `Effect` (core) only carries the *requested* effect
identity/payload (`PORT-JOURNAL-003`). `PORT-JOURNAL-003` names the
required content ("dispatch result, and canonical error/result") but does
not prescribe its exact key/shape inside `data`; this module picks the
least-committal placement (a single `dispatch_result` field carrying
whatever portable mapping the caller supplies) so both adapters agree. See
the PR body's "Ambiguities encountered" for why this is a stopgap rather
than a normative shape.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from orc_werk.core.effects import Effect
from orc_werk.core.errors import validation_error
from orc_werk.core.portable import to_portable
from orc_werk.core.serialization import effect_to_envelope

DISPATCH_RESULT_KEY = "dispatch_result"


def build_effect_envelope(
    effect: Effect, *, seq: int, dispatch_result: Mapping[str, Any]
) -> dict[str, Any]:
    """`PORT-JOURNAL-003`: build the settled-effect-record envelope --
    `effect_to_envelope` (core) plus the dispatch result merged into
    `data` under `dispatch_result`. Raises the same canonical
    `ERR-VALIDATION` `effect_to_envelope` already raises for the
    core-reserved keys (`work_id`/`idempotency_key`), extended to also
    reject an `effect.data` that already shadows `dispatch_result`."""
    envelope = effect_to_envelope(effect, seq=seq)
    if DISPATCH_RESULT_KEY in envelope["data"]:
        raise validation_error(
            f"{effect.id} data uses reserved envelope key(s): ['{DISPATCH_RESULT_KEY}']",
            record_id=effect.id,
            reserved_keys=[DISPATCH_RESULT_KEY],
        )
    envelope["data"] = {
        **envelope["data"],
        DISPATCH_RESULT_KEY: to_portable(dict(dispatch_result)),
    }
    return envelope


def deep_copy_portable(value: Any) -> Any:
    """Defensive copy so a record returned from `append_*`/`history()`
    cannot be mutated via the caller's reference to affect the journal's
    own store (`CONF-JOURNAL-002`: history is immutable/append-preserving).
    Portable envelopes are plain JSON-compatible data, so a stdlib
    `copy.deepcopy` is sufficient -- no custom object graph to worry
    about."""
    return copy.deepcopy(value)


__all__ = ["DISPATCH_RESULT_KEY", "build_effect_envelope", "deep_copy_portable"]
