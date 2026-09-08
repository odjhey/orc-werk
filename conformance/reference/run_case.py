#!/usr/bin/env python3
"""Reference driver for the portable conformance kit.

`CONFORMANCE-PORTABLE-KIT` (`docs/conformance/portable-kit.md`) is the
normative source; this file is the reference-implementation adapter it
describes, not the contract itself.

Wire contract (the entire language-neutral boundary):

  stdin  -- exactly one JSON object: `{"delivery_run_id": "...", "history":
            [envelope, ...]}`, where each `envelope` is a canonical
            `PORT-JOURNAL-ENVELOPE` record -- the exact on-disk shape a
            real `.orc/*/journal.jsonl` line has:
            `{schema_version, seq, delivery_run_id, kind, id, data,
            extensions}`, `kind` one of `"fact"`/`"decision"`/`"effect"`,
            ordered by `seq`. This is not a Python-internal shape and not
            a driver-specific convenience format -- it is the same
            envelope every real adapter (`adapters/jsonl/journal.py`,
            `adapters/memory/journal.py`) reads back.

  stdout -- exactly one JSON object: the observed-result envelope
            (`kit_version`, `outcome`, and either `projection`+`decisions`
            for `"ok"` or `error`+`failing_*` for `"error"`). The success
            shape is this kit's OWN normalized observation adapter over the
            domain's derived state -- it never serializes a Python
            dataclass verbatim; see `_normalize_projection`/
            `_normalize_decision` below and `docs/conformance/portable-
            kit.md`'s output-schema table for the field-by-field contract.

This driver performs the SAME operation `PORT-JOURNAL-005 load_projection`
performs on a real journal (`CONF-JOURNAL-003`'s replay-determinism
guarantee): it derives both run-scoped budgets from the history's own
`FX-CREATE-WORK` effect record (`orc_werk.core.reducer
.journaled_max_attempts` / `.journaled_max_assurance_attempts` --
including their documented legacy-fallback rule), then folds every `fact`
envelope, in `seq` order, under those derived budgets
(`orc_werk.core.reducer.apply_fact`) -- never a caller-supplied policy
override, exactly as `SCN-008`'s single-authority ruling (issue #240)
requires. `decide()` runs after the fold, per Work, to report the
currently-applicable next Decision/Effect(s) (or none).

Any other implementation that accepts the same stdin shape and emits the
same stdout shape may be substituted for this file via
`checker.py --driver-cmd`. This file exists to be read for its shape, not
its Python: no case, expectation, or comparison rule lives here.

This process is intentionally dependency-free beyond the stdlib and the
`orc_werk.core` package it drives -- no third-party package, no filesystem
side effect beyond reading stdin/writing stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

# Resolve the sibling `src/` tree by path so this driver runs from a bare
# checkout with no install step and no reliance on the caller's PYTHONPATH
# (though `PYTHONPATH=src python3 conformance/reference/run_case.py` also
# works unchanged, matching `scripts/check.sh`'s convention).
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from orc_werk.core.decisions import (  # noqa: E402
    DEC_ACCEPT,
    DEC_BLOCK,
    DEC_DISPATCH,
    DEC_REQUEST_ASSURANCE,
    DEC_RETRY,
    Decision,
)
from orc_werk.core.effects import (  # noqa: E402
    Effect,
    FX_BLOCK_WORK,
    FX_COMPLETE_WORK,
    FX_START_ASSURANCE,
    FX_START_EXECUTION,
)
from orc_werk.core.errors import CoreError, canonical_error  # noqa: E402
from orc_werk.core.errors import ERR_VALIDATION  # noqa: E402
from orc_werk.core.facts import FACT_INTENT_SUBMITTED  # noqa: E402
from orc_werk.core.policy import decide  # noqa: E402
from orc_werk.core.portable import to_portable  # noqa: E402
from orc_werk.core.reducer import (  # noqa: E402
    apply_fact,
    journaled_max_assurance_attempts,
    journaled_max_attempts,
)
from orc_werk.core.serialization import KIND_FACT, fact_from_envelope  # noqa: E402
from orc_werk.core.state import WorkProjection  # noqa: E402

KIT_VERSION = 1


def _normalize_projection(proj: WorkProjection) -> dict[str, Any]:
    """The kit's normalized per-Work observation (`docs/conformance/
    portable-kit.md`'s output-schema table is the field-by-field contract
    this function implements). It derives *observable* pending markers
    from the domain's raw historical lists rather than exposing the
    reducer's own retained-pointer fields verbatim -- `current_execution_id`
    /`current_assurance_id`/`assurance_started_for_current` are private
    reset quirks of the Python reducer's replay bookkeeping, not part of
    what a real adapter would ever need to observe."""
    executions = [
        {"execution_id": item["execution_id"], "outcome": item.get("outcome")}
        for item in proj.executions
    ]
    pending_execution_id = None
    if proj.current_execution_id is not None:
        for item in proj.executions:
            if item["execution_id"] == proj.current_execution_id and item.get("outcome") is None:
                pending_execution_id = proj.current_execution_id
                break

    assurances = [
        {
            "assurance_id": item["assurance_id"],
            "candidate_id": item["candidate_id"],
            "execution_id": item["execution_id"],
            # A raw "abandoned" entry is never a fourth canonical verdict:
            # it folds back to `verdict: null` plus a separate boolean.
            "verdict": None if item.get("verdict") in (None, "abandoned") else item["verdict"],
            "abandoned": item.get("verdict") == "abandoned",
        }
        for item in proj.assurances
    ]
    pending_assurance_id = None
    if proj.current_assurance_id is not None:
        for item in proj.assurances:
            if item["assurance_id"] == proj.current_assurance_id and item.get("verdict") is None:
                pending_assurance_id = proj.current_assurance_id
                break

    candidate_conflict = None
    if proj.candidate_conflict is not None:
        candidate_conflict = {
            "candidate_id": proj.candidate_conflict["candidate_id"],
            "reason": proj.candidate_conflict["reason"],
        }

    return to_portable(
        {
            "state": proj.state,
            "attempt_number": proj.attempt_number,
            "executions": executions,
            "candidates": {cid: dict(c) for cid, c in proj.candidates.items()},
            "current_candidate_id": proj.current_candidate_id,
            "assurances": assurances,
            "pending_execution_id": pending_execution_id,
            "pending_assurance_id": pending_assurance_id,
            "assurance_pending": pending_assurance_id is not None,
            "blocked_reason": proj.blocked_reason,
            "blocked_confirmed": proj.blocked_confirmed,
            "cancelled_reason": proj.cancelled_reason,
            "cancelled_confirmed": proj.cancelled_confirmed,
            "candidate_conflict": candidate_conflict,
        }
    )


def _idempotency_scope(
    decision: Decision, effect: Effect, projection: WorkProjection
) -> list[Any]:
    """The kit-specific structured stand-in for `INV-020`'s idempotency
    key (`orc_werk.core.idempotency.idempotency_key`'s opaque `|`-joined
    string): `[delivery_run_id, work_id, execution_attempt_number,
    effect_id, candidate_fingerprint_or_null, assurance_number_or_null]`.
    `execution_attempt_number` is the exact attempt the effect targets --
    the *upcoming* attempt for `DEC-DISPATCH`/`DEC-RETRY`'s
    `FX-START-EXECUTION`, the Work's *current* attempt for every other
    decision. The fifth and sixth members mirror `idempotency_key`'s own
    `FX-START-ASSURANCE` branch (`orc_werk.core.idempotency`): both are
    `null` for every other effect; for `FX-START-ASSURANCE` the fifth is
    always the candidate's fingerprint and the sixth is `decide()`'s
    `assurance_number` when it is greater than `1`, else `null` (the
    first assurance of a Candidate keeps the pre-`INV-021` reduced key
    form verbatim, per `INV-020`/`ADR-0006`) -- so two starts of the same
    attempt against *different* candidate fingerprints never collide on
    the same scope even when their `assurance_number` also matches."""
    if decision.id in (DEC_DISPATCH, DEC_RETRY):
        attempt_number = decision.data["attempt_number"]
    else:
        attempt_number = projection.attempt_number
    if effect.id == FX_START_ASSURANCE:
        candidate_fingerprint = effect.data["candidate_fingerprint"]
        assurance_number = decision.data["assurance_number"]
        scoped_assurance_number = assurance_number if assurance_number > 1 else None
    else:
        candidate_fingerprint = None
        scoped_assurance_number = None
    return [
        decision.delivery_run_id,
        decision.work_id,
        attempt_number,
        effect.id,
        candidate_fingerprint,
        scoped_assurance_number,
    ]


# Bounded v0 observation profile (`docs/conformance/portable-kit.md`'s
# decision/effect data-shape tables): the exact, complete key set this
# driver emits per `id` -- never the raw `Decision.data`/`Effect.data`
# dict verbatim. This is a deliberately small, fully specified kit
# observation, not a claim that these are the only fields `decide()`'s
# domain data payload happens to carry (e.g. the retry/assurance budget
# arithmetic folded into `DEC-BLOCK.data` alongside `reason`); a real
# adapter needing that arithmetic already has it from `projection` and
# `idempotency_scope` and MUST NOT rely on undocumented decision/effect
# keys leaking through here. There is no ID outside these two tables in
# this bounded profile -- `docs/protocol/decisions.md`/`effects.md` name
# the full protocol-wide ID vocabulary, of which this profile only ever
# observes the five decision IDs and four effect IDs `decide()` itself
# can emit.
_DECISION_DATA_FIELDS: dict[str, tuple[str, ...]] = {
    DEC_DISPATCH: (),
    DEC_RETRY: (),
    DEC_REQUEST_ASSURANCE: ("candidate_id", "assurance_number", "max_assurance_attempts"),
    DEC_ACCEPT: (),
    DEC_BLOCK: ("reason",),
}
_EFFECT_DATA_FIELDS: dict[str, tuple[str, ...]] = {
    FX_START_EXECUTION: (),
    FX_START_ASSURANCE: ("candidate_id", "candidate_fingerprint", "assurance_number"),
    FX_COMPLETE_WORK: (),
    FX_BLOCK_WORK: ("reason",),
}


def _whitelisted_data(data: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return to_portable({field: data[field] for field in fields})


def _normalize_decision(decision: Decision, effects: tuple[Effect, ...], projection: WorkProjection) -> dict[str, Any]:
    return {
        "decision": {
            "id": decision.id,
            "data": _whitelisted_data(decision.data, _DECISION_DATA_FIELDS[decision.id]),
        },
        "effects": [
            {
                "id": effect.id,
                "data": _whitelisted_data(effect.data, _EFFECT_DATA_FIELDS[effect.id]),
                "idempotency_scope": _idempotency_scope(decision, effect, projection),
            }
            for effect in effects
        ],
    }


def _extract_fact_id(record: Mapping[str, Any]) -> Any:
    fact_id = record.get("id")
    return fact_id if isinstance(fact_id, str) else None


def _extract_work_id(record: Mapping[str, Any]) -> Any:
    """Phase-independent location extraction (`docs/conformance/portable-
    kit.md`): the raw envelope's `data.work_id` when that value is a
    string, `null` otherwise -- available even when the envelope failed to
    become a `Fact` object, so a decode/validation failure never hides a
    work id merely because construction never reached that point."""
    data = record.get("data")
    if isinstance(data, dict):
        work_id = data.get("work_id")
        if isinstance(work_id, str):
            return work_id
    return None


def run(case_input: dict[str, Any]) -> dict[str, Any]:
    # Transport-level failures with no associated raw fact envelope
    # (`docs/conformance/portable-kit.md`): a missing/non-string
    # `delivery_run_id`, `history` itself not being a JSON array, or one
    # of its entries not being a JSON object, all happen before any fact
    # could be identified -- all three location fields report `null`,
    # never a fabricated index/id/work_id.
    delivery_run_id = case_input.get("delivery_run_id")
    if not isinstance(delivery_run_id, str):
        return _error_result(
            ValueError("'delivery_run_id' must be a JSON string"),
            fact_index=None,
            fact_id=None,
            work_id=None,
        )
    history = case_input.get("history", [])
    if not isinstance(history, list):
        return _error_result(
            ValueError("'history' must be a JSON array of envelopes"),
            fact_index=None,
            fact_id=None,
            work_id=None,
        )
    for record in history:
        if not isinstance(record, dict):
            return _error_result(
                ValueError("every 'history' entry must be a JSON object"),
                fact_index=None,
                fact_id=None,
                work_id=None,
            )

    # Single-authority budget derivation (issue #240 R1, `SCN-008`,
    # `SCN-021`'s legacy-fallback amendment): read straight off the raw
    # history, never a field the caller supplies alongside it.
    max_attempts = journaled_max_attempts(history)
    max_assurance_attempts = journaled_max_assurance_attempts(history)

    works: dict[str, Any] = {}
    fact_index = -1

    for record in history:
        if record.get("kind") != KIND_FACT:
            continue
        fact_index += 1
        try:
            fact = fact_from_envelope(record)
        except (CoreError, ValueError) as exc:
            return _error_result(
                exc,
                fact_index=fact_index,
                fact_id=_extract_fact_id(record),
                work_id=_extract_work_id(record),
            )

        if fact.id == FACT_INTENT_SUBMITTED:
            continue

        work_id = fact.data.get("work_id")
        try:
            works[work_id] = apply_fact(
                works.get(work_id),
                fact,
                max_attempts=max_attempts,
                max_assurance_attempts=max_assurance_attempts,
            )
        except (CoreError, ValueError) as exc:
            return _error_result(
                exc, fact_index=fact_index, fact_id=fact.id, work_id=work_id
            )

    decisions: dict[str, Any] = {}
    for work_id, projection in works.items():
        outcome = decide(
            projection,
            max_attempts=max_attempts,
            max_assurance_attempts=max_assurance_attempts,
        )
        decisions[work_id] = (
            _normalize_decision(outcome.decision, outcome.effects, projection)
            if outcome is not None
            else None
        )

    return {
        "kit_version": KIT_VERSION,
        "outcome": "ok",
        "delivery_run_id": delivery_run_id,
        "derived_max_attempts": max_attempts,
        "derived_max_assurance_attempts": max_assurance_attempts,
        "projection": {work_id: _normalize_projection(proj) for work_id, proj in works.items()},
        "decisions": decisions,
    }


def _error_result(
    exc: Exception, *, fact_index: int | None, fact_id: Any, work_id: Any = None
) -> dict[str, Any]:
    """Every failure this driver can hit is a canonical error
    (`CONTRACT-ERRORS`): a plain `ValueError` (raised by this driver's own
    shape guards, or by `Fact.__post_init__`/`fact_from_envelope` for a
    malformed record -- unknown id, missing required field, non-portable
    data, or an invalid enum value such as a malformed assurance verdict)
    is normalized to `ERR-VALIDATION` rather than surfaced as an uncaught
    traceback; a `CoreError` already carries its own canonical error
    id/message. `fact_index`/`fact_id`/`work_id` are `None` exactly when
    the failure happened outside any identifiable fact envelope (`history`
    itself malformed, or one of its entries not a JSON object) -- there is
    no envelope position to report."""
    error = exc.to_canonical() if isinstance(exc, CoreError) else canonical_error(
        ERR_VALIDATION, str(exc)
    )
    return {
        "kit_version": KIT_VERSION,
        "outcome": "error",
        "failing_fact_index": fact_index,
        "failing_fact_id": fact_id,
        "failing_work_id": work_id,
        "error": error,
    }


def main() -> int:
    case_input = json.load(sys.stdin)
    result = run(case_input)
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
