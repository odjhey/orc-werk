"""Pure reducer: folds an ordered Fact sequence into per-Work state
(`STATE-DELIVERY` transition table).

The reducer is mechanics only (TASK-M0-001): it validates that each Fact is
a legal transition from the Work's current derived state and mechanically
derives the next state -- it never chooses between alternative courses of
action (that is `orc_werk.core.policy`'s job). Where the transition table's
"Next" column depends on the retry budget (INV-018/INV-019), the reducer
compares `attempt_number` against the supplied `max_attempts` -- this is
arithmetic derivation, not policy judgment; v0 has exactly one deterministic
budget rule, so there is nothing to choose between.

State-derivation convention (design note, not a normative source): each row
of the transition table's "Next" column is entered eagerly, as soon as the
row's trigger Fact is folded (e.g. `FACT-EXEC-SETTLED(failed)` moves the
Work straight to READY or BLOCKED). The subsequent "confirmation" Facts
(`FACT-EXEC-STARTED`, `FACT-WORK-COMPLETED`, `FACT-WORK-BLOCKED`) are then
validated as the only legal continuations from that state and flip
idempotency markers (`assurance_started_for_current`, `completed_confirmed`,
`blocked_confirmed`) so `policy.decide` fires each Decision exactly once.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional

from orc_werk.core.errors import conflict_error, not_found_error, validation_error
from orc_werk.core.facts import (
    EXEC_OUTCOMES,
    FACT_ASSURE_SETTLED,
    FACT_ASSURE_STARTED,
    FACT_ATTEMPT_ABANDONED,
    FACT_CANDIDATE_OBSERVED,
    FACT_EXEC_SETTLED,
    FACT_EXEC_STARTED,
    FACT_INTENT_SUBMITTED,
    FACT_WORK_BLOCKED,
    FACT_WORK_CANCELLED,
    FACT_WORK_CLAIMED,
    FACT_WORK_COMPLETED,
    FACT_WORK_CREATED,
    FACT_WORK_READY,
    Fact,
)
from orc_werk.core.state import (
    STATE_ACCEPTED,
    STATE_ASSURING,
    STATE_BLOCKED,
    STATE_EXECUTING,
    STATE_READY,
    DeliveryProjection,
    WorkProjection,
    replace_projection,
)

DEFAULT_MAX_ATTEMPTS = 3


def _require_state(fact: Fact, projection: WorkProjection, *expected: str) -> None:
    if projection.state not in expected:
        raise conflict_error(
            f"{fact.id} illegal from state {projection.state!r} (expected one of {list(expected)})",
            fact_id=fact.id,
            work_id=projection.work_id,
            state=projection.state,
        )


def _settled_assurance_for_candidate(
    projection: WorkProjection, candidate_id: str
) -> Optional[dict]:
    """The most recent settled assurance entry for `candidate_id` in this
    Work's lineage (verdict inheritance, STATE-DELIVERY item 8), or `None`
    if this candidate has no settled assurance to inherit from yet."""
    match = None
    for entry in projection.assurances:
        if entry["candidate_id"] == candidate_id and entry.get("verdict") not in (None, "abandoned"):
            match = entry
    return match


def _inherit_verdict(
    projection: WorkProjection,
    candidate_id: str,
    inherited: Mapping[str, object],
    *,
    max_attempts: int,
) -> WorkProjection:
    """Fold a re-observed candidate's inherited verdict (STATE-DELIVERY
    item 8) exactly as the FACT-ASSURE-SETTLED branch would have for a
    fresh settlement carrying the same verdict -- except no new Fact is
    journaled (INV-003: no fabricated assurance evidence) and the basis
    cited for whatever DEC-* follows is the *prior* settlement Fact."""
    verdict = inherited["verdict"]
    if verdict == "accepted":
        next_state = STATE_ACCEPTED
    elif verdict == "rejected":
        next_state = STATE_READY if projection.attempt_number < max_attempts else STATE_BLOCKED
    elif verdict == "inconclusive":
        next_state = STATE_BLOCKED
    else:
        raise validation_error(f"unknown inherited assurance verdict: {verdict!r}")
    return replace_projection(
        projection,
        state=next_state,
        current_candidate_id=candidate_id,
        trigger_facts=(inherited["settled_fact"],),
    )


def apply_fact(
    projection: Optional[WorkProjection],
    fact: Fact,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> WorkProjection:
    """Fold one Fact into the prior per-Work projection (or create it, for
    `FACT-WORK-CREATED`). Raises `CoreError` for illegal transitions."""

    if fact.id == FACT_WORK_CREATED:
        if projection is not None:
            raise conflict_error(
                "FACT-WORK-CREATED for a Work that already exists",
                work_id=fact.field("work_id"),
            )
        # STATE-DELIVERY's diagram enters READY with no incoming arrow: Work
        # creation is mechanical (INV-011) and places the Work in READY,
        # awaiting the FACT-WORK-READY eligibility signal (INV-015) before
        # DEC-DISPATCH may fire.
        return WorkProjection(
            work_id=fact.field("work_id"),
            delivery_run_id=fact.delivery_run_id,
            state=STATE_READY,
        )

    if projection is None:
        raise not_found_error(
            f"{fact.id} references a Work with no FACT-WORK-CREATED yet",
            fact_id=fact.id,
        )

    if fact.data.get("work_id") not in (None, projection.work_id):
        raise validation_error(
            f"{fact.id} work_id does not match projection",
            fact_id=fact.id,
            expected=projection.work_id,
            actual=fact.data.get("work_id"),
        )

    if fact.id == FACT_WORK_READY:
        _require_state(fact, projection, STATE_READY)
        return replace_projection(
            projection,
            ready_confirmed=True,
            trigger_facts=(fact.to_dict(),),
        )

    if fact.id == FACT_WORK_CLAIMED:
        _require_state(fact, projection, STATE_READY)
        return replace_projection(projection, claim_ref=fact.field("claim_ref"))

    if fact.id == FACT_EXEC_STARTED:
        _require_state(fact, projection, STATE_READY)
        if not projection.ready_confirmed:
            raise conflict_error(
                "FACT-EXEC-STARTED without a prior FACT-WORK-READY (INV-015)",
                work_id=projection.work_id,
            )
        if projection.attempt_number >= max_attempts:
            raise conflict_error(
                "FACT-EXEC-STARTED exceeds retry budget (INV-018/INV-019)",
                work_id=projection.work_id,
                attempt_number=projection.attempt_number,
                max_attempts=max_attempts,
            )
        execution_id = fact.field("execution_id")
        if any(item["execution_id"] == execution_id for item in projection.executions):
            # INV-004: retry MUST create a new Execution identity; historical
            # Executions MUST NOT be overwritten/reused.
            raise conflict_error(
                "FACT-EXEC-STARTED reuses an existing execution_id (INV-004)",
                work_id=projection.work_id,
                execution_id=execution_id,
            )
        executions = projection.executions + (
            {"execution_id": execution_id, "outcome": None, "settled_fact": None},
        )
        return replace_projection(
            projection,
            state=STATE_EXECUTING,
            attempt_number=projection.attempt_number + 1,
            executions=executions,
            current_execution_id=execution_id,
            current_candidate_id=None,
            current_assurance_id=None,
            assurance_started_for_current=False,
            trigger_facts=(),
        )

    if fact.id == FACT_EXEC_SETTLED:
        _require_state(fact, projection, STATE_EXECUTING)
        execution_id = fact.field("execution_id")
        if execution_id != projection.current_execution_id:
            raise conflict_error(
                "FACT-EXEC-SETTLED references an execution that is not current (INV-004)",
                work_id=projection.work_id,
                execution_id=execution_id,
                current_execution_id=projection.current_execution_id,
            )
        outcome = fact.field("outcome")
        if outcome not in EXEC_OUTCOMES:
            raise validation_error(f"unknown execution outcome: {outcome!r}")
        if outcome == "cancelled":
            # CANCELLED is reserved/unreachable in v0/M0 (STATE-DELIVERY).
            raise validation_error(
                "FACT-EXEC-SETTLED(cancelled) has no v0/M0 transition row (STATE-DELIVERY reserved)",
                work_id=projection.work_id,
            )
        executions = tuple(
            {**item, "outcome": outcome, "settled_fact": fact.to_dict()}
            if item["execution_id"] == execution_id
            else item
            for item in projection.executions
        )
        if outcome == "completed":
            # Awaiting FACT-CANDIDATE-OBSERVED before ASSURING is reachable
            # (transition table: "settled(completed) + candidate available").
            return replace_projection(projection, executions=executions)
        # outcome == "failed": INV-018/INV-019 budget split. attempt_number
        # already reflects this attempt (incremented on FACT-EXEC-STARTED).
        if projection.attempt_number < max_attempts:
            next_state = STATE_READY
        else:
            next_state = STATE_BLOCKED
        return replace_projection(
            projection,
            state=next_state,
            executions=executions,
            trigger_facts=(fact.to_dict(),),
        )

    if fact.id == FACT_CANDIDATE_OBSERVED:
        _require_state(fact, projection, STATE_EXECUTING)
        execution_id = fact.field("execution_id")
        if execution_id != projection.current_execution_id:
            raise conflict_error(
                "FACT-CANDIDATE-OBSERVED references an execution that is not current",
                work_id=projection.work_id,
                execution_id=execution_id,
            )
        current_entry = next(
            item for item in projection.executions if item["execution_id"] == execution_id
        )
        if current_entry["outcome"] != "completed":
            # INV-005: assurance requires an identifiable candidate for a
            # completed Execution -- candidate observation before settlement
            # is not a legal precondition for ASSURING in v0.
            raise conflict_error(
                "FACT-CANDIDATE-OBSERVED before the current execution settled completed (INV-005)",
                work_id=projection.work_id,
            )
        candidate_id = fact.field("candidate_id")
        if candidate_id in projection.candidates:
            # STATE-DELIVERY mechanical fact sequencing item 8
            # (TASK-M3B-001, issue #76): a re-observed candidate identity is
            # legal, not an unconditional conflict. When the re-observation
            # is exact (fingerprint matches -- INV-006) and a prior
            # FACT-ASSURE-SETTLED exists for it, the kernel mechanically
            # inherits that verdict (P-007/INV-011: no Decision here --
            # the ordinary DEC-ACCEPT/DEC-RETRY/DEC-BLOCK machinery reads
            # the resulting state next and cites the inherited settlement
            # as basis, INV-012). No new assurance evidence is fabricated
            # (INV-003): no FACT-ASSURE-SETTLED is journaled for this fold.
            prior_fp = projection.candidates[candidate_id]["fingerprint"]
            incoming_fp = fact.field("fingerprint")
            inherited = (
                _settled_assurance_for_candidate(projection, candidate_id)
                if incoming_fp == prior_fp
                else None
            )
            if inherited is not None:
                return _inherit_verdict(
                    projection, candidate_id, inherited, max_attempts=max_attempts
                )
            # item 9: neither an exact re-observation with something to
            # inherit, nor a legal fresh observation -- an unresolved
            # candidate-observation conflict (identity collision, INV-006/
            # INV-008, or a reused id whose only prior assurance never
            # settled). The Fact is still journaled/observed (immutable,
            # PROTOCOL-FACTS) and the Work rests at EXECUTING, marked --
            # mirroring item 7's "waiting is a normal resting point"
            # precedent -- rather than raising and permanently wedging
            # every future replay (the append-only journal cannot un-
            # observe this Fact). Recovery is DEC-ABANDON-ATTEMPT (item 9).
            return replace_projection(
                projection,
                candidate_conflict={
                    "candidate_id": candidate_id,
                    "fact": fact.to_dict(),
                    "reason": (
                        "fingerprint-mismatch"
                        if incoming_fp != prior_fp
                        else "no-inheritable-verdict"
                    ),
                },
                trigger_facts=(fact.to_dict(),),
            )
        candidates = dict(projection.candidates)
        candidates[candidate_id] = {
            "fingerprint": fact.field("fingerprint"),
            "execution_id": execution_id,
        }
        return replace_projection(
            projection,
            state=STATE_ASSURING,
            candidates=candidates,
            current_candidate_id=candidate_id,
            assurance_started_for_current=False,
            trigger_facts=(current_entry["settled_fact"], fact.to_dict()),
        )

    if fact.id == FACT_ASSURE_STARTED:
        _require_state(fact, projection, STATE_ASSURING)
        candidate_id = fact.field("candidate_id")
        if candidate_id != projection.current_candidate_id:
            # INV-007/INV-008: assurance must target the exact current candidate.
            raise conflict_error(
                "FACT-ASSURE-STARTED targets a candidate that is not current (INV-007/INV-008)",
                work_id=projection.work_id,
                candidate_id=candidate_id,
                current_candidate_id=projection.current_candidate_id,
            )
        if projection.assurance_started_for_current:
            raise conflict_error(
                "FACT-ASSURE-STARTED already recorded for the current candidate",
                work_id=projection.work_id,
            )
        assurance_id = fact.field("assurance_id")
        assurances = projection.assurances + (
            {"assurance_id": assurance_id, "candidate_id": candidate_id, "verdict": None},
        )
        return replace_projection(
            projection,
            assurances=assurances,
            current_assurance_id=assurance_id,
            assurance_started_for_current=True,
            trigger_facts=(),
        )

    if fact.id == FACT_ASSURE_SETTLED:
        _require_state(fact, projection, STATE_ASSURING)
        assurance_id = fact.field("assurance_id")
        if assurance_id != projection.current_assurance_id:
            raise conflict_error(
                "FACT-ASSURE-SETTLED references an assurance run that is not current",
                work_id=projection.work_id,
            )
        expected_fp = projection.current_candidate_fingerprint()
        actual_fp = fact.field("candidate_fingerprint")
        if actual_fp != expected_fp:
            # INV-007/INV-008: evidence non-transferable across candidates.
            raise conflict_error(
                "FACT-ASSURE-SETTLED candidate_fingerprint does not match the current "
                "candidate (INV-007/INV-008: evidence is non-transferable)",
                work_id=projection.work_id,
                expected_fingerprint=expected_fp,
                actual_fingerprint=actual_fp,
            )
        verdict = fact.field("verdict")
        assurances = tuple(
            {**item, "verdict": verdict, "settled_fact": fact.to_dict()}
            if item["assurance_id"] == assurance_id
            else item
            for item in projection.assurances
        )
        if verdict == "accepted":
            # INV-003/INV-009: only an accepted verdict may lead to ACCEPTED.
            next_state = STATE_ACCEPTED
        elif verdict == "rejected":
            if projection.attempt_number < max_attempts:
                next_state = STATE_READY
            else:
                next_state = STATE_BLOCKED
        elif verdict == "inconclusive":
            # INV-009: inconclusive MUST NOT satisfy acceptance.
            next_state = STATE_BLOCKED
        else:
            raise validation_error(f"unknown assurance verdict: {verdict!r}")
        return replace_projection(
            projection,
            state=next_state,
            assurances=assurances,
            trigger_facts=(fact.to_dict(),),
        )

    if fact.id == FACT_WORK_COMPLETED:
        _require_state(fact, projection, STATE_ACCEPTED)
        if projection.completed_confirmed:
            raise conflict_error(
                "FACT-WORK-COMPLETED already recorded", work_id=projection.work_id
            )
        return replace_projection(projection, completed_confirmed=True, trigger_facts=())

    if fact.id == FACT_WORK_BLOCKED:
        _require_state(fact, projection, STATE_BLOCKED)
        if projection.blocked_confirmed:
            raise conflict_error(
                "FACT-WORK-BLOCKED already recorded", work_id=projection.work_id
            )
        return replace_projection(
            projection,
            blocked_reason=fact.field("reason"),
            blocked_confirmed=True,
            trigger_facts=(),
        )

    if fact.id == FACT_ATTEMPT_ABANDONED:
        # STATE-DELIVERY mechanical fact sequencing item 9 (TASK-M3B-001,
        # issues #76/#95): legal only from the two resting points item 9
        # names -- an unresolved candidate-observation conflict at
        # EXECUTING, or ASSURING with the current Assurance still
        # unsettled (the operator's out-of-band judgment that it never
        # will). Consumes the blocking condition and settles the attempt
        # as failed via the identical INV-018/INV-019 arithmetic every
        # other failed-attempt row already uses -- never a verdict
        # (INV-003/INV-009 intact: no FACT-ASSURE-SETTLED accompanies it).
        conflicted = projection.state == STATE_EXECUTING and projection.candidate_conflict is not None
        unsettleable = (
            projection.state == STATE_ASSURING
            and projection.assurance_started_for_current
            and projection.assurances
            and projection.assurances[-1]["verdict"] is None
        )
        if not (conflicted or unsettleable):
            raise conflict_error(
                "FACT-ATTEMPT-ABANDONED illegal: no unresolved candidate-observation "
                "conflict and no unsettled current Assurance (STATE-DELIVERY item 9)",
                work_id=projection.work_id,
                state=projection.state,
            )
        if projection.attempt_number < max_attempts:
            next_state = STATE_READY
        else:
            next_state = STATE_BLOCKED
        assurances = projection.assurances
        if unsettleable:
            assurances = tuple(
                {**item, "verdict": "abandoned"} if item is projection.assurances[-1] else item
                for item in assurances
            )
        return replace_projection(
            projection,
            state=next_state,
            assurances=assurances,
            candidate_conflict=None,
            trigger_facts=(fact.to_dict(),),
        )

    if fact.id == FACT_WORK_CANCELLED:
        # Reserved: declared per PROTOCOL-FACTS, no v0/M0 transition row.
        raise validation_error(
            "FACT-WORK-CANCELLED has no v0/M0 transition row (STATE-DELIVERY reserved)",
            work_id=projection.work_id,
        )

    raise validation_error(f"unhandled fact id: {fact.id!r}")


def reduce(
    facts: Iterable[Fact],
    *,
    delivery_run_id: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> DeliveryProjection:
    """Fold an ordered Fact sequence for one DeliveryRun into a projection."""

    intent_id: Optional[str] = None
    works: dict[str, WorkProjection] = {}

    for fact in facts:
        if fact.delivery_run_id != delivery_run_id:
            raise validation_error(
                "fact belongs to a different delivery_run_id",
                expected=delivery_run_id,
                actual=fact.delivery_run_id,
            )
        if fact.id == FACT_INTENT_SUBMITTED:
            intent_id = fact.field("intent_id")
            continue

        work_id = fact.field("work_id")
        prior = works.get(work_id)
        works[work_id] = apply_fact(prior, fact, max_attempts=max_attempts)

    return DeliveryProjection(delivery_run_id=delivery_run_id, intent_id=intent_id, works=works)
