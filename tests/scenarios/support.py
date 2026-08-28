"""Shared builders for tests/scenarios/ -- executable forms of `SCN-001`
through `SCN-006` (`ARCH-REPOSITORY-STRUCTURE`).

Not a test module itself (no `test_` prefix). Scenarios drive the
`orc_werk.app.Orchestrator` with scripted/memory adapters, mirroring each
`docs/scenarios/SCN-*.md` step-for-step rather than reaching into
`orc_werk.core` reducer/policy internals directly (that is `tests/core/`'s
job).
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.memory.journal import MemoryJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate, fingerprint_of
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app import Orchestrator, RunConfig, default_single_work_plan
from orc_werk.core.effects import FX_START_EXECUTION
from orc_werk.core.idempotency import idempotency_key
from orc_werk.ports.journal import JournalPort
from orc_werk.ports.work_graph import WorkGraphPort


def predicted_execution_id(*, delivery_run_id: str, work_id: str, attempt_number: int) -> str:
    """Mirrors `ScriptedExecution`'s own documented, deterministic
    execution-id derivation (`CONF-EXEC-001`): a pure function of the
    `FX-START-EXECUTION` idempotency key. Lets tests pre-author
    `ScriptedCandidate` subjects (keyed by `execution_id`) without reaching
    into adapter internals."""
    key = idempotency_key(
        FX_START_EXECUTION, delivery_run_id=delivery_run_id, work_id=work_id, attempt_number=attempt_number
    )
    return f"exec-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"


def build_run(
    *,
    delivery_run_id: str,
    attempts_by_work: Mapping[str, Sequence[Mapping[str, Any]]],
    plan: Optional[Mapping[str, Any]] = None,
    max_attempts: int = 3,
    resume_capability: Optional[str] = None,
    execution_capabilities: Sequence[str] = (),
    journal: Optional[JournalPort] = None,
    work_graph: Optional[WorkGraphPort] = None,
) -> tuple[Orchestrator, JournalPort, WorkGraphPort]:
    """Build a fully-wired `Orchestrator` (+ its journal/work-graph) from a
    per-work attempt script.

    `attempts_by_work[work_id]` is a list of attempts in order (attempt 1
    first); each attempt is a mapping with:

    - `outcome`: `"completed"` or `"failed"` (required).
    - `candidate`: portable subject-identity content, or omitted/`None`
      when the attempt should produce no assurable candidate (only
      meaningful when `outcome == "completed"`).
    - `verdict`: `"accepted"` | `"rejected"` | `"inconclusive"`, only
      meaningful when `candidate` is present.
    """
    execution_script: dict[str, list[dict[str, Any]]] = {}
    candidate_subjects: dict[str, dict[str, Any]] = {}
    assurance_script: dict[str, dict[str, Any]] = {}

    for work_id, attempts in attempts_by_work.items():
        execution_script[work_id] = []
        for attempt in attempts:
            entry: dict[str, Any] = {"outcome": attempt["outcome"]}
            if attempt.get("states") is not None:
                entry["states"] = attempt["states"]
            execution_script[work_id].append(entry)
        for attempt_index, attempt in enumerate(attempts):
            candidate_content = attempt.get("candidate")
            if attempt["outcome"] != "completed" or candidate_content is None:
                continue
            execution_id = predicted_execution_id(
                delivery_run_id=delivery_run_id, work_id=work_id, attempt_number=attempt_index + 1
            )
            candidate_subjects[execution_id] = {"work_id": work_id, "subject_identity": candidate_content}
            verdict = attempt.get("verdict")
            if verdict is not None:
                assurance_script[fingerprint_of(candidate_content)] = {"verdict": verdict}

    journal = journal if journal is not None else MemoryJournal()
    work_graph = work_graph if work_graph is not None else MemoryWorkGraph()
    execution = ScriptedExecution(script=execution_script, capabilities=execution_capabilities)
    candidate = ScriptedCandidate(subjects=candidate_subjects, current_by_work={})
    assurance = ScriptedAssurance(script=assurance_script)

    orchestrator = Orchestrator(
        delivery_run_id=delivery_run_id,
        journal=journal,
        work_graph=work_graph,
        execution=execution,
        candidate=candidate,
        assurance=assurance,
        config=RunConfig(max_attempts=max_attempts, resume_capability=resume_capability),
    )
    resolved_plan = plan or default_single_work_plan(next(iter(attempts_by_work)))
    orchestrator.bootstrap(intent_id=delivery_run_id, text=f"scenario {delivery_run_id}", plan=resolved_plan)
    return orchestrator, journal, work_graph


__all__ = ["build_run", "predicted_execution_id"]
