"""Deterministic v0 policy (`STATE-DELIVERY`, `M-000`).

Given one Work's derived projection (`orc_werk.core.reducer`) and a policy
config, `decide` returns the next Decision + Effect(s), or `None` when no
Work-scoped state-changing action is currently pending (mid-flight,
awaiting an external settlement fact, or already terminal/confirmed).

Policy is a deterministic lookup from (state, pending markers) to the exact
Decision/Effect(s) named by the transition table -- v0 defines no
alternative strategies to choose between (M-000 explicitly excludes an LLM
planner/watchtower policy), so this mapping is not a "choice" in the
INV-011 sense beyond selecting the single row the table already specifies.
All budget arithmetic (INV-018/INV-019) already happened in the reducer;
policy only reads `projection.state`.
"""

from __future__ import annotations

from dataclasses import dataclass

from orc_werk.core.decisions import (
    DEC_ACCEPT,
    DEC_BLOCK,
    DEC_DISPATCH,
    DEC_REQUEST_ASSURANCE,
    DEC_RETRY,
    Decision,
    make_decision,
)
from orc_werk.core.effects import (
    FX_BLOCK_WORK,
    FX_COMPLETE_WORK,
    FX_START_ASSURANCE,
    FX_START_EXECUTION,
    Effect,
    make_effect,
)
from orc_werk.core.idempotency import idempotency_key
from orc_werk.core.reducer import DEFAULT_MAX_ATTEMPTS
from orc_werk.core.state import STATE_ACCEPTED, STATE_ASSURING, STATE_BLOCKED, STATE_READY, WorkProjection


@dataclass(frozen=True)
class PolicyOutcome:
    decision: Decision
    effects: tuple[Effect, ...]


def _block_reason(projection: WorkProjection, *, max_attempts: int) -> str:
    trigger = projection.trigger_facts[-1] if projection.trigger_facts else {}
    fact_id = trigger.get("id")
    if fact_id == "FACT-ASSURE-SETTLED" and trigger.get("data", {}).get("verdict") == "inconclusive":
        return "assurance-inconclusive"
    return "retry-budget-exhausted"


def decide(
    projection: WorkProjection,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> PolicyOutcome | None:
    delivery_run_id = projection.delivery_run_id
    work_id = projection.work_id
    state_basis = {"attempt_number": projection.attempt_number, "max_attempts": max_attempts}

    if projection.state == STATE_READY and projection.ready_confirmed:
        upcoming_attempt = projection.attempt_number + 1
        decision_id = DEC_DISPATCH if projection.attempt_number == 0 else DEC_RETRY
        decision = make_decision(
            decision_id,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            basis=projection.trigger_facts,
            data={"attempt_number": upcoming_attempt},
        )
        effect = make_effect(
            FX_START_EXECUTION,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            idempotency_key=idempotency_key(
                FX_START_EXECUTION,
                delivery_run_id=delivery_run_id,
                work_id=work_id,
                attempt_number=upcoming_attempt,
            ),
            data={"attempt_number": upcoming_attempt},
        )
        return PolicyOutcome(decision=decision, effects=(effect,))

    if projection.state == STATE_ASSURING and not projection.assurance_started_for_current:
        fingerprint = projection.current_candidate_fingerprint()
        decision = make_decision(
            DEC_REQUEST_ASSURANCE,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            basis=projection.trigger_facts,
            data={"candidate_id": projection.current_candidate_id},
        )
        effect = make_effect(
            FX_START_ASSURANCE,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            idempotency_key=idempotency_key(
                FX_START_ASSURANCE,
                delivery_run_id=delivery_run_id,
                work_id=work_id,
                attempt_number=projection.attempt_number,
                candidate_fingerprint=fingerprint,
            ),
            data={"candidate_id": projection.current_candidate_id, "candidate_fingerprint": fingerprint},
        )
        return PolicyOutcome(decision=decision, effects=(effect,))

    if projection.state == STATE_ACCEPTED and not projection.completed_confirmed:
        decision = make_decision(
            DEC_ACCEPT,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            basis=projection.trigger_facts,
        )
        effect = make_effect(
            FX_COMPLETE_WORK,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            idempotency_key=idempotency_key(
                FX_COMPLETE_WORK,
                delivery_run_id=delivery_run_id,
                work_id=work_id,
                attempt_number=projection.attempt_number,
            ),
        )
        return PolicyOutcome(decision=decision, effects=(effect,))

    if projection.state == STATE_BLOCKED and not projection.blocked_confirmed:
        reason = _block_reason(projection, max_attempts=max_attempts)
        decision = make_decision(
            DEC_BLOCK,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            basis=projection.trigger_facts,
            data={**state_basis, "reason": reason},
        )
        effect = make_effect(
            FX_BLOCK_WORK,
            delivery_run_id=delivery_run_id,
            work_id=work_id,
            idempotency_key=idempotency_key(
                FX_BLOCK_WORK,
                delivery_run_id=delivery_run_id,
                work_id=work_id,
                attempt_number=projection.attempt_number,
            ),
            data={"reason": reason},
        )
        return PolicyOutcome(decision=decision, effects=(effect,))

    return None
