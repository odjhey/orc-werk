"""Shared ABC surface for the five mandatory v0 ports.

`Port` centralizes the capability-advertisement surface every port needs
(`INV-013`/`SCN-006`, `CONTRACT-CAPABILITIES`) plus the one shared
lifecycle-state vocabulary (`requested | running | settled`) that both
`PORT-EXECUTION` and `PORT-ASSURANCE` use verbatim for their `inspect`
observations.

Ports only depend on `orc_werk.core` and the standard library
(`ARCH-REPOSITORY-STRUCTURE`: `ports -> core canonical types` only, never
`adapters`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from orc_werk.core.errors import ERR_UNSUPPORTED_CAPABILITY, CoreError, canonical_error
from orc_werk.ports.capabilities import validate_capabilities

# Shared inspect/observation lifecycle vocabulary (PORT-EXECUTION,
# PORT-ASSURANCE) -- both ports document the exact same three-state
# progression, so it is defined once here rather than duplicated per port.
LIFECYCLE_STATE_REQUESTED = "requested"
LIFECYCLE_STATE_RUNNING = "running"
LIFECYCLE_STATE_SETTLED = "settled"
LIFECYCLE_STATES = frozenset(
    {LIFECYCLE_STATE_REQUESTED, LIFECYCLE_STATE_RUNNING, LIFECYCLE_STATE_SETTLED}
)


class Port(ABC):
    """Base class for `WorkGraphPort`, `ExecutionPort`, `CandidatePort`,
    `AssurancePort`, and `JournalPort`.

    Concrete adapters implement `capabilities()` to declare the exact
    `CAP-*` set (`CONTRACT-CAPABILITIES`) they guarantee. Operations gated
    by a capability (e.g. `ExecutionPort.send`, `.cancel`, `.resume`,
    `WorkGraphPort.claim`) are ordinary abstract methods -- adapters that
    do not support the required capability implement them by raising the
    canonical `ERR-UNSUPPORTED-CAPABILITY` error via `self._unsupported(...)`
    rather than emulating a stronger semantic with a weaker one (`INV-013`).
    """

    @abstractmethod
    def capabilities(self) -> frozenset[str]:
        """Return the exact `CAP-*` identifiers this adapter instance
        guarantees. Implementations SHOULD build the returned set with
        `orc_werk.ports.capabilities.validate_capabilities` so an invented
        capability id fails fast rather than silently misadvertising."""
        raise NotImplementedError

    def supports(self, capability: str) -> bool:
        """Query whether this adapter instance advertises `capability`."""
        return capability in self.capabilities()

    def _unsupported(self, capability: str, *, operation: str, **details: Any) -> CoreError:
        """Build (does not raise) the canonical `ERR-UNSUPPORTED-CAPABILITY`
        error value (`INV-013`) for a capability-gated operation this
        adapter instance does not guarantee."""
        return CoreError(
            canonical_error(
                ERR_UNSUPPORTED_CAPABILITY,
                f"{operation} requires capability {capability!r}, which this "
                "provider does not advertise",
                capability=capability,
                operation=operation,
                **details,
            )
        )

    def _require_capability(self, capability: str, *, operation: str, **details: Any) -> None:
        """Raise the canonical `ERR-UNSUPPORTED-CAPABILITY` error unless
        `capability` is advertised. Convenience wrapper around
        `_unsupported` for adapters that want a one-line guard clause."""
        if not self.supports(capability):
            raise self._unsupported(capability, operation=operation, **details)


__all__ = [
    "LIFECYCLE_STATE_REQUESTED",
    "LIFECYCLE_STATE_RUNNING",
    "LIFECYCLE_STATE_SETTLED",
    "LIFECYCLE_STATES",
    "Port",
    "validate_capabilities",
]
