"""ExecutionPort (`PORT-EXECUTION`): start, inspect, communicate with, and
cancel external work-producing executions without modeling provider-native
agent internals.

Explicit non-semantics (`docs/contracts/ports/execution-port.md`): this
port never promises model identity, subagent visibility, transcript
access, provider tool-call events, or terminal/pane identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from abc import abstractmethod
from typing import Any, Mapping, Optional

from orc_werk.core.facts import EXEC_OUTCOMES
from orc_werk.core.models import Execution
from orc_werk.core.portable import is_portable, to_portable
from orc_werk.ports.base import LIFECYCLE_STATES, Port


@dataclass(frozen=True)
class ExecutionObservation:
    """`PORT-EXEC-002` canonical `inspect` result:

    ```text
    state: requested | running | settled
    outcome?: completed | failed | cancelled
    artifact_refs?: opaque references
    ```

    `outcome` and `artifact_refs` are optional per the port doc (not tied
    to a specific state by the normative text); `extensions` carries
    opaque, portable, losslessly-preserved baggage (`CONTRACT-EXTENSIONS`).
    """

    state: str
    outcome: Optional[str] = None
    artifact_refs: tuple[Any, ...] = field(default_factory=tuple)
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in LIFECYCLE_STATES:
            raise ValueError(f"unknown execution observation state: {self.state!r}")
        if self.outcome is not None and self.outcome not in EXEC_OUTCOMES:
            raise ValueError(f"unknown execution outcome: {self.outcome!r}")
        if not is_portable(list(self.artifact_refs)):
            raise ValueError("artifact_refs is not portable/JSON-compatible")
        if not is_portable(dict(self.extensions)):
            raise ValueError("extensions is not portable/JSON-compatible")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"state": self.state}
        if self.outcome is not None:
            data["outcome"] = self.outcome
        data["artifact_refs"] = to_portable(list(self.artifact_refs))
        data["extensions"] = to_portable(dict(self.extensions))
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionObservation":
        return cls(
            state=data["state"],
            outcome=data.get("outcome"),
            artifact_refs=tuple(data.get("artifact_refs", [])),
            extensions=dict(data.get("extensions", {})),
        )


class ExecutionPort(Port):
    """`PORT-EXECUTION`: start / inspect / send / cancel / resume."""

    @abstractmethod
    def start(
        self,
        *,
        work_id: str,
        execution_request: Mapping[str, Any],
        idempotency_key: str,
    ) -> Execution:
        """`PORT-EXEC-001`. `execution_request` is an opaque portable
        mapping -- the port does not structure provider-specific request
        contents. Returns a stable Execution reference."""
        raise NotImplementedError

    @abstractmethod
    def inspect(self, *, execution_id: str) -> ExecutionObservation:
        """`PORT-EXEC-002`."""
        raise NotImplementedError

    @abstractmethod
    def send(self, *, execution_id: str, message: Mapping[str, Any]) -> None:
        """`PORT-EXEC-003`. Gated by `CAP-EXEC-SEND`
        (`orc_werk.ports.capabilities.CAP_EXEC_SEND`); adapters that do not
        support it MUST raise
        `self._unsupported(CAP_EXEC_SEND, operation="send")`. `message` is
        an opaque portable mapping."""
        raise NotImplementedError

    @abstractmethod
    def cancel(self, *, execution_id: str) -> None:
        """`PORT-EXEC-004`. Optional/required according to adapter profile;
        gated by `CAP-EXEC-CANCEL`
        (`orc_werk.ports.capabilities.CAP_EXEC_CANCEL`)."""
        raise NotImplementedError

    @abstractmethod
    def resume(self, *, execution_id: str, resume_request: Mapping[str, Any]) -> Execution:
        """`PORT-EXEC-005`. Optional; gated by
        `CAP-EXEC-RESUME-BEST-EFFORT` / `CAP-EXEC-RESUME-EXACT`. Adapters
        MUST distinguish which resume strength they provide via
        `capabilities()` and MUST NOT silently emulate exact resume with
        best-effort resume (`INV-013`, `SCN-006`) -- an adapter lacking the
        strength policy requires MUST raise
        `self._unsupported(CAP_EXEC_RESUME_EXACT, operation="resume")` (or
        the best-effort equivalent) rather than starting a fresh
        conversation silently. `resume_request` is an opaque portable
        mapping."""
        raise NotImplementedError


__all__ = ["ExecutionObservation", "ExecutionPort"]
