"""Portable serialization to/from `PORT-JOURNAL-ENVELOPE`.

Every persisted/interchanged Fact, Decision, or Effect uses the canonical
envelope:

    {schema_version, seq, delivery_run_id, kind, id, data, extensions}

`seq` is assigned by the JournalPort on append (PORT-JOURNAL-ENVELOPE);
core never invents it. These functions accept/emit whatever `seq` the
caller supplies (e.g. `0` as a not-yet-assigned placeholder when serializing
for append, or the persisted value when deserializing history) -- core only
transports it.

Effect records: PORT-JOURNAL-003 additionally wants dispatch result and
canonical error/result once an effect has actually been attempted. Core's
`Effect` value type only carries the *requested* effect (identity +
idempotency key + payload) -- dispatch outcome is produced by the app/port
layer outside `orc_werk.core`, so `effect_to_envelope` does not invent those
fields; a caller appending a settled effect record may add them to the
returned `data` dict before persisting.
"""

from __future__ import annotations

from typing import Any, Mapping

from orc_werk.core.decisions import ALL_DECISION_IDS, Decision
from orc_werk.core.effects import ALL_EFFECT_IDS, Effect
from orc_werk.core.errors import validation_error
from orc_werk.core.facts import ALL_FACT_IDS, Fact
from orc_werk.core.portable import is_portable, to_portable

SCHEMA_VERSION = 1

KIND_FACT = "fact"
KIND_DECISION = "decision"
KIND_EFFECT = "effect"
ALL_KINDS = frozenset({KIND_FACT, KIND_DECISION, KIND_EFFECT})


def _envelope(
    *,
    schema_version: int,
    seq: int,
    delivery_run_id: str,
    kind: str,
    record_id: str,
    data: Mapping[str, Any],
    extensions: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "seq": seq,
        "delivery_run_id": delivery_run_id,
        "kind": kind,
        "id": record_id,
        "data": to_portable(dict(data)),
        "extensions": to_portable(dict(extensions)),
    }


def fact_to_envelope(fact: Fact, *, seq: int, schema_version: int = SCHEMA_VERSION) -> dict[str, Any]:
    return _envelope(
        schema_version=schema_version,
        seq=seq,
        delivery_run_id=fact.delivery_run_id,
        kind=KIND_FACT,
        record_id=fact.id,
        data=fact.data,
        extensions=fact.extensions,
    )


def fact_from_envelope(envelope: Mapping[str, Any]) -> Fact:
    _validate_envelope(envelope, expected_kind=KIND_FACT, valid_ids=ALL_FACT_IDS)
    return Fact(
        id=envelope["id"],
        delivery_run_id=envelope["delivery_run_id"],
        data=envelope["data"],
        extensions=envelope.get("extensions", {}),
    )


DECISION_RESERVED_DATA_KEYS = frozenset({"work_id", "attribution", "basis"})
EFFECT_RESERVED_DATA_KEYS = frozenset({"work_id", "idempotency_key"})


def _assert_disjoint_reserved_keys(
    data: Mapping[str, Any], *, reserved: frozenset[str], record_id: str
) -> None:
    clobbered = reserved & set(data)
    if clobbered:
        raise validation_error(
            f"{record_id} data uses reserved envelope key(s): {sorted(clobbered)}",
            record_id=record_id,
            reserved_keys=sorted(clobbered),
        )


def decision_to_envelope(
    decision: Decision, *, seq: int, schema_version: int = SCHEMA_VERSION
) -> dict[str, Any]:
    _assert_disjoint_reserved_keys(
        decision.data, reserved=DECISION_RESERVED_DATA_KEYS, record_id=decision.id
    )
    data = {
        "work_id": decision.work_id,
        "attribution": decision.attribution,
        "basis": list(decision.basis),
        **decision.data,
    }
    return _envelope(
        schema_version=schema_version,
        seq=seq,
        delivery_run_id=decision.delivery_run_id,
        kind=KIND_DECISION,
        record_id=decision.id,
        data=data,
        extensions=decision.extensions,
    )


def decision_from_envelope(envelope: Mapping[str, Any]) -> Decision:
    _validate_envelope(envelope, expected_kind=KIND_DECISION, valid_ids=ALL_DECISION_IDS)
    data = dict(envelope["data"])
    work_id = data.pop("work_id")
    attribution = data.pop("attribution")
    basis = tuple(dict(item) for item in data.pop("basis"))
    return Decision(
        id=envelope["id"],
        delivery_run_id=envelope["delivery_run_id"],
        work_id=work_id,
        attribution=attribution,
        basis=basis,
        data=data,
        extensions=envelope.get("extensions", {}),
    )


def effect_to_envelope(effect: Effect, *, seq: int, schema_version: int = SCHEMA_VERSION) -> dict[str, Any]:
    _assert_disjoint_reserved_keys(
        effect.data, reserved=EFFECT_RESERVED_DATA_KEYS, record_id=effect.id
    )
    data = {
        "work_id": effect.work_id,
        "idempotency_key": effect.idempotency_key,
        **effect.data,
    }
    return _envelope(
        schema_version=schema_version,
        seq=seq,
        delivery_run_id=effect.delivery_run_id,
        kind=KIND_EFFECT,
        record_id=effect.id,
        data=data,
        extensions=effect.extensions,
    )


def effect_from_envelope(envelope: Mapping[str, Any]) -> Effect:
    _validate_envelope(envelope, expected_kind=KIND_EFFECT, valid_ids=ALL_EFFECT_IDS)
    data = dict(envelope["data"])
    work_id = data.pop("work_id")
    idempotency_key = data.pop("idempotency_key")
    return Effect(
        id=envelope["id"],
        delivery_run_id=envelope["delivery_run_id"],
        work_id=work_id,
        idempotency_key=idempotency_key,
        data=data,
        extensions=envelope.get("extensions", {}),
    )


def to_envelope(record: Fact | Decision | Effect, *, seq: int, schema_version: int = SCHEMA_VERSION) -> dict[str, Any]:
    if isinstance(record, Fact):
        return fact_to_envelope(record, seq=seq, schema_version=schema_version)
    if isinstance(record, Decision):
        return decision_to_envelope(record, seq=seq, schema_version=schema_version)
    if isinstance(record, Effect):
        return effect_to_envelope(record, seq=seq, schema_version=schema_version)
    raise TypeError(f"not a canonical Fact/Decision/Effect: {record!r}")


def from_envelope(envelope: Mapping[str, Any]) -> Fact | Decision | Effect:
    kind = envelope.get("kind")
    if kind == KIND_FACT:
        return fact_from_envelope(envelope)
    if kind == KIND_DECISION:
        return decision_from_envelope(envelope)
    if kind == KIND_EFFECT:
        return effect_from_envelope(envelope)
    raise validation_error(f"unknown envelope kind: {kind!r}")


def _validate_envelope(envelope: Mapping[str, Any], *, expected_kind: str, valid_ids: frozenset[str]) -> None:
    required_keys = {"schema_version", "seq", "delivery_run_id", "kind", "id", "data"}
    missing = required_keys - set(envelope)
    if missing:
        raise validation_error(f"envelope missing required key(s): {sorted(missing)}")
    if envelope["kind"] != expected_kind:
        raise validation_error(
            f"envelope kind mismatch: expected {expected_kind!r}, got {envelope['kind']!r}"
        )
    if envelope["id"] not in valid_ids:
        raise validation_error(f"unknown {expected_kind} id: {envelope['id']!r}")
    if not isinstance(envelope["seq"], int):
        raise validation_error("envelope seq must be an int")
    if not is_portable(dict(envelope.get("extensions", {}))):
        raise validation_error("envelope extensions is not portable/JSON-compatible")
