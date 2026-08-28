"""ScriptedExecution (`TASK-M0-003`): a deterministic `ExecutionPort` test
double driven entirely by a portable script supplied at construction -- no
randomness, wall-clock time, process identity, or external I/O
(`AGENTS.md` #8/#9, `INV-020`).
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping

from orc_werk.core.errors import not_found_error, validation_error
from orc_werk.core.models import Execution
from orc_werk.core.portable import is_portable
from orc_werk.ports.base import (
    LIFECYCLE_STATE_SETTLED,
)
from orc_werk.ports.capabilities import (
    CAP_EXEC_CANCEL,
    CAP_EXEC_RESUME_BEST_EFFORT,
    CAP_EXEC_RESUME_EXACT,
    CAP_EXEC_SEND,
    validate_capabilities,
)
from orc_werk.ports.execution import ExecutionObservation, ExecutionPort

_RESUME_STRENGTHS = (CAP_EXEC_RESUME_BEST_EFFORT, CAP_EXEC_RESUME_EXACT)


def _digest(*parts: str) -> str:
    """Deterministic opaque-id derivation: stable given identical inputs,
    never randomness/wall-clock time (`CONF-EXEC-001`, `INV-020`)."""
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


class ScriptedExecution(ExecutionPort):
    """Deterministic `ExecutionPort` test double.

    Script format (portable data, one entry per Work's cumulative attempt
    sequence -- design note, see PR body for the "script format" decision):

    ```python
    {
      "<work_id>": [
        {
          "states": ["running", "settled"],   # optional; default ["settled"]
          "outcome": "completed",              # used once state == "settled"
          "artifact_refs": [...],              # optional, portable
          "extensions": {...},                 # optional, portable (CONTRACT-EXTENSIONS)
        },
        ...  # one entry per attempt, in script order
      ],
    }
    ```

    The attempt index consumed for one `work_id` is the count of *distinct*
    idempotency keys `start()` has already accepted for that `work_id`
    (0-based into the script list): repeated `start()` calls carrying an
    already-seen idempotency key return the existing `Execution` and do NOT
    consume a new script entry (`CONF-EXEC-002`).

    `resume_request["capability"]` names the exact resume strength the
    caller requires -- `CAP-EXEC-RESUME-BEST-EFFORT` or
    `CAP-EXEC-RESUME-EXACT`; omitted defaults to best-effort (least
    commitment, since the port doc does not name a default). A request for
    a strength this instance does not advertise in `capabilities()` raises
    the canonical `ERR-UNSUPPORTED-CAPABILITY` (`INV-013`, `CONF-EXEC-004`,
    `SCN-006`) -- it never silently starts a fresh conversation. This
    adapter does not treat `CAP-EXEC-RESUME-EXACT` as implying
    `CAP-EXEC-RESUME-BEST-EFFORT`: neither the port doc nor
    `CONTRACT-CAPABILITIES` states such an implication, so a script that
    wants to serve both strengths must advertise both explicitly
    (least-commitment; see "Ambiguities encountered" in the PR body).
    """

    def __init__(
        self,
        *,
        script: Mapping[str, Iterable[Mapping[str, Any]]],
        capabilities: Iterable[str] = (),
    ) -> None:
        script_dict = {work_id: list(entries) for work_id, entries in script.items()}
        if not is_portable({k: list(v) for k, v in script_dict.items()}):
            raise ValueError("ScriptedExecution script must be portable/JSON-compatible")
        self._script: dict[str, list[dict[str, Any]]] = {
            work_id: [dict(entry) for entry in entries] for work_id, entries in script_dict.items()
        }
        self._capabilities = validate_capabilities(capabilities)

        self._by_idempotency_key: dict[str, Execution] = {}
        self._attempts_by_work: dict[str, list[str]] = {}
        self._entry_by_execution: dict[str, Mapping[str, Any]] = {}
        self._inspect_calls: dict[str, int] = {}
        self._cancelled: set[str] = set()
        self._sent: dict[str, list[Mapping[str, Any]]] = {}

    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    def start(
        self,
        *,
        work_id: str,
        execution_request: Mapping[str, Any],
        idempotency_key: str,
    ) -> Execution:
        if idempotency_key in self._by_idempotency_key:
            # CONF-EXEC-002: same idempotency key -> same Execution ref, no
            # duplicate logical execution, no script entry consumed.
            return self._by_idempotency_key[idempotency_key]

        attempts = self._attempts_by_work.setdefault(work_id, [])
        attempt_index = len(attempts)  # 0-based into the script list
        entries = self._script.get(work_id, [])
        if attempt_index >= len(entries):
            raise not_found_error(
                "ScriptedExecution has no scripted outcome for this attempt",
                work_id=work_id,
                attempt_index=attempt_index,
            )
        entry = dict(entries[attempt_index])

        # CONF-EXEC-001: stable, deterministic, opaque -- derived from the
        # idempotency key only, never randomness/time.
        execution_id = f"exec-{_digest(idempotency_key)}"
        execution = Execution(id=execution_id, work_id=work_id, attempt_number=attempt_index + 1)

        attempts.append(execution_id)
        self._by_idempotency_key[idempotency_key] = execution
        self._entry_by_execution[execution_id] = entry
        self._inspect_calls[execution_id] = 0
        return execution

    def inspect(self, *, execution_id: str) -> ExecutionObservation:
        entry = self._entry_by_execution.get(execution_id)
        if entry is None:
            raise not_found_error("unknown execution_id", execution_id=execution_id)

        if execution_id in self._cancelled:
            return ExecutionObservation(state=LIFECYCLE_STATE_SETTLED, outcome="cancelled")

        states = list(entry.get("states", [LIFECYCLE_STATE_SETTLED]))
        call_index = self._inspect_calls[execution_id]
        self._inspect_calls[execution_id] = call_index + 1
        # CONF-EXEC-003: successive inspect() calls walk the scripted state
        # sequence; once exhausted, the last (terminal) state is sticky.
        state = states[min(call_index, len(states) - 1)]

        if state != LIFECYCLE_STATE_SETTLED:
            return ExecutionObservation(state=state)

        return ExecutionObservation(
            state=LIFECYCLE_STATE_SETTLED,
            outcome=entry.get("outcome", "completed"),
            artifact_refs=tuple(entry.get("artifact_refs", ())),
            extensions=dict(entry.get("extensions", {})),
        )

    def send(self, *, execution_id: str, message: Mapping[str, Any]) -> None:
        self._require_capability(CAP_EXEC_SEND, operation="send", execution_id=execution_id)
        if execution_id not in self._entry_by_execution:
            raise not_found_error("unknown execution_id", execution_id=execution_id)
        self._sent.setdefault(execution_id, []).append(dict(message))

    def cancel(self, *, execution_id: str) -> None:
        self._require_capability(CAP_EXEC_CANCEL, operation="cancel", execution_id=execution_id)
        if execution_id not in self._entry_by_execution:
            raise not_found_error("unknown execution_id", execution_id=execution_id)
        self._cancelled.add(execution_id)

    def resume(self, *, execution_id: str, resume_request: Mapping[str, Any]) -> Execution:
        requested = resume_request.get("capability", CAP_EXEC_RESUME_BEST_EFFORT)
        if requested not in _RESUME_STRENGTHS:
            raise validation_error(
                "resume_request['capability'] must name a resume-strength capability id",
                requested=requested,
            )
        # INV-013 / CONF-EXEC-004 / SCN-006: never silently emulate a
        # stronger semantic with a weaker one -- fail explicitly instead.
        self._require_capability(requested, operation="resume", execution_id=execution_id)

        if execution_id not in self._entry_by_execution:
            raise not_found_error("unknown execution_id", execution_id=execution_id)

        work_id = None
        attempt_index = None
        for candidate_work_id, ids in self._attempts_by_work.items():
            if execution_id in ids:
                work_id = candidate_work_id
                attempt_index = ids.index(execution_id)
                break
        assert work_id is not None and attempt_index is not None  # guarded by the lookup above

        # Scripted resume is a no-op continuation of the same logical
        # Execution: this test double has no provider-side conversation to
        # actually resume, so it returns the same Execution reference once
        # the requested strength is confirmed supported.
        return Execution(id=execution_id, work_id=work_id, attempt_number=attempt_index + 1)


__all__ = ["ScriptedExecution"]
