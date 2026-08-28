"""Canonical error values (CONTRACT-ERRORS).

Canonical errors are portable, JSON-compatible dicts of the shape
``{"error": "<ERR-*>", "message": str, "details": {...}}``. `CoreError` is a
Python exception used only as a stack-unwinding carrier for that portable
value (AGENTS.md #9 / ARCH-REPOSITORY-STRUCTURE portability rules): callers
must treat `CoreError.error` (or `.to_canonical()`) as the canonical shape,
never the exception class name, args, or traceback.

An optional, additive ``next`` key (issue #94, `PLAYBOOK-CLI-USAGE`'s
affordance rule extended to the error surface) may sit alongside
``error``/``message``/``details``: a list of 1-3 runnable or navigational
strings naming where to find what is missing, or what to run to inspect
the failure. Backward-compatible -- callers that never pass `next_steps`
get the exact same three-key shape as before; the CLI is where this field
is populated by convention (`orc_werk.cli`), not a requirement this module
enforces on every raiser.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

ERR_VALIDATION = "ERR-VALIDATION"
ERR_CONFLICT = "ERR-CONFLICT"
ERR_NOT_FOUND = "ERR-NOT-FOUND"
ERR_UNSUPPORTED_CAPABILITY = "ERR-UNSUPPORTED-CAPABILITY"
ERR_PROVIDER_UNAVAILABLE = "ERR-PROVIDER-UNAVAILABLE"
ERR_UNSAFE_STATE = "ERR-UNSAFE-STATE"
ERR_TEMPORARY = "ERR-TEMPORARY"
ERR_PERMANENT = "ERR-PERMANENT"

# CONTRACT-ERRORS registry.
CANONICAL_ERROR_IDS = frozenset(
    {
        ERR_VALIDATION,
        ERR_CONFLICT,
        ERR_NOT_FOUND,
        ERR_UNSUPPORTED_CAPABILITY,
        ERR_PROVIDER_UNAVAILABLE,
        ERR_UNSAFE_STATE,
        ERR_TEMPORARY,
        ERR_PERMANENT,
    }
)


def canonical_error(
    error_id: str, message: str, *, next_steps: Optional[Sequence[str]] = None, **details: Any
) -> dict[str, Any]:
    """Build a portable canonical error value.

    Returns plain JSON-compatible data only -- no Python exception/class
    shapes (ARCH-REPOSITORY-STRUCTURE portability rules).

    `next_steps` (issue #94), when given and non-empty, becomes the
    envelope's additive ``next`` list -- omitted entirely otherwise, so a
    caller that never passes it gets the unchanged three-key shape.
    """
    if error_id not in CANONICAL_ERROR_IDS:
        raise ValueError(f"unknown canonical error id: {error_id!r}")
    error: dict[str, Any] = {"error": error_id, "message": message, "details": dict(details)}
    if next_steps:
        error["next"] = list(next_steps)
    return error


class CoreError(Exception):
    """Raised by core code; carries a canonical error value (never itself
    the canonical shape -- see module docstring)."""

    def __init__(self, error: Mapping[str, Any]) -> None:
        super().__init__(error.get("message", error.get("error", "core error")))
        self.error: dict[str, Any] = dict(error)

    def to_canonical(self) -> dict[str, Any]:
        return dict(self.error)


def validation_error(message: str, *, next_steps: Optional[Sequence[str]] = None, **details: Any) -> CoreError:
    return CoreError(canonical_error(ERR_VALIDATION, message, next_steps=next_steps, **details))


def conflict_error(message: str, *, next_steps: Optional[Sequence[str]] = None, **details: Any) -> CoreError:
    return CoreError(canonical_error(ERR_CONFLICT, message, next_steps=next_steps, **details))


def not_found_error(message: str, *, next_steps: Optional[Sequence[str]] = None, **details: Any) -> CoreError:
    return CoreError(canonical_error(ERR_NOT_FOUND, message, next_steps=next_steps, **details))
