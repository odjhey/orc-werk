"""Shared fact-sequence builders for tests/core/.

Not a test module itself (no `test_` prefix) -- imported by the actual
test modules to build up per-Work fact sequences that mirror the golden
scenarios and the STATE-DELIVERY transition table.
"""

from __future__ import annotations

from orc_werk.core.facts import (
    FACT_ASSURE_SETTLED,
    FACT_ASSURE_STARTED,
    FACT_CANDIDATE_OBSERVED,
    FACT_EXEC_SETTLED,
    FACT_EXEC_STARTED,
    FACT_WORK_BLOCKED,
    FACT_WORK_CLAIMED,
    FACT_WORK_COMPLETED,
    FACT_WORK_CREATED,
    FACT_WORK_READY,
    Fact,
    make_fact,
)


def created_and_ready(*, delivery_run_id: str, work_id: str) -> list[Fact]:
    return [
        make_fact(FACT_WORK_CREATED, delivery_run_id=delivery_run_id, work_id=work_id),
        make_fact(FACT_WORK_READY, delivery_run_id=delivery_run_id, work_id=work_id),
    ]


def dispatched(
    *, delivery_run_id: str, work_id: str, execution_id: str
) -> list[Fact]:
    facts = created_and_ready(delivery_run_id=delivery_run_id, work_id=work_id)
    facts.append(
        make_fact(FACT_EXEC_STARTED, delivery_run_id=delivery_run_id, work_id=work_id, execution_id=execution_id)
    )
    return facts


def settled_completed_with_candidate(
    *,
    delivery_run_id: str,
    work_id: str,
    execution_id: str,
    candidate_id: str,
    fingerprint: str,
) -> list[Fact]:
    facts = dispatched(delivery_run_id=delivery_run_id, work_id=work_id, execution_id=execution_id)
    facts.append(
        make_fact(
            FACT_EXEC_SETTLED,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            execution_id=execution_id,
            outcome="completed",
        )
    )
    facts.append(
        make_fact(
            FACT_CANDIDATE_OBSERVED,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            candidate_id=candidate_id,
            fingerprint=fingerprint,
            execution_id=execution_id,
        )
    )
    return facts


def assuring(
    *,
    delivery_run_id: str,
    work_id: str,
    execution_id: str,
    candidate_id: str,
    fingerprint: str,
    assurance_id: str,
) -> list[Fact]:
    facts = settled_completed_with_candidate(
        delivery_run_id=delivery_run_id,
        work_id=work_id,
        execution_id=execution_id,
        candidate_id=candidate_id,
        fingerprint=fingerprint,
    )
    facts.append(
        make_fact(
            FACT_ASSURE_STARTED,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            assurance_id=assurance_id,
            candidate_id=candidate_id,
        )
    )
    return facts


def assure_settled(
    *,
    delivery_run_id: str,
    work_id: str,
    assurance_id: str,
    fingerprint: str,
    verdict: str,
) -> Fact:
    return make_fact(
        FACT_ASSURE_SETTLED,
        delivery_run_id=delivery_run_id,
        work_id=work_id,
        assurance_id=assurance_id,
        candidate_fingerprint=fingerprint,
        verdict=verdict,
    )


def exec_settled_failed(*, delivery_run_id: str, work_id: str, execution_id: str) -> Fact:
    return make_fact(
        FACT_EXEC_SETTLED,
        delivery_run_id=delivery_run_id,
        work_id=work_id,
        execution_id=execution_id,
        outcome="failed",
    )


def happy_path_facts(
    *, delivery_run_id: str, work_id: str
) -> list[Fact]:
    """SCN-001: one dispatch, one execution, one accepted candidate."""
    facts = assuring(
        delivery_run_id=delivery_run_id,
        work_id=work_id,
        execution_id="e1",
        candidate_id="c1",
        fingerprint="fp-c1",
        assurance_id="a1",
    )
    facts.append(
        assure_settled(
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            assurance_id="a1",
            fingerprint="fp-c1",
            verdict="accepted",
        )
    )
    facts.append(make_fact(FACT_WORK_COMPLETED, delivery_run_id=delivery_run_id, work_id=work_id))
    return facts


def attempt_budget_exhausted_facts(
    *, delivery_run_id: str, work_id: str, max_attempts: int
) -> list[Fact]:
    """SCN-004: `max_attempts` consecutive failed executions, then BLOCKED."""
    facts = created_and_ready(delivery_run_id=delivery_run_id, work_id=work_id)
    for attempt in range(1, max_attempts + 1):
        execution_id = f"e{attempt}"
        facts.append(
            make_fact(FACT_EXEC_STARTED, delivery_run_id=delivery_run_id, work_id=work_id, execution_id=execution_id)
        )
        facts.append(exec_settled_failed(delivery_run_id=delivery_run_id, work_id=work_id, execution_id=execution_id))
    facts.append(
        make_fact(
            FACT_WORK_BLOCKED,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            reason="retry-budget-exhausted",
        )
    )
    return facts
