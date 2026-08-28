"""Shared envelope-append/replay helpers for `JournalPort` adapters.

`MemoryJournal` (`orc_werk.adapters.memory.journal`) and `JSONLJournal`
(`orc_werk.adapters.jsonl.journal`) both build the same canonical
`PORT-JOURNAL-ENVELOPE` shape via `orc_werk.core.serialization`; this module
centralizes the pieces of *adapter* mechanics that are not core's job and
must nonetheless be identical across every `JournalPort` implementation for
`CONF-JOURNAL-*` to hold: how a settled effect's dispatch result gets
merged into the persisted envelope (`build_effect_envelope`), and how
`load_projection` recovers the run's own effective retry budget from
history before folding it (`effective_max_attempts`, issue #52).

`orc_werk.core.serialization.effect_to_envelope` deliberately does not
invent the dispatch-result placement -- its docstring says a caller
appending a settled effect record "may add [dispatch outcome] to the
returned `data` dict before persisting" -- because `Effect` (core) only
carries the *requested* effect identity/payload (`PORT-JOURNAL-003`).
`PORT-JOURNAL-003` names the required content ("dispatch result, and
canonical error/result") but does not prescribe its exact key/shape inside
`data`; this module picks the least-committal placement (a single
`dispatch_result` field carrying whatever portable mapping the caller
supplies) so both adapters agree. See the PR body's "Ambiguities
encountered" for why this is a stopgap rather than a normative shape.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from orc_werk.core.effects import FX_CREATE_WORK, Effect
from orc_werk.core.errors import validation_error
from orc_werk.core.portable import to_portable
from orc_werk.core.reducer import DEFAULT_MAX_ATTEMPTS
from orc_werk.core.serialization import KIND_EFFECT, effect_to_envelope

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


def effective_max_attempts(history: Sequence[Mapping[str, Any]]) -> int:
    """`PORT-JOURNAL-005`/`CONF-JOURNAL-003` (issue #52): the retry budget
    `load_projection` must fold this run's Facts under -- the run's own
    recorded `data.max_attempts` from its `FX-CREATE-WORK` effect record
    (`CONTRACT-DURABILITY`'s topology/budget row), journaled by
    `Orchestrator.bootstrap` alongside `data.plan` and read back the same
    way `Orchestrator._replay_effect_record` already reads `data.plan`
    back (the ratified topology-durability precedent, issue #41).

    A journal written before this field existed carries a `FX-CREATE-WORK`
    record with `data.plan` but no `data.max_attempts` -- this is a
    documented read-fallback (issue #55 layout fallback precedent), not an
    error: such a run folds under the reducer's own schema default
    (`DEFAULT_MAX_ATTEMPTS`), exactly as if it had used that default. A
    run with no `FX-CREATE-WORK` record at all (an empty/not-yet-bootstrapped
    journal) also falls back to the schema default -- there is nothing to
    read yet."""
    for record in history:
        if record.get("kind") != KIND_EFFECT:
            continue
        if record.get("id") != FX_CREATE_WORK:
            continue
        data = record.get("data") or {}
        recorded = data.get("max_attempts")
        if isinstance(recorded, int) and not isinstance(recorded, bool) and recorded > 0:
            return recorded
        return DEFAULT_MAX_ATTEMPTS
    return DEFAULT_MAX_ATTEMPTS


def deep_copy_portable(value: Any) -> Any:
    """Defensive copy so a record returned from `append_*`/`history()`
    cannot be mutated via the caller's reference to affect the journal's
    own store (`CONF-JOURNAL-002`: history is immutable/append-preserving).
    Portable envelopes are plain JSON-compatible data, so a stdlib
    `copy.deepcopy` is sufficient -- no custom object graph to worry
    about."""
    return copy.deepcopy(value)


__all__ = [
    "DISPATCH_RESULT_KEY",
    "build_effect_envelope",
    "deep_copy_portable",
    "effective_max_attempts",
]
