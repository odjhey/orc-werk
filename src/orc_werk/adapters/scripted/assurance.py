"""ScriptedAssurance (`TASK-M0-003`): deterministic, candidate-bound
`AssurancePort` test double.

Settled verdicts are snapshotted the first time `inspect()` observes
`settled` and never re-derived afterward, so a rejected run can never later
read back as accepted even if a test subsequently mutates the underlying
script mapping (`CONF-ASSURE-002` immutability). `inspect()` always reports
the `candidate_fingerprint` the run was actually `request()`-ed against --
bound once at request time -- never whatever a caller currently considers
"current" (`INV-007`/`INV-008`).

M0 note (`docs/contracts/ports/assurance-port.md`): this adapter does not
advertise `CAP-ASSURE-MAY-MUTATE-CANDIDATE`; the constructor raises if a
caller tries to.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping, Sequence, Union

from orc_werk.core.errors import not_found_error, validation_error
from orc_werk.core.facts import ASSURANCE_VERDICTS
from orc_werk.core.models import AssuranceRun, Candidate
from orc_werk.core.portable import is_portable
from orc_werk.ports.assurance import AssuranceObservation, AssurancePort
from orc_werk.ports.base import LIFECYCLE_STATE_RUNNING, LIFECYCLE_STATE_SETTLED
from orc_werk.ports.capabilities import (
    CAP_ASSURE_CANDIDATE_BOUND,
    CAP_ASSURE_MAY_MUTATE_CANDIDATE,
    validate_capabilities,
)

_DEFAULT_CAPABILITIES = frozenset({CAP_ASSURE_CANDIDATE_BOUND})


def _entry_list(value: Any) -> list[dict[str, Any]]:
    """Normalize one fingerprint's script value to a list of entries.

    A bare mapping (the pre-`ADR-0006` shape every existing caller writes)
    becomes a one-element list, so a script with exactly one assurance per
    candidate behaves byte-identically to before. A list/tuple is copied
    entry-by-entry. Anything else is a caller bug, rejected here rather
    than misread later."""
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, (list, tuple)):
        entries = []
        for item in value:
            if not isinstance(item, Mapping):
                raise ValueError(
                    "ScriptedAssurance script entries must be JSON objects "
                    f"(got {type(item).__name__} inside a per-fingerprint list)"
                )
            entries.append(dict(item))
        return entries
    raise ValueError(
        "ScriptedAssurance script values must be a JSON object or a list of them "
        f"(got {type(value).__name__})"
    )


def _digest(*parts: str) -> str:
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


class ScriptedAssurance(AssurancePort):
    """Script format (portable data), keyed by candidate fingerprint:

    ```python
    script = {
      "<candidate_fingerprint>": {
        "verdict": "accepted",              # accepted | rejected | inconclusive
        "states": ["running", "settled"],   # optional; default ["settled"]
        "evidence_refs": [...],             # optional, portable
        "extensions": {...},                # optional, portable
      },
      # INV-021/ADR-0006: a fingerprint may instead map to a LIST of such
      # entries, consumed in request order -- element 0 is the candidate's
      # first assurance within an execution attempt, element 1 the bounded
      # re-request after an `inconclusive` settlement, and so on. A single
      # mapping is exactly equivalent to a one-element list.
      "<other_fingerprint>": [{"verdict": "inconclusive"}, {"verdict": "accepted"}],
    }
    ```

    A `request()` for a candidate whose fingerprint is absent from the
    script raises the canonical `ERR-NOT-FOUND` -- there is nothing scripted
    for this deterministic double to evaluate. So does a request past the
    end of a fingerprint's entry list (`pending=False`); under
    `pending=True` both are the ordinary `SCN-007` pending wait instead.

    Which entry a run binds to is decided at `request()` time from the
    number of DISTINCT idempotency keys already requested for that
    fingerprint -- and `request()` is idempotent on the key, so a fresh
    process replaying the journal's `FX-START-ASSURANCE` records in `seq`
    order re-derives exactly the same binding (`INV-020`: never
    process-local memory as the authority, always a deterministic function
    of durable replay order).

    `pending` (`TASK-M1-002`, `SCN-007`): when `False` (the default --
    unchanged M0 "strict" behavior relied on by `tests/conformance` and the
    dogfood corpus), a `request()` for an unscripted candidate fingerprint
    raises `ERR-NOT-FOUND` immediately, as it always has. When `True` (the
    CLI-wired M1a default), the same `request()` succeeds instead -- the
    caller journals `FACT-ASSURE-STARTED` exactly as it would for a
    scripted verdict -- and `inspect()` reports `state=running` until a
    later-constructed instance (re-dispatch over an updated config
    recording the verdict) observes the same `assurance_id` with a script
    entry present. Mirrors `ScriptedExecution`'s `pending` flag for the
    ASSURING boundary (`STATE-DELIVERY` mechanical fact sequencing item 7).
    """

    def __init__(
        self,
        *,
        script: Mapping[str, Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]],
        capabilities: Iterable[str] = _DEFAULT_CAPABILITIES,
        pending: bool = False,
    ) -> None:
        normalized = {key: _entry_list(val) for key, val in script.items()}
        if not is_portable(normalized):
            raise ValueError("ScriptedAssurance script must be portable/JSON-compatible")
        caps = validate_capabilities(capabilities)
        if CAP_ASSURE_MAY_MUTATE_CANDIDATE in caps:
            # assurance-port.md M0 note: scripted adapters never advertise this.
            raise ValueError(
                "ScriptedAssurance must not advertise CAP-ASSURE-MAY-MUTATE-CANDIDATE (M0 note)"
            )
        self._capabilities = caps
        self._pending = pending
        # Every fingerprint holds a LIST of entries (a bare mapping is
        # normalized to a one-element list), consumed in request order --
        # INV-021's bounded re-request needs more than one settlement per
        # candidate within one execution attempt.
        self._script: dict[str, list[dict[str, Any]]] = normalized

        self._by_idempotency_key: dict[str, AssuranceRun] = {}
        self._fingerprint_by_run: dict[str, str] = {}
        # (fingerprint, index) each run is bound to; the entry itself stays
        # resolved lazily at inspect() time, exactly as before, so
        # CONF-ASSURE-002's snapshot-on-settle immutability rule is the one
        # and only place a verdict is frozen.
        self._slot_by_run: dict[str, int] = {}
        self._requests_by_fingerprint: dict[str, int] = {}
        self._pending_runs: set[str] = set()
        self._inspect_calls: dict[str, int] = {}
        self._settled_snapshot: dict[str, AssuranceObservation] = {}

    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    def request(
        self,
        *,
        candidate: Candidate,
        requirements: Mapping[str, Any],
        idempotency_key: str,
    ) -> AssuranceRun:
        if idempotency_key in self._by_idempotency_key:
            # PORT-ASSURE-001: request is idempotent on idempotency_key.
            return self._by_idempotency_key[idempotency_key]

        # INV-021: the slot this new run binds to is the count of distinct
        # keys already requested for this fingerprint (0-based), i.e. its
        # `assurance_number - 1`. Counted here, on the request path only,
        # so replaying the journal's FX-START-ASSURANCE records rebuilds
        # the identical binding.
        slot = self._requests_by_fingerprint.get(candidate.fingerprint, 0)
        entries = self._script.get(candidate.fingerprint)

        if entries is None or slot >= len(entries):
            if not self._pending:
                raise not_found_error(
                    "ScriptedAssurance has no scripted verdict for this candidate fingerprint",
                    candidate_fingerprint=candidate.fingerprint,
                    assurance_number=slot + 1,
                )
            # TASK-M1-002/SCN-007 pending-capable mode: a requested
            # assurance run with no recorded verdict yet is PENDING, not a
            # failure -- it still "requests" successfully so the caller
            # journals FACT-ASSURE-STARTED; inspect() below reports
            # state=running until a later instance observes a verdict.
            assurance_id = f"assure-{_digest(idempotency_key)}"
            run = AssuranceRun(id=assurance_id, candidate_id=candidate.id)
            self._by_idempotency_key[idempotency_key] = run
            self._fingerprint_by_run[assurance_id] = candidate.fingerprint
            self._slot_by_run[assurance_id] = slot
            self._requests_by_fingerprint[candidate.fingerprint] = slot + 1
            self._pending_runs.add(assurance_id)
            self._inspect_calls[assurance_id] = 0
            return run

        assurance_id = f"assure-{_digest(idempotency_key)}"
        run = AssuranceRun(id=assurance_id, candidate_id=candidate.id)

        self._by_idempotency_key[idempotency_key] = run
        self._slot_by_run[assurance_id] = slot
        self._requests_by_fingerprint[candidate.fingerprint] = slot + 1
        # Candidate-bound: fixed at request time to the exact candidate this
        # run evaluates (INV-007) -- never re-derived from whatever is
        # "current" later (that is exactly the evidence-transfer INV-008
        # violation the kernel reducer guards against).
        self._fingerprint_by_run[assurance_id] = candidate.fingerprint
        self._inspect_calls[assurance_id] = 0
        return run

    def inspect(self, *, assurance_id: str) -> AssuranceObservation:
        if assurance_id in self._settled_snapshot:
            # CONF-ASSURE-002: a settled verdict is immutable -- never
            # re-derived from the (possibly since-mutated) script mapping.
            return self._settled_snapshot[assurance_id]

        if assurance_id in self._pending_runs:
            # SCN-007: no verdict observed yet -- MUST NOT be reported as
            # settled (mechanical fact sequencing item 7).
            return AssuranceObservation(state=LIFECYCLE_STATE_RUNNING)

        fingerprint = self._fingerprint_by_run.get(assurance_id)
        if fingerprint is None:
            raise not_found_error("unknown assurance_id", assurance_id=assurance_id)

        entry = self._script[fingerprint][self._slot_by_run[assurance_id]]
        states = list(entry.get("states", [LIFECYCLE_STATE_SETTLED]))
        call_index = self._inspect_calls[assurance_id]
        self._inspect_calls[assurance_id] = call_index + 1
        state = states[min(call_index, len(states) - 1)]

        if state != LIFECYCLE_STATE_SETTLED:
            return AssuranceObservation(state=state)

        verdict = entry.get("verdict")
        if verdict not in ASSURANCE_VERDICTS:
            raise validation_error(
                "ScriptedAssurance entry missing a valid verdict",
                candidate_fingerprint=fingerprint,
                verdict=verdict,
            )
        observation = AssuranceObservation(
            state=LIFECYCLE_STATE_SETTLED,
            verdict=verdict,
            # CONF-ASSURE-001: settled evidence names the exact candidate
            # fingerprint this run was bound to at request time.
            candidate_fingerprint=fingerprint,
            evidence_refs=tuple(entry.get("evidence_refs", (f"evidence-for-{fingerprint}",))),
            extensions=dict(entry.get("extensions", {})),
        )
        self._settled_snapshot[assurance_id] = observation
        return observation


__all__ = ["ScriptedAssurance"]
