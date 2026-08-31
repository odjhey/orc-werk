"""The M0 orchestration loop (`TASK-M0-005`, `ORCHESTRATION-CONTRACT`,
`STATE-DELIVERY`, `M-000`).

`Orchestrator` coordinates the pure core (`orc_werk.core.reducer.reduce`,
`orc_werk.core.policy.decide`) with wired port instances
(`WorkGraphPort`, `ExecutionPort`, `CandidatePort`, `AssurancePort`,
`JournalPort`) to autonomously drive one DeliveryRun's Work items from
intent to terminal state (ACCEPTED/BLOCKED), per the M-000 goal loop:

    intent -> ready work -> dispatch attempt 1 -> candidate A ->
    assurance rejected -> retry attempt 2 -> candidate B ->
    assurance accepted -> work complete

Design (see the TASK-M0-005 PR body for the full rationale):

- **Replay is the state source** (ADR-0001, ARCH-REPOSITORY-STRUCTURE
  "self-healing boundary"): every loop iteration rebuilds the
  `DeliveryProjection` from `JournalPort.history()` via
  `orc_werk.core.reducer.reduce`. No in-memory orchestrator state is
  load-bearing across iterations.
- **Mechanics vs. policy** (`INV-011`): `FX-CREATE-WORK`, `FX-CLAIM-WORK`,
  and `FX-IDENTIFY-CANDIDATE` are dispatched without an accompanying
  Decision. Every other state-changing effect is dispatched only as the
  result of `orc_werk.core.policy.decide` returning a `PolicyOutcome`.
- **Reconciliation by idempotency key** (`INV-020`, self-healing): before
  dispatching any effect, the orchestrator checks whether an effect record
  with the same idempotency key already exists in journal history. If so,
  it reuses the recorded `dispatch_result` instead of re-invoking the
  port -- this is what makes constructing a fresh `Orchestrator` over a
  non-empty journal resume cleanly rather than re-dispatching.
- **Port-state reconciliation on construction**: a volatile port instance
  (for example a freshly-constructed `MemoryWorkGraph`/`ScriptedExecution`
  after a process restart) has lost whatever state it built up before a
  crash. `Orchestrator.__init__` replays every historical effect record
  against the wired ports (tolerating `ERR-CONFLICT` for the naturally
  non-idempotent `create`/`claim` operations) so the ports' state matches
  the durable journal before the main loop runs. A durable/persistent
  future adapter would find its own state already correct and the replay
  calls become idempotent no-ops (`ERR-CONFLICT` swallowed, `complete`/
  `block` already idempotent by design, `start`/`request` idempotent by
  idempotency key).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

from orc_werk.core.decisions import DEC_ABANDON_ATTEMPT, DEC_CANCEL, make_decision
from orc_werk.core.effects import (
    FX_BLOCK_WORK,
    FX_CLAIM_WORK,
    FX_COMPLETE_WORK,
    FX_CREATE_WORK,
    FX_IDENTIFY_CANDIDATE,
    FX_START_ASSURANCE,
    FX_START_EXECUTION,
    Effect,
    make_effect,
)
from orc_werk.core.errors import ERR_CONFLICT, CoreError, not_found_error, validation_error
from orc_werk.core.facts import (
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
    make_fact,
)
from orc_werk.core.idempotency import idempotency_key as derive_idempotency_key
from orc_werk.core.models import Candidate
from orc_werk.core.policy import decide
from orc_werk.core.reducer import DEFAULT_MAX_ATTEMPTS, apply_fact, reduce
from orc_werk.core.serialization import KIND_EFFECT, KIND_FACT, fact_from_envelope
from orc_werk.core.state import (
    STATE_ACCEPTED,
    STATE_ASSURING,
    STATE_BLOCKED,
    STATE_CANCELLED,
    STATE_EXECUTING,
    STATE_READY,
    DeliveryProjection,
    WorkProjection,
)
from orc_werk.ports.assurance import AssurancePort
from orc_werk.ports.base import LIFECYCLE_STATE_SETTLED
from orc_werk.ports.candidate import CandidatePort
from orc_werk.ports.execution import ExecutionPort
from orc_werk.ports.journal import JournalPort
from orc_werk.ports.work_graph import WorkGraphPort, validate_plan

# Default single-work plan's work_id (PORT-WORK-001's "deterministic
# single-work plan" degenerate form). Not normative -- an app-layer
# convenience default; callers may always supply an explicit multi-work
# plan (needed for SCN-005 fan-in).
DEFAULT_WORK_ID = "work-1"

# Safety bound on loop iterations so a genuine orchestrator/policy defect
# (an infinite no-progress oscillation) fails loudly instead of hanging
# forever. Golden scenarios need only a handful of iterations.
DEFAULT_MAX_ITERATIONS = 2_000


def default_single_work_plan(work_id: str = DEFAULT_WORK_ID) -> dict[str, Any]:
    """The `PORT-WORK-001` degenerate single-work plan shape."""
    return {"works": [{"work_id": work_id, "deps": []}]}


@dataclass(frozen=True)
class RunConfig:
    """Policy/config knobs for one `Orchestrator` run.

    `resume_capability`: when set (e.g. `CAP-EXEC-RESUME-EXACT` from
    `orc_werk.ports.capabilities`), every dispatch of a Work's Execution
    (`DEC-DISPATCH` and `DEC-RETRY`) is carried out via
    `ExecutionPort.resume` with that capability, instead of
    `ExecutionPort.start` (`PORT-EXEC-005`, `SCN-006`). `PROTOCOL-EFFECTS`
    has no distinct resume effect id, so this still dispatches as
    `FX-START-EXECUTION` -- only the underlying port call differs; see the
    PR body's "Ambiguities encountered" for why.
    """

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    resume_capability: Optional[str] = None


def _is_confirmed_terminal(wp: WorkProjection) -> bool:
    if wp.state == STATE_ACCEPTED:
        return wp.completed_confirmed
    if wp.state == STATE_BLOCKED:
        return wp.blocked_confirmed
    if wp.state == STATE_CANCELLED:
        return wp.cancelled_confirmed
    return False


def is_pending(wp: WorkProjection) -> bool:
    """`TASK-M1-002`/`SCN-007`: true when `wp` is resting at
    `EXECUTING`/`ASSURING` because the current attempt's outcome (an
    Execution settlement, or an Assurance verdict) has not been observed
    yet -- `STATE-DELIVERY` mechanical fact sequencing item 7 ("absence of
    a settlement observation is not a settlement"). Distinct from
    `BLOCKED` (a confirmed terminal outcome) and from a dispatch-gate
    failure (item 6: an unsupported capability or unavailable provider
    settles immediately as a failed attempt, never pending). Mirrors the
    exact predicates `Orchestrator._poll_execution`/`_poll_assurance` use
    to decide whether there is anything new to journal."""
    if wp.state == STATE_EXECUTING:
        current = next(
            (item for item in wp.executions if item["execution_id"] == wp.current_execution_id), None
        )
        return current is not None and current["outcome"] is None
    if wp.state == STATE_ASSURING and wp.assurance_started_for_current:
        current = wp.assurances[-1] if wp.assurances else None
        return current is not None and current["verdict"] is None
    return False


def has_candidate_conflict(wp: WorkProjection) -> bool:
    """`TASK-M3B-001`/`STATE-DELIVERY` item 9: true when `wp` rests at
    `EXECUTING` with an unresolved candidate-observation conflict (a
    re-observed candidate identity `SCN-009`'s verdict-inheritance rule
    could not resolve) -- a second, distinct normal resting point,
    disjoint from `is_pending`. Legal grounds for `Orchestrator.
    abandon_attempt`, alongside `is_pending`'s `ASSURING` case."""
    return wp.state == STATE_EXECUTING and wp.candidate_conflict is not None


def _find_effect_record(
    history: Sequence[Mapping[str, Any]], idempotency_key: str
) -> Optional[Mapping[str, Any]]:
    for record in history:
        if record.get("kind") != KIND_EFFECT:
            continue
        if record.get("data", {}).get("idempotency_key") == idempotency_key:
            return record
    return None


def _predicted_resume_execution_id(work_id: str) -> str:
    """Deterministic placeholder execution reference used when
    `RunConfig.resume_capability` is exercised on a Work's very first
    attempt (no prior Execution identity exists yet to resume). Stable,
    replay-safe (INV-020): a pure function of `work_id` only."""
    digest = hashlib.sha256(f"resume-target|{work_id}".encode("utf-8")).hexdigest()[:16]
    return f"resume-target-{digest}"


class Orchestrator:
    """Drives one DeliveryRun's Work items to terminal state by
    interpreting core Decisions/Effects against wired ports and journaling
    the resulting canonical Facts/Decisions/Effect-records."""

    def __init__(
        self,
        *,
        delivery_run_id: str,
        journal: JournalPort,
        work_graph: WorkGraphPort,
        execution: ExecutionPort,
        candidate: CandidatePort,
        assurance: AssurancePort,
        config: Optional[RunConfig] = None,
    ) -> None:
        self.delivery_run_id = delivery_run_id
        self.journal = journal
        self.work_graph = work_graph
        self.execution = execution
        self.candidate = candidate
        self.assurance = assurance
        self.config = config or RunConfig()
        # At most one candidate-identification call per logical effect in a
        # single dispatch; a later dispatch resets this transient guard and
        # retries null observations from durable journal state (SCN-014).
        self._identification_attempted: set[str] = set()
        # Self-healing: rebuild any volatile port-side state a fresh port
        # instance lost across a restart from durable journal history
        # (ARCH-REPOSITORY-STRUCTURE "self-healing boundary").
        self._reconcile_ports()

    # -- construction-time port reconciliation ------------------------------

    def _reconcile_ports(self) -> None:
        history = self.journal.history(delivery_run_id=self.delivery_run_id)
        if not history:
            return
        facts = [fact_from_envelope(r) for r in history if r["kind"] == KIND_FACT]
        projection = reduce(
            facts, delivery_run_id=self.delivery_run_id, max_attempts=self.config.max_attempts
        )
        for record in history:
            if record["kind"] != KIND_EFFECT:
                continue
            self._replay_effect_record(record, projection)

    def _replay_effect_record(
        self, record: Mapping[str, Any], projection: DeliveryProjection
    ) -> None:
        effect_id = record["id"]
        data = record["data"]
        dispatch_result = data.get("dispatch_result", {})
        if isinstance(dispatch_result, Mapping) and "error" in dispatch_result:
            return  # a failed dispatch touched no durable port-side state.
        work_id = data.get("work_id")

        if effect_id == FX_CREATE_WORK:
            plan = data.get("plan")
            self._tolerate_conflict(
                lambda: self.work_graph.create(delivery_run_id=self.delivery_run_id, plan=plan)
            )
        elif effect_id == FX_CLAIM_WORK:
            self._tolerate_conflict(lambda: self.work_graph.claim(work_id=work_id))
        elif effect_id == FX_COMPLETE_WORK:
            self.work_graph.complete(work_id=work_id)  # PORT-WORK-005: idempotent.
        elif effect_id == FX_BLOCK_WORK:
            reason = data.get("reason", dispatch_result.get("reason", ""))
            self.work_graph.block(work_id=work_id, reason=reason)  # idempotent, same reason.
        elif effect_id == FX_START_EXECUTION:
            via = dispatch_result.get("via")
            if via == "resume":
                execution_id = dispatch_result.get("execution_id")
                if execution_id and self.config.resume_capability:
                    self.execution.resume(
                        execution_id=execution_id,
                        resume_request={"capability": self.config.resume_capability},
                    )
            else:
                self.execution.start(
                    work_id=work_id,
                    execution_request={},
                    idempotency_key=data["idempotency_key"],
                )
        elif effect_id == FX_START_ASSURANCE:
            candidate_id = data.get("candidate_id")
            fingerprint = data.get("candidate_fingerprint")
            candidate = self._reconstruct_candidate(projection, work_id, candidate_id, fingerprint)
            self.assurance.request(
                candidate=candidate, requirements={}, idempotency_key=data["idempotency_key"]
            )
        # FX_IDENTIFY_CANDIDATE: CandidatePort.identify is a stateless
        # function of execution_id for the M0 scripted/memory adapters --
        # no port-side state to rebuild by replaying it.

    @staticmethod
    def _tolerate_conflict(fn: Callable[[], Any]) -> None:
        try:
            fn()
        except CoreError as exc:
            if exc.error.get("error") != ERR_CONFLICT:
                raise

    @staticmethod
    def _reconstruct_candidate(
        projection: DeliveryProjection,
        work_id: Optional[str],
        candidate_id: Optional[str],
        fingerprint: Optional[str],
    ) -> Candidate:
        execution_id = ""
        wp = projection.works.get(work_id) if work_id else None
        if wp is not None and candidate_id in wp.candidates:
            execution_id = wp.candidates[candidate_id].get("execution_id", "")
        return Candidate(
            id=candidate_id or "",
            work_id=work_id or "",
            execution_id=execution_id,
            subject_identity=None,
            fingerprint=fingerprint or "",
        )

    # -- bootstrap (INV-011 mechanics: no Decision) --------------------------

    def bootstrap(
        self,
        *,
        intent_id: str,
        text: str,
        plan: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Journal `FACT-INTENT-SUBMITTED`, dispatch `FX-CREATE-WORK`
        (mechanical, INV-011), and journal `FACT-WORK-CREATED` for each
        planned Work. `FACT-WORK-READY`/`FACT-WORK-CLAIMED` are left to the
        main loop's ready+claim step (`_claim_ready_work`) so the initial
        and later-unlocked (fan-in, SCN-005) cases share one code path.

        A no-op when the journal is already non-empty (resume path)."""
        if self.journal.history(delivery_run_id=self.delivery_run_id):
            return

        self.journal.append_fact(
            make_fact(
                FACT_INTENT_SUBMITTED, delivery_run_id=self.delivery_run_id, intent_id=intent_id, text=text
            )
        )

        resolved_plan = dict(plan) if plan is not None else default_single_work_plan()
        validate_plan(resolved_plan)

        effect = make_effect(
            FX_CREATE_WORK,
            delivery_run_id=self.delivery_run_id,
            work_id="",
            idempotency_key=derive_idempotency_key(FX_CREATE_WORK, delivery_run_id=self.delivery_run_id),
            # `data.max_attempts` alongside `data.plan`, issue #52: the
            # run's effective retry budget becomes durable journal state,
            # exactly mirroring the ratified topology-durability precedent
            # (issue #41) so PORT-JOURNAL-005 replay is self-sufficient --
            # a faithful replay must fold under the same policy parameters
            # the run used (CONTRACT-DURABILITY's topology/budget row).
            data={"plan": resolved_plan, "max_attempts": self.config.max_attempts},
        )
        try:
            created = self.work_graph.create(delivery_run_id=self.delivery_run_id, plan=resolved_plan)
            dispatch_result: dict[str, Any] = {"works": [w.to_dict() for w in created]}
        except CoreError as exc:
            dispatch_result = exc.to_canonical()
        self.journal.append_effect_record(effect, dispatch_result=dispatch_result)

        if "error" in dispatch_result:
            raise CoreError(dispatch_result)

        for work_entry in resolved_plan["works"]:
            self.journal.append_fact(
                make_fact(
                    FACT_WORK_CREATED,
                    delivery_run_id=self.delivery_run_id,
                    work_id=work_entry["work_id"],
                )
            )

    # -- main loop ------------------------------------------------------------

    def projection(self) -> DeliveryProjection:
        history = self.journal.history(delivery_run_id=self.delivery_run_id)
        facts = [fact_from_envelope(r) for r in history if r["kind"] == KIND_FACT]
        return reduce(facts, delivery_run_id=self.delivery_run_id, max_attempts=self.config.max_attempts)

    def step(self) -> bool:
        """Perform at most one phase's worth of progress (claim/ready, poll
        a settlement, or advance a policy decision) and return whether any
        progress was made. `run()` is `step()` called in a loop; exposed
        separately so callers (notably crash-resume tests) can advance a
        DeliveryRun a bounded number of steps and then simulate a restart
        mid-flight -- constructing a fresh `Orchestrator` over the same
        journal and calling `run()` again must reach the identical terminal
        outcome with no duplicated effects (INV-020)."""
        projection = self.projection()
        if self._all_terminal(projection):
            return False
        return self._advance_one_phase(projection)

    def _advance_one_phase(self, projection: DeliveryProjection) -> bool:
        if self._claim_ready_work(projection):
            return True
        if self._poll_settlements(projection):
            return True
        if self._advance_policy(projection):
            return True
        return False

    def run(self, *, max_iterations: int = DEFAULT_MAX_ITERATIONS) -> DeliveryProjection:
        """Advance the DeliveryRun until every Work is terminal
        (ACCEPTED/BLOCKED, confirmed) or no further progress is possible.
        Every iteration replays the journal from scratch -- replay IS the
        state source (ADR-0001)."""
        self._identification_attempted.clear()
        projection = self.projection()
        for _ in range(max_iterations):
            if self._all_terminal(projection):
                return projection
            if not self._advance_one_phase(projection):
                # No progress possible this pass (e.g. genuinely blocked on
                # an external settlement, or a candidate that never
                # materializes).
                return projection
            projection = self.projection()
        raise RuntimeError(
            f"orchestrator exceeded max_iterations={max_iterations} without reaching a stable state "
            f"(delivery_run_id={self.delivery_run_id!r})"
        )

    @staticmethod
    def _all_terminal(projection: DeliveryProjection) -> bool:
        if not projection.works:
            return False
        return all(_is_confirmed_terminal(wp) for wp in projection.works.values())

    # -- phase 1: ready + claim (mechanical, once per Work lineage) ---------

    def _claim_ready_work(self, projection: DeliveryProjection) -> bool:
        progressed = False
        for work in self.work_graph.ready(delivery_run_id=self.delivery_run_id):
            wp = projection.works.get(work.id)
            if wp is None or wp.state != STATE_READY or wp.claim_ref is not None:
                continue

            # INV-020 reduced form for FX-CLAIM-WORK: (delivery_run_id,
            # work_id, effect_id) -- once per Work lineage, no
            # attempt_number component.
            claim_key = derive_idempotency_key(
                FX_CLAIM_WORK, delivery_run_id=self.delivery_run_id, work_id=work.id
            )
            history = self.journal.history(delivery_run_id=self.delivery_run_id)
            existing = _find_effect_record(history, claim_key)
            if existing is not None:
                dispatch_result = existing["data"].get("dispatch_result", {})
            else:
                effect = make_effect(
                    FX_CLAIM_WORK,
                    delivery_run_id=self.delivery_run_id,
                    work_id=work.id,
                    idempotency_key=claim_key,
                )
                try:
                    claim = self.work_graph.claim(work_id=work.id)
                    dispatch_result = dict(claim)
                except CoreError as exc:
                    dispatch_result = exc.to_canonical()
                self.journal.append_effect_record(effect, dispatch_result=dispatch_result)

            if "error" in dispatch_result:
                # Nothing mechanically actionable here (M0: no scenario
                # exercises a claim race); leave it for a later pass/operator.
                continue

            self.journal.append_fact(
                make_fact(
                    FACT_WORK_CLAIMED,
                    delivery_run_id=self.delivery_run_id,
                    work_id=work.id,
                    claim_ref=dispatch_result["claim_ref"],
                )
            )
            self.journal.append_fact(
                make_fact(FACT_WORK_READY, delivery_run_id=self.delivery_run_id, work_id=work.id)
            )
            progressed = True
        return progressed

    # -- phase 2: poll in-flight settlements (mechanical normalization) -----

    def _poll_settlements(self, projection: DeliveryProjection) -> bool:
        progressed = False
        for work_id, wp in projection.works.items():
            if wp.state == STATE_EXECUTING:
                if self._poll_execution(work_id, wp):
                    progressed = True
            elif wp.state == STATE_ASSURING and wp.assurance_started_for_current:
                if self._poll_assurance(work_id, wp):
                    progressed = True
        return progressed

    def _poll_execution(self, work_id: str, wp: WorkProjection) -> bool:
        current = next(
            (item for item in wp.executions if item["execution_id"] == wp.current_execution_id), None
        )
        if current is None:
            return False
        if current["outcome"] == "completed" and wp.current_candidate_id is None:
            # STATE-DELIVERY item 9 / SCN-014: a prior null candidate
            # identification is non-binding. A later dispatch retries the
            # same logical effect and reports progress only if it binds.
            return self._identify_candidate(work_id, wp.current_execution_id, wp.attempt_number)
        if current["outcome"] is not None:
            return False
        observation = self.execution.inspect(execution_id=wp.current_execution_id)
        if observation.state != LIFECYCLE_STATE_SETTLED:
            return False
        self.journal.append_fact(
            make_fact(
                FACT_EXEC_SETTLED,
                delivery_run_id=self.delivery_run_id,
                work_id=work_id,
                execution_id=wp.current_execution_id,
                outcome=observation.outcome,
                # CONF-EXT-003: transport ExecutionObservation.extensions
                # losslessly into the journal envelope -- the orchestrator
                # never inspects/branches on them (CONF-EXT-006), only
                # carries them through.
                extensions=dict(observation.extensions),
            )
        )
        if observation.outcome == "completed":
            self._identify_candidate(work_id, wp.current_execution_id, wp.attempt_number)
        return True

    def _poll_assurance(self, work_id: str, wp: WorkProjection) -> bool:
        current = wp.assurances[-1] if wp.assurances else None
        if current is None or current["verdict"] is not None:
            return False
        observation = self.assurance.inspect(assurance_id=wp.current_assurance_id)
        if observation.state != LIFECYCLE_STATE_SETTLED:
            return False
        self.journal.append_fact(
            make_fact(
                FACT_ASSURE_SETTLED,
                delivery_run_id=self.delivery_run_id,
                work_id=work_id,
                assurance_id=wp.current_assurance_id,
                candidate_fingerprint=observation.candidate_fingerprint,
                verdict=observation.verdict,
                **(
                    {"evidence_refs": list(observation.evidence_refs)}
                    if observation.evidence_refs
                    else {}
                ),
                # CONF-EXT-003: transport AssuranceObservation.extensions
                # losslessly (e.g. EXT-REVIEW-FINDINGS-V1); CONF-EXT-006:
                # never inspected/branched on here.
                extensions=dict(observation.extensions),
            )
        )
        return True

    def _identify_candidate(self, work_id: str, execution_id: str, attempt_number: int) -> bool:
        """Mechanical `FX-IDENTIFY-CANDIDATE` step (INV-011: no Decision).

        Return whether a candidate Fact bound. A null PORT-CAND-001 result
        is non-binding and is retried on a subsequent dispatch (SCN-014).
        """
        key = derive_idempotency_key(
            FX_IDENTIFY_CANDIDATE,
            delivery_run_id=self.delivery_run_id,
            work_id=work_id,
            attempt_number=attempt_number,
        )
        if key in self._identification_attempted:
            return False
        self._identification_attempted.add(key)
        history = self.journal.history(delivery_run_id=self.delivery_run_id)
        existing = _find_effect_record(history, key)
        dispatch_result = existing["data"].get("dispatch_result", {}) if existing is not None else {}
        # A successful prior result is reconciled by key. A null result is
        # explicitly non-binding, so re-dispatch invokes the adapter again
        # with the same logical-effect key (INV-020), like settlement re-poll.
        if existing is None or dispatch_result.get("candidate") is None:
            try:
                found = self.candidate.identify(execution_id=execution_id)
                dispatch_result = {"candidate": found.to_dict() if found is not None else None}
            except CoreError as exc:
                dispatch_result = exc.to_canonical()
            effect = make_effect(
                FX_IDENTIFY_CANDIDATE,
                delivery_run_id=self.delivery_run_id,
                work_id=work_id,
                idempotency_key=key,
                data={"execution_id": execution_id},
            )
            self.journal.append_effect_record(effect, dispatch_result=dispatch_result)

        candidate_data = dispatch_result.get("candidate") if isinstance(dispatch_result, Mapping) else None
        if candidate_data:
            self.journal.append_fact(
                make_fact(
                    FACT_CANDIDATE_OBSERVED,
                    delivery_run_id=self.delivery_run_id,
                    work_id=work_id,
                    candidate_id=candidate_data["id"],
                    fingerprint=candidate_data["fingerprint"],
                    execution_id=execution_id,
                )
            )
            return True
        # PORT-CAND-001: no assurable subject is a non-binding observation.
        return False

    # -- operator surface: abandon (TASK-M3B-001, issues #76/#95) -----------

    def _find_fact_record(
        self, history: Sequence[Mapping[str, Any]], fact_id: str, *, work_id: str, **match: Any
    ) -> Optional[Mapping[str, Any]]:
        found: Optional[Mapping[str, Any]] = None
        for record in history:
            if record.get("kind") != KIND_FACT or record.get("id") != fact_id:
                continue
            data = record.get("data", {})
            if data.get("work_id") != work_id:
                continue
            if any(data.get(key) != value for key, value in match.items()):
                continue
            found = record  # last match wins -- history is seq-ordered ascending.
        return found

    def abandon_attempt(self, *, work_id: str, reason: str, by: str) -> None:
        """Operator-only recording surface (`docs/playbooks/cli-usage.md`,
        never the ship/verify agent path): journals `DEC-ABANDON-ATTEMPT` +
        `FACT-ATTEMPT-ABANDONED` for `work_id` (`STATE-DELIVERY` mechanical
        fact sequencing item 9). Legal only when the Work currently rests
        at an unresolved candidate-observation conflict
        (`has_candidate_conflict`) or at `ASSURING` with its current
        Assurance still unsettled (`is_pending`) -- anything else raises
        `ERR-VALIDATION`, never silently no-ops. `reason`/`by` become the
        Decision's `data`/`attribution` (`INV-011`/`INV-012`); the Fact
        itself only carries `reason` (mirrors `FACT-WORK-BLOCKED`'s
        shape -- `PROTOCOL-FACTS`)."""
        projection = self.projection()
        wp = projection.works.get(work_id)
        if wp is None:
            raise not_found_error(
                f"no such work in run {self.delivery_run_id!r}: {work_id!r}",
                work_id=work_id,
                next_steps=[f"orc status {self.delivery_run_id}"],
            )
        history = self.journal.history(delivery_run_id=self.delivery_run_id)
        if has_candidate_conflict(wp):
            basis: tuple[Mapping[str, Any], ...] = (dict(wp.candidate_conflict["fact"]),)
        elif (
            wp.state == STATE_EXECUTING
            and wp.current_candidate_id is None
            and wp.executions
            and wp.executions[-1].get("outcome") == "completed"
        ):
            settled = self._find_fact_record(
                history, FACT_EXEC_SETTLED, work_id=work_id, execution_id=wp.current_execution_id
            )
            basis = (dict(settled),) if settled is not None else ({"work_id": work_id},)
        elif wp.state == STATE_ASSURING and is_pending(wp):
            started = self._find_fact_record(
                history, FACT_ASSURE_STARTED, work_id=work_id, assurance_id=wp.current_assurance_id
            )
            basis = (dict(started),) if started is not None else ({"work_id": work_id},)
        else:
            raise validation_error(
                f"FACT-ATTEMPT-ABANDONED illegal for work {work_id!r} in state {wp.state!r}: "
                "no unresolved candidate-observation conflict, settled execution awaiting "
                "candidate, or unsettled current assurance (STATE-DELIVERY item 9)",
                work_id=work_id,
                state=wp.state,
                next_steps=[f"orc status {self.delivery_run_id}"],
            )
        decision = make_decision(
            DEC_ABANDON_ATTEMPT,
            delivery_run_id=self.delivery_run_id,
            work_id=work_id,
            attribution={"operator": by},
            basis=list(basis),
            data={"reason": reason},
        )
        self.journal.append_decision(decision)
        self.journal.append_fact(
            make_fact(
                FACT_ATTEMPT_ABANDONED,
                delivery_run_id=self.delivery_run_id,
                work_id=work_id,
                reason=reason,
            )
        )

    def cancel_work(self, *, work_id: str, reason: str, by: str) -> None:
        """Operator-only terminal closure (`STATE-DELIVERY` item 10).

        Records `DEC-CANCEL` and `FACT-WORK-CANCELLED` without dispatching a
        port Effect. The reducer preflight supplies the canonical conflict
        for terminal Work before either record is appended.
        """
        projection = self.projection()
        wp = projection.works.get(work_id)
        if wp is None:
            raise not_found_error(
                f"no such work in run {self.delivery_run_id!r}: {work_id!r}",
                work_id=work_id,
                next_steps=[f"orc status {self.delivery_run_id}"],
            )
        fact = make_fact(
            FACT_WORK_CANCELLED,
            delivery_run_id=self.delivery_run_id,
            work_id=work_id,
            reason=reason,
        )
        apply_fact(wp, fact, max_attempts=self.config.max_attempts)
        history = self.journal.history(delivery_run_id=self.delivery_run_id)
        basis_record = next(
            (
                record
                for record in reversed(history)
                if record.get("kind") == KIND_FACT
                and record.get("data", {}).get("work_id") == work_id
            ),
            None,
        )
        basis = [dict(basis_record)] if basis_record is not None else [wp.to_dict()]
        self.journal.append_decision(
            make_decision(
                DEC_CANCEL,
                delivery_run_id=self.delivery_run_id,
                work_id=work_id,
                attribution={"operator": by},
                basis=basis,
                data={"reason": reason},
            )
        )
        self.journal.append_fact(fact)

    # -- phase 3: policy decisions --------------------------------------------

    def _advance_policy(self, projection: DeliveryProjection) -> bool:
        progressed = False
        history = self.journal.history(delivery_run_id=self.delivery_run_id)
        for work_id, wp in projection.works.items():
            if _is_confirmed_terminal(wp):
                continue
            if self._apply_decision(wp, history):
                progressed = True
                history = self.journal.history(delivery_run_id=self.delivery_run_id)
        return progressed

    def _apply_decision(self, wp: WorkProjection, history: Sequence[Mapping[str, Any]]) -> bool:
        outcome = decide(wp, max_attempts=self.config.max_attempts)
        if outcome is None:
            return False
        effect = outcome.effects[0]  # v0 policy: exactly one effect per Decision.
        existing = _find_effect_record(history, effect.idempotency_key)
        if existing is not None:
            dispatch_result = existing["data"].get("dispatch_result", {})
        else:
            self.journal.append_decision(outcome.decision)
            dispatch_result = self._dispatch_policy_effect(effect, wp)
            self.journal.append_effect_record(effect, dispatch_result=dispatch_result)
        self._apply_policy_dispatch_result(wp, effect, dispatch_result)
        return True

    def _dispatch_policy_effect(self, effect: Effect, wp: WorkProjection) -> dict[str, Any]:
        try:
            if effect.id == FX_START_EXECUTION:
                return self._start_or_resume_execution(wp, effect)
            if effect.id == FX_START_ASSURANCE:
                candidate = self._current_candidate(wp)
                run = self.assurance.request(
                    candidate=candidate, requirements={}, idempotency_key=effect.idempotency_key
                )
                return {"assurance_id": run.id}
            if effect.id == FX_COMPLETE_WORK:
                work = self.work_graph.complete(work_id=wp.work_id)
                return {"work_id": work.id}
            if effect.id == FX_BLOCK_WORK:
                reason = effect.data.get("reason", "")
                work = self.work_graph.block(work_id=wp.work_id, reason=reason)
                return {"work_id": work.id, "reason": reason}
        except CoreError as exc:
            return exc.to_canonical()
        raise AssertionError(f"unexpected v0 policy effect id: {effect.id!r}")

    def _start_or_resume_execution(self, wp: WorkProjection, effect: Effect) -> dict[str, Any]:
        if self.config.resume_capability:
            execution_id = wp.current_execution_id or _predicted_resume_execution_id(wp.work_id)
            execution = self.execution.resume(
                execution_id=execution_id,
                resume_request={"capability": self.config.resume_capability},
            )
            return {"execution_id": execution.id, "via": "resume"}
        execution = self.execution.start(
            work_id=wp.work_id, execution_request={}, idempotency_key=effect.idempotency_key
        )
        return {"execution_id": execution.id, "via": "start"}

    @staticmethod
    def _current_candidate(wp: WorkProjection) -> Candidate:
        candidate_id = wp.current_candidate_id
        entry = wp.candidates[candidate_id]
        return Candidate(
            id=candidate_id,
            work_id=wp.work_id,
            execution_id=entry["execution_id"],
            subject_identity=None,
            fingerprint=entry["fingerprint"],
        )

    def _apply_policy_dispatch_result(
        self, wp: WorkProjection, effect: Effect, dispatch_result: Mapping[str, Any]
    ) -> None:
        delivery_run_id = self.delivery_run_id
        work_id = wp.work_id

        if effect.id == FX_START_EXECUTION:
            if "error" in dispatch_result:
                # INV-013/SCN-006: the port refused the required capability.
                # STATE-DELIVERY has no direct "dispatch failed" transition;
                # the least-commitment mapping that reuses only legal
                # reducer transitions is to record this as an Execution
                # attempt that started and immediately settled failed, so
                # normal retry-budget/BLOCK machinery takes over next pass
                # (see the PR body's "Ambiguities encountered").
                attempt_number = effect.data["attempt_number"]
                # #16 item 3: this prefix used to say "capability-failure"
                # for every dispatch-gate failure regardless of actual
                # cause (misleading when grepping history for a genuine
                # capability mismatch) -- renamed cause-neutral.
                # STATE-DELIVERY item 6 only requires "a unique synthetic
                # execution reference", pinning no literal text (grepped
                # docs/ to confirm before renaming); the reference is
                # opaque and nothing parses its contents, so old journals
                # carrying the previous "exec-capability-failure-..." form
                # still replay identically.
                synthetic_execution_id = (
                    f"exec-dispatch-failure-{delivery_run_id}-{work_id}-{attempt_number}"
                )
                self.journal.append_fact(
                    make_fact(
                        FACT_EXEC_STARTED,
                        delivery_run_id=delivery_run_id,
                        work_id=work_id,
                        execution_id=synthetic_execution_id,
                    )
                )
                self.journal.append_fact(
                    make_fact(
                        FACT_EXEC_SETTLED,
                        delivery_run_id=delivery_run_id,
                        work_id=work_id,
                        execution_id=synthetic_execution_id,
                        outcome="failed",
                    )
                )
                return
            execution_id = dispatch_result["execution_id"]
            self.journal.append_fact(
                make_fact(
                    FACT_EXEC_STARTED,
                    delivery_run_id=delivery_run_id,
                    work_id=work_id,
                    execution_id=execution_id,
                )
            )
            return

        if effect.id == FX_START_ASSURANCE:
            if "error" in dispatch_result:
                raise CoreError(dict(dispatch_result))  # not exercised by any M0 scenario.
            assurance_id = dispatch_result["assurance_id"]
            candidate_id = effect.data["candidate_id"]
            self.journal.append_fact(
                make_fact(
                    FACT_ASSURE_STARTED,
                    delivery_run_id=delivery_run_id,
                    work_id=work_id,
                    assurance_id=assurance_id,
                    candidate_id=candidate_id,
                )
            )
            return

        if effect.id == FX_COMPLETE_WORK:
            if "error" in dispatch_result:
                raise CoreError(dict(dispatch_result))
            self.journal.append_fact(
                make_fact(FACT_WORK_COMPLETED, delivery_run_id=delivery_run_id, work_id=work_id)
            )
            return

        if effect.id == FX_BLOCK_WORK:
            if "error" in dispatch_result:
                raise CoreError(dict(dispatch_result))
            reason = effect.data.get("reason", "")
            self.journal.append_fact(
                make_fact(
                    FACT_WORK_BLOCKED, delivery_run_id=delivery_run_id, work_id=work_id, reason=reason
                )
            )
            return


__all__ = [
    "DEFAULT_WORK_ID",
    "DEFAULT_MAX_ITERATIONS",
    "Orchestrator",
    "RunConfig",
    "default_single_work_plan",
    "has_candidate_conflict",
    "is_pending",
]
