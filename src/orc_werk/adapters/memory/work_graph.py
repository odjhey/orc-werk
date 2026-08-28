"""In-memory `WorkGraphPort` (`PORT-WORK-GRAPH`) adapter (`TASK-M0-002`).

Dependency-free reference implementation: stdlib + `orc_werk.core` +
`orc_werk.ports` only (`ARCH-REPOSITORY-STRUCTURE`). No provider
vocabulary, no randomness, no wall-clock reads -- `claim_ref` is derived
deterministically from `work_id` alone so replay (`PORT-JOURNAL-005`)
reproduces identical values (`INV-020`).

Design decisions (also recorded in the TASK-M0-002 PR body):

- One plan per DeliveryRun (`INV-020`'s note that v0 permits exactly one
  plan creation per DeliveryRun): a second `create` for the same
  `delivery_run_id` raises `ERR-CONFLICT` rather than replacing the plan.
- `ready` is authoritative per `INV-015`/`INV-016`: a Work is eligible
  only when it is not completed, not blocked, not already claimed, and
  every dependency's `condition` ("accepted", the only v0 condition) is
  satisfied by that dependency's committed `completed` state -- never by
  mere upstream Execution settlement (`SCN-005`).
- `claim` advertises `CAP-WORK-ATOMIC-CLAIM` and is atomic and
  fail-closed: it requires current eligibility per the exact criteria
  `ready()` uses, so claiming an already-claimed, completed, or blocked
  Work -- or one whose dependencies are not yet committed-complete --
  raises `ERR-CONFLICT` (an early claim can never poison a
  not-yet-unlocked Work).
- Claim semantics are once-per-lineage (watchtower ruling on the
  TASK-M0-002 review): the claim holder owns the Work across all retry
  attempts; `ready()` is the discovery surface for unclaimed eligible
  work; retries are driven by the holder from journal state, never by
  re-claiming. A second claim on the same Work is therefore always
  `ERR-CONFLICT`, and `claim_ref` is simply `f"claim:{work_id}"` --
  opaque, deterministic, replay-stable.
- `complete` is idempotent: completing an already-completed Work is a
  no-op that returns the same `Work` rather than raising (chosen over the
  "deterministically conflicting" alternative `CONF-WORK-003` also
  permits, to match this repo's general idempotent-effects design
  posture, CLAUDE.md #11). Completing a blocked Work raises
  `ERR-CONFLICT` (blocked is terminal per the delivery state machine's
  mechanical fact sequencing).
- `block` records `reason` verbatim (free-form per `PROTOCOL-FACTS`).
  Blocking an already-completed Work raises `ERR-CONFLICT` (accepted is
  terminal); re-blocking an already-blocked Work is idempotent and
  overwrites `reason` with the latest call, mirroring `complete`'s
  idempotency choice above.
- `claim`/`complete`/`block` take only `work_id` (matching the
  `WorkGraphPort` ABC signatures, which do not pass `delivery_run_id`).
  This adapter therefore assumes `work_id` values are unique across all
  DeliveryRuns tracked by one `MemoryWorkGraph` instance.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence

from orc_werk.core.errors import conflict_error, not_found_error
from orc_werk.core.models import Work
from orc_werk.ports.capabilities import CAP_WORK_ATOMIC_CLAIM, validate_capabilities
from orc_werk.ports.work_graph import DEPENDENCY_CONDITION_ACCEPTED, WorkGraphPort, validate_plan


class MemoryWorkGraph(WorkGraphPort):
    """In-memory `WorkGraphPort` reference adapter. State lives only in
    process memory; nothing here is durable across restarts (durability is
    the journal's job, `PORT-JOURNAL-*`, not this adapter's)."""

    def __init__(self) -> None:
        # delivery_run_id -> work_id -> mutable work-graph state.
        self._runs: dict[str, dict[str, MutableMapping[str, Any]]] = {}

    def capabilities(self) -> frozenset[str]:
        return validate_capabilities({CAP_WORK_ATOMIC_CLAIM})

    def create(self, *, delivery_run_id: str, plan: Mapping[str, Any]) -> Sequence[Work]:
        validate_plan(plan)
        if delivery_run_id in self._runs:
            raise conflict_error(
                f"a work-graph plan already exists for delivery_run_id: {delivery_run_id!r} "
                "(v0 permits exactly one plan creation per DeliveryRun)",
                delivery_run_id=delivery_run_id,
            )

        works_state: dict[str, MutableMapping[str, Any]] = {}
        for entry in plan["works"]:
            work_id = entry["work_id"]
            deps = [
                {"work_id": dep["work_id"], "condition": dep["condition"]}
                for dep in entry.get("deps", [])
            ]
            works_state[work_id] = {
                "deps": deps,
                "completed": False,
                "blocked_reason": None,
                "claimed": False,
            }

        self._runs[delivery_run_id] = works_state
        return tuple(
            Work(id=work_id, delivery_run_id=delivery_run_id) for work_id in works_state
        )

    def snapshot(self, *, delivery_run_id: str) -> Mapping[str, Any]:
        works_state = self._require_run(delivery_run_id)
        return {
            "works": [
                {
                    "work_id": work_id,
                    "deps": [dict(dep) for dep in state["deps"]],
                    "completed": state["completed"],
                    "blocked_reason": state["blocked_reason"],
                }
                for work_id, state in works_state.items()
            ]
        }

    def ready(self, *, delivery_run_id: str) -> Sequence[Work]:
        works_state = self._require_run(delivery_run_id)
        eligible = []
        for work_id, state in works_state.items():
            if state["completed"] or state["blocked_reason"] is not None or state["claimed"]:
                continue
            if self._deps_satisfied(works_state, state["deps"]):
                eligible.append(Work(id=work_id, delivery_run_id=delivery_run_id))
        return tuple(eligible)

    def claim(self, *, work_id: str) -> Mapping[str, Any]:
        self._require_capability(CAP_WORK_ATOMIC_CLAIM, operation="claim", work_id=work_id)
        state, delivery_run_id = self._find_work(work_id)

        if state["claimed"]:
            raise conflict_error(f"work is already claimed: {work_id!r}", work_id=work_id)
        if state["completed"]:
            raise conflict_error(f"cannot claim a completed work: {work_id!r}", work_id=work_id)
        if state["blocked_reason"] is not None:
            raise conflict_error(f"cannot claim a blocked work: {work_id!r}", work_id=work_id)
        # Fail-closed: claim requires current eligibility per the exact
        # criteria ready() uses (INV-015). A Work whose dependencies are
        # not yet committed-complete cannot be claimed early and poisoned.
        if not self._deps_satisfied(self._runs[delivery_run_id], state["deps"]):
            raise conflict_error(
                f"cannot claim a work whose dependencies are not committed-complete: {work_id!r}",
                work_id=work_id,
            )

        state["claimed"] = True
        # Once-per-lineage claim: one claim ever per Work, so the
        # deterministic opaque claim_ref needs no counter (INV-020:
        # replay-stable, no randomness/wall-clock).
        return {"work_id": work_id, "claim_ref": f"claim:{work_id}"}

    def complete(self, *, work_id: str) -> Work:
        state, delivery_run_id = self._find_work(work_id)

        if state["completed"]:
            # Idempotent duplicate completion (CONF-WORK-003; see module
            # docstring for the rationale over deterministic conflict).
            return Work(id=work_id, delivery_run_id=delivery_run_id)
        if state["blocked_reason"] is not None:
            raise conflict_error(
                f"cannot complete a blocked work: {work_id!r}", work_id=work_id
            )

        state["completed"] = True
        return Work(id=work_id, delivery_run_id=delivery_run_id)

    def block(self, *, work_id: str, reason: str) -> Work:
        state, delivery_run_id = self._find_work(work_id)

        if state["completed"]:
            raise conflict_error(
                f"cannot block a completed work: {work_id!r}", work_id=work_id
            )

        state["blocked_reason"] = reason
        return Work(id=work_id, delivery_run_id=delivery_run_id)

    def _deps_satisfied(
        self,
        works_state: Mapping[str, Mapping[str, Any]],
        deps: Sequence[Mapping[str, Any]],
    ) -> bool:
        for dep in deps:
            # DEPENDENCY_CONDITION_ACCEPTED is the only v0 condition
            # (PORT-WORK-001); validate_plan already rejects any other
            # value at create() time, so this is an authoritative-mapping
            # guard rather than a live branch in practice.
            if dep["condition"] != DEPENDENCY_CONDITION_ACCEPTED:
                return False
            dep_state = works_state.get(dep["work_id"])
            if dep_state is None or not dep_state["completed"]:
                return False
        return True

    def _require_run(self, delivery_run_id: str) -> dict[str, MutableMapping[str, Any]]:
        works_state = self._runs.get(delivery_run_id)
        if works_state is None:
            raise not_found_error(
                f"no work-graph plan exists for delivery_run_id: {delivery_run_id!r}",
                delivery_run_id=delivery_run_id,
            )
        return works_state

    def _find_work(self, work_id: str) -> tuple[MutableMapping[str, Any], str]:
        for delivery_run_id, works_state in self._runs.items():
            state = works_state.get(work_id)
            if state is not None:
                return state, delivery_run_id
        raise not_found_error(f"unknown work_id: {work_id!r}", work_id=work_id)


__all__ = ["MemoryWorkGraph"]
