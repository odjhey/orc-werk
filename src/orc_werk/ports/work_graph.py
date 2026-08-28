"""WorkGraphPort (`PORT-WORK-GRAPH`): canonical work topology/readiness
interface. Exposes authoritative logical Work topology and dispatch
eligibility without exposing provider-specific work-tracker concepts.

Explicit non-semantics (`docs/contracts/ports/work-graph-port.md`): this
port never defines provider issue types, provider labels, provider
workflow-template vocabulary, branch/repository policy, or executor
selection (`INV-014`).
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Mapping, Sequence

from orc_werk.core.errors import validation_error
from orc_werk.core.models import Work
from orc_werk.ports.base import Port

# The only v0 dependency condition (PORT-WORK-001), consistent with the
# committed-completion unlock rule in INV-016.
DEPENDENCY_CONDITION_ACCEPTED = "accepted"
VALID_DEPENDENCY_CONDITIONS = frozenset({DEPENDENCY_CONDITION_ACCEPTED})


def validate_plan(plan: Mapping[str, Any]) -> None:
    """Validate a `PORT-WORK-001` plan shape, raising the exact
    `ERR-VALIDATION` cases the (amended) port doc enumerates:

    - a duplicate `work_id`;
    - a `deps` entry naming a work not present in the plan, or naming the
      work itself;
    - an empty `works` list;
    - a dependency cycle;
    - a `deps` entry whose `condition` is not `"accepted"` (the only v0
      condition).

    Structurally malformed plans (missing required keys, wrong types --
    e.g. a non-list `deps`, a non-mapping `works`/`deps` entry) are also
    rejected with `ERR-VALIDATION`; this function never lets a
    `KeyError`/`TypeError`/`AttributeError` escape.

    Pure/stdlib-only so every WorkGraphPort adapter (in-memory, real
    provider) shares one implementation of these rejection cases rather
    than reimplementing them. Does not mutate or return the plan; callers
    pass a validated plan through to `WorkGraphPort.create` unchanged.
    """
    if not isinstance(plan, Mapping):
        raise validation_error("work-graph plan must be a mapping", plan=_safe_repr(plan))

    works = plan.get("works")
    if not isinstance(works, list) or not works:
        raise validation_error(
            "work-graph plan must have a non-empty 'works' list", plan=_safe_repr(plan)
        )

    seen: set[str] = set()
    for entry in works:
        if not isinstance(entry, Mapping):
            raise validation_error(
                "work-graph plan 'works' entry must be a mapping", entry=_safe_repr(entry)
            )
        work_id = entry.get("work_id")
        if not isinstance(work_id, str) or not work_id:
            raise validation_error(
                "work-graph plan 'works' entry must have a non-empty string 'work_id'",
                entry=_safe_repr(entry),
            )
        if work_id in seen:
            raise validation_error(
                f"work-graph plan has a duplicate work_id: {work_id!r}", work_id=work_id
            )
        seen.add(work_id)

    for entry in works:
        work_id = entry["work_id"]
        deps = entry.get("deps", [])
        if not isinstance(deps, list):
            raise validation_error(
                f"work-graph plan 'deps' must be a list for work_id: {work_id!r}",
                work_id=work_id,
                deps=_safe_repr(deps),
            )
        for dep in deps:
            if not isinstance(dep, Mapping):
                raise validation_error(
                    f"work-graph plan dependency entry must be a mapping for work_id: {work_id!r}",
                    work_id=work_id,
                    dep=_safe_repr(dep),
                )
            dep_id = dep.get("work_id")
            if dep_id == work_id:
                raise validation_error(
                    f"work-graph plan dependency names the work itself: {work_id!r}",
                    work_id=work_id,
                )
            if dep_id not in seen:
                raise validation_error(
                    "work-graph plan dependency names a work not present in the plan: "
                    f"{dep_id!r}",
                    work_id=work_id,
                    dep_id=dep_id,
                )
            condition = dep.get("condition")
            if condition not in VALID_DEPENDENCY_CONDITIONS:
                raise validation_error(
                    "work-graph plan dependency condition must be "
                    f"{DEPENDENCY_CONDITION_ACCEPTED!r}: {condition!r}",
                    work_id=work_id,
                    dep_id=dep_id,
                    condition=_safe_repr(condition),
                )

    _reject_cycles(works)


def _safe_repr(value: Any) -> Any:
    """Return `value` unchanged if it is already portable-ish JSON-like
    data, otherwise its `repr()`. Keeps `ERR-VALIDATION` `details` from
    ever carrying an arbitrary/unportable object straight through when the
    plan itself is structurally malformed (e.g. `plan` is not a mapping at
    all)."""
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return repr(value)


def _reject_cycles(works: Sequence[Mapping[str, Any]]) -> None:
    edges = {entry["work_id"]: [dep["work_id"] for dep in entry.get("deps", [])] for entry in works}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise validation_error(
                f"work-graph plan has a dependency cycle involving work_id: {node!r}",
                work_id=node,
            )
        visiting.add(node)
        for dep in edges.get(node, []):
            visit(dep)
        visiting.discard(node)
        visited.add(node)

    for node in edges:
        visit(node)


class WorkGraphPort(Port):
    """`PORT-WORK-GRAPH`: create / snapshot / ready / claim / complete / block."""

    @abstractmethod
    def create(self, *, delivery_run_id: str, plan: Mapping[str, Any]) -> Sequence[Work]:
        """`PORT-WORK-001`. `plan` is the portable shape validated by
        `validate_plan`; implementations MUST call it (or an equivalent
        check) before committing Work records. The deterministic
        single-work plan is the degenerate one-element form: `works` with
        a single entry and an empty `deps` list."""
        raise NotImplementedError

    @abstractmethod
    def snapshot(self, *, delivery_run_id: str) -> Mapping[str, Any]:
        """`PORT-WORK-002`. The current bounded canonical work topology for
        one DeliveryRun, as an opaque portable mapping (the port doc does
        not further structure this return shape)."""
        raise NotImplementedError

    @abstractmethod
    def ready(self, *, delivery_run_id: str) -> Sequence[Work]:
        """`PORT-WORK-003`. Work eligible for dispatch now. Eligibility is
        authoritative: implementations MUST obey `INV-015` and `INV-016`."""
        raise NotImplementedError

    @abstractmethod
    def claim(self, *, work_id: str) -> Mapping[str, Any]:
        """`PORT-WORK-004`. Claim one Work item for orchestration/execution
        when supported, gated by `CAP-WORK-ATOMIC-CLAIM`
        (`orc_werk.ports.capabilities.CAP_WORK_ATOMIC_CLAIM`). Adapters
        that do not support atomic claim MUST raise
        `self._unsupported(CAP_WORK_ATOMIC_CLAIM, operation="claim")`
        (`INV-013`). Returns a portable mapping carrying at least
        `work_id` and `claim_ref` (the fields `FACT-WORK-CLAIMED` requires)."""
        raise NotImplementedError

    @abstractmethod
    def complete(self, *, work_id: str) -> Work:
        """`PORT-WORK-005`. Commit the completion condition required to
        unlock dependents (`INV-016`)."""
        raise NotImplementedError

    @abstractmethod
    def block(self, *, work_id: str, reason: str) -> Work:
        """`PORT-WORK-006`. Commit a non-terminal or terminal block reason
        according to policy/provider capability."""
        raise NotImplementedError


__all__ = [
    "DEPENDENCY_CONDITION_ACCEPTED",
    "VALID_DEPENDENCY_CONDITIONS",
    "WorkGraphPort",
    "validate_plan",
]
