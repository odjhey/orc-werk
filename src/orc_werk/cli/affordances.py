"""HATEOAS-style per-state affordance mapping (issue #43's watchtower
reframe of the "next-step hints" item -- the organizing principle for the
whole CLI-UX round).

The delivery state machine (`STATE-DELIVERY`,
`docs/domain/state-machines/delivery.md`) IS the hypermedia map: this
module owns the single per-state -> "next:" text mapping that `orc
dispatch`/`orc status` render from. A new transition in that state machine
must force the affordance question here -- there must be no hand-scattered
"next:" string anywhere else in this CLI.

Per-state map (issue #43, second watchtower comment; the `CANDIDATE-CONFLICT`
row is `TASK-M3B-001`, `STATE-DELIVERY` mechanical fact sequencing item 9):

| Work state                         | Affordance                                                              |
|-------------------------------------|--------------------------------------------------------------------------|
| PENDING @ EXECUTING (`is_pending`)  | record the execution outcome, then re-dispatch (exact command)          |
| PENDING @ ASSURING  (`is_pending`)  | record the assurance verdict -- a different agent than the settlement recorder (playbook discipline), then re-dispatch |
| AWAITING-CANDIDATE @ EXECUTING (`abandon_legality(...).awaiting_candidate`, issue #244/SCN-014) | candidate identification returned no subject -- ensure `candidate.repo_path` exists and re-dispatch (re-derivation is automatic) |
| CANDIDATE-CONFLICT @ EXECUTING (`has_candidate_conflict`) | operator-only: `orc dispatch --abandon-work <id> --abandon-reason "<why>"` (`TASK-M3B-001`) -- verdict inheritance could not resolve this re-observed candidate |
| BLOCKED                             | `orc history <run>` root-cause pointer + retry-budget note              |
| ACCEPTED                            | `orc report <run>` (+ `gh pr view <n>` when the candidate carries a `pr` field) |
| READY                               | no affordance -- not actionable by an agent; the kernel dispatches it   |

`ERR-NOT-FOUND(run)` (definitive available-runs list + dispatch affordance)
is handled at the point that error is raised
(`orc_werk.cli.journal_reading._require_journal_file`), not here -- there is
no `WorkProjection` to key off when the run itself was never found.

Multi-work runs: works sharing the *same* next-step guidance are grouped
into one bullet naming every matching work id, rather than repeating an
identical sentence once per work -- the guidance ("record the execution
outcome for work X") is otherwise textually redundant across works in the
same state, and a long fan-out/fan-in run could otherwise bury the one
distinct re-dispatch command under many copies of the same sentence.

Presentation-only, CLI-owned composition (CLAUDE.md #6/#7): reads
`WorkProjection`/journal history the same way `status`/`dispatch`/`report`
already do, invents no new canonical semantics, and records nothing.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.jsonl import layout
from orc_werk.app.orchestrator import has_candidate_conflict, is_pending
from orc_werk.cli.journal_reading import (
    BLOCKED_REASON_ASSURANCE_INCONCLUSIVE,
    BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED,
    _awaiting_label,
)
from orc_werk.core.decisions import DEC_BLOCK, DEC_REQUEST_ASSURANCE
from orc_werk.core.reducer import abandon_legality
from orc_werk.core.state import (
    STATE_ACCEPTED,
    STATE_ASSURING,
    STATE_BLOCKED,
    STATE_EXECUTING,
    DeliveryProjection,
    WorkProjection,
)

_PLACEHOLDER_INTENT = "<intent text>"
_PLACEHOLDER_CONFIG = "<path-to-dispatch-config.json>"


def redispatch_command(
    *,
    intent_text: Optional[str],
    config_path: Optional[Path],
    journal_dir: Path,
    run_id: str,
) -> str:
    """The exact `orc dispatch` invocation that resumes this run
    (`docs/playbooks/agent-cli-usage.md` protocol step 4: "Re-dispatch...
    This is always safe"). Absolute journal dir and an explicit `--run-id`
    (never relies on the intent-text hash re-deriving the same id) are
    always concrete; `intent_text` renders as a bracketed placeholder only
    when the caller genuinely does not know it (e.g. `orc status` was never
    given a `--config`) rather than fabricating a value -- CLAUDE.md #3,
    "do not invent missing semantics in code".

    `config_path` -- the caller's own, possibly ephemeral `--config`
    argument -- is used only as a last-resort fallback. Issue #55 H2's
    config persistence means any run dispatched at least once already has
    its effective config durably copied to
    `<journal_dir>/<run_id>/config.json`; when that file exists, the
    affordance names IT instead, per the operator ruling that a
    re-dispatch `next:` command "must reference the durable in-run-dir
    config path, not the caller's ephemeral path" -- a path only the
    invoking session may have had (a scratchpad file, a path on someone
    else's machine) is not something a *different*, later reader of this
    affordance can rely on."""
    intent_token = shlex.quote(intent_text) if intent_text is not None else _PLACEHOLDER_INTENT
    persisted_config = layout.config_path(journal_dir, run_id)
    if persisted_config.exists():
        config_token = str(persisted_config)
    elif config_path is not None:
        config_token = str(config_path)
    else:
        config_token = _PLACEHOLDER_CONFIG
    return (
        f"orc dispatch {intent_token} --config {config_token} "
        f"--journal {journal_dir} --run-id {run_id}"
    )


def _resolved_config_token(*, config_path: Optional[Path], journal_dir: Path, run_id: str) -> str:
    """The same persisted-config-preferred precedence `redispatch_command`
    already documents (issue #55 H2): a run dispatched at least once has
    its effective config durably copied to `<journal_dir>/<run_id>/
    config.json`, which every later reader can rely on regardless of
    which (possibly ephemeral, possibly another session's) `--config` path
    invoked this dispatch. Used by affordance lines that name a concrete
    `orc dispatch ... --config <path>` command outside of
    `redispatch_command` itself (e.g. the `--abandon-work` escape hatch)."""
    persisted_config = layout.config_path(journal_dir, run_id)
    if persisted_config.exists():
        return str(persisted_config)
    if config_path is not None:
        return str(config_path)
    return str(journal_dir / run_id / "config.json")


def _block_budget(history: Sequence[Mapping[str, Any]], work_id: str) -> Optional[tuple[Any, Any]]:
    """`(attempt_number, max_attempts)` from this Work's most recent
    `DEC-BLOCK` decision (`core/policy.py`'s `state_basis`), or `None` if
    this Work never blocked. `history` is `seq`-ordered ascending, so the
    last match is the most recent."""
    result: Optional[tuple[Any, Any]] = None
    for record in history:
        if record.get("kind") != "decision" or record.get("id") != DEC_BLOCK:
            continue
        data = record.get("data", {})
        if data.get("work_id") != work_id:
            continue
        result = (data.get("attempt_number"), data.get("max_attempts"))
    return result


def _block_assurance_budget(
    history: Sequence[Mapping[str, Any]], work_id: str
) -> Optional[tuple[Any, Any]]:
    """`(assurance_number, max_assurance_attempts)` from this Work's most
    recent `DEC-BLOCK` (`INV-021`, `core/policy.py`'s `state_basis`), or
    `None` for a Work that never blocked or whose block predates
    `ADR-0006` (the fields are simply absent there -- read defensively,
    never invented)."""
    result: Optional[tuple[Any, Any]] = None
    for record in history:
        if record.get("kind") != "decision" or record.get("id") != DEC_BLOCK:
            continue
        data = record.get("data", {})
        if data.get("work_id") != work_id:
            continue
        if "max_assurance_attempts" not in data:
            result = None
            continue
        result = (data.get("assurance_number"), data.get("max_assurance_attempts"))
    return result


def _assurance_index_suffix(wp: WorkProjection, history: Sequence[Mapping[str, Any]]) -> str:
    """`SCN-021` item 7: name which assurance of the current attempt the
    verify seat is being asked for, so a re-request (`INV-021`) is visible
    as a re-request rather than looking like the first ask. Empty string
    when no assurance has started for the current Execution."""
    number = wp.assurance_number()
    if number < 1:
        return ""
    budget = _requested_assurance_budget(history, wp.work_id)
    if isinstance(budget, int):
        return f" (assurance {number} of {budget})"
    return f" (assurance {number})"


def _requested_assurance_budget(history: Sequence[Mapping[str, Any]], work_id: str) -> Optional[Any]:
    """The `max_assurance_attempts` this Work's most recent
    `DEC-REQUEST-ASSURANCE` recorded (`INV-021`). `None` for a run whose
    decisions predate `ADR-0006` -- the field is absent there, and an
    absent budget is rendered as an absent budget, never a guessed one."""
    budget: Optional[Any] = None
    for record in history:
        if record.get("kind") != "decision" or record.get("id") != DEC_REQUEST_ASSURANCE:
            continue
        data = record.get("data", {})
        if data.get("work_id") != work_id:
            continue
        budget = data.get("max_assurance_attempts")
    return budget


def _identified_candidate_subject_identity(
    history: Sequence[Mapping[str, Any]], work_id: str, wp: WorkProjection
) -> Optional[Mapping[str, Any]]:
    """The current candidate's `subject_identity`, when the shipper's
    recorded candidate happens to carry one (`docs/playbooks/
    agent-cli-usage.md` #3's "externally resolvable identity"). Reads the
    same `FX-IDENTIFY-CANDIDATE` effect records `orc_werk.cli.report.
    _candidate_subject_identities` reads; duplicated here narrowly (one
    lookup, generic-shaped) rather than importing `cli.report`, to avoid a
    `cli.report` <-> `cli.affordances` import cycle (`report.py` imports
    this module for its own `next:` rendering)."""
    candidate_id = wp.current_candidate_id
    if candidate_id is None:
        return None
    for record in history:
        if record.get("kind") != "effect" or record.get("id") != "FX-IDENTIFY-CANDIDATE":
            continue
        if record.get("data", {}).get("work_id") != work_id:
            continue
        candidate = record.get("data", {}).get("dispatch_result", {}).get("candidate")
        if isinstance(candidate, Mapping) and candidate.get("id") == candidate_id:
            subject_identity = candidate.get("subject_identity")
            if isinstance(subject_identity, Mapping):
                return subject_identity
    return None


def _candidate_pr(history: Sequence[Mapping[str, Any]], work_id: str, wp: WorkProjection) -> Optional[Any]:
    """The `pr` field of the accepted candidate's `subject_identity`, when
    present -- a PR number is the common case for a `git`-backed
    candidate."""
    subject_identity = _identified_candidate_subject_identity(history, work_id, wp)
    if subject_identity is not None and "pr" in subject_identity:
        return subject_identity["pr"]
    return None


def _candidate_head_sha(history: Sequence[Mapping[str, Any]], work_id: str, wp: WorkProjection) -> Optional[str]:
    """The `head_sha` field of the current candidate's `subject_identity`,
    when present (a `git`-backed candidate, `orc_werk.adapters.git.
    candidate`) -- generic across every assurance adapter (`PORT-CANDIDATE`
    concept, not adapter-specific vocabulary, `INV-014`). Used by the
    pending-assurance affordance (`TASK-M3B-002`, issue #92) to name the
    candidate identity a bound assurance run's outcome must still match
    before it can honestly settle -- without this CLI layer ever parsing
    any adapter-owned `assurance_id` format itself."""
    subject_identity = _identified_candidate_subject_identity(history, work_id, wp)
    if subject_identity is not None and isinstance(subject_identity.get("head_sha"), str):
        return subject_identity["head_sha"]
    return None


def _work_group_key(work_id: str, wp: WorkProjection) -> Optional[str]:
    """The grouping key for one Work's affordance, or `None` when its
    current state carries no affordance (`READY`: not actionable by an
    agent -- the kernel dispatches it, `STATE-DELIVERY` declares no agent
    action at `READY`)."""
    if has_candidate_conflict(wp):
        return "candidate-conflict"
    # Issue #244/SCN-014: a settled Execution still resting at EXECUTING with
    # no bound Candidate because the latest FX-IDENTIFY-CANDIDATE observation
    # was null (PORT-CAND-001's legitimate no-subject result) is neither
    # `is_pending` (its Execution outcome IS observed) nor a candidate
    # conflict -- a third, distinct resting shape with its own affordance.
    # `abandon_legality` is the single source of truth for this exact
    # predicate (issue #200; also what `abandon_attempt`'s preflight and the
    # reducer's replay-time legality check use), so this can never drift
    # from what a subsequent `--abandon-work` will accept.
    if abandon_legality(wp).awaiting_candidate:
        return "awaiting-candidate"
    if is_pending(wp):
        if wp.state == STATE_EXECUTING:
            return "pending-execution"
        if wp.state == STATE_ASSURING:
            return "pending-assurance"
        return f"pending-{_awaiting_label(wp)}"
    if wp.state == STATE_BLOCKED:
        return f"blocked-{wp.blocked_reason}"
    if wp.state == STATE_ACCEPTED:
        return "accepted"
    return None


def _group_works(projection: DeliveryProjection) -> tuple[dict[str, list[str]], list[str]]:
    """The per-state grouping both `render_next_block` (text) and
    `next_entries` (issue #53's structured `--json` sibling) key off:
    every Work with an affordance, bucketed by `_work_group_key`, in
    first-seen order over `sorted(projection.works)`. Extracted once so
    the two renderers can never derive a different set of groups from the
    same projection -- the single per-state map lives in
    `_work_group_key`; this only shares its bucketing."""
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    for work_id in sorted(projection.works):
        wp = projection.works[work_id]
        key = _work_group_key(work_id, wp)
        if key is None:
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(work_id)
    return groups, order


def render_next_block(
    projection: DeliveryProjection,
    history: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    journal_dir: Path,
    config_path: Optional[Path],
    intent_text: Optional[str],
) -> list[str]:
    """The full `next:` block (`[]` when no Work carries an affordance --
    e.g. every Work is still `READY`) for `dispatch`/`status` output.
    `journal_dir` and `config_path` should already be absolute (per-caller
    resolution) so every printed command is copy-pasteable regardless of
    the reader's cwd."""
    groups, order = _group_works(projection)

    if not groups:
        return []

    lines = ["next:"]
    needs_redispatch = False
    for key in order:
        work_ids = groups[key]
        ids_text = ", ".join(work_ids)
        if key == "candidate-conflict":
            # TASK-M3B-001 (issues #76/#95): an operator-only power, never
            # part of the ship/verify agent seat rotation this block's
            # other entries implicitly invite -- named explicitly here
            # rather than folded into the shared re-dispatch line below.
            for work_id in work_ids:
                lines.append(
                    f"  - work {work_id} rests at a candidate-observation conflict "
                    "verdict inheritance could not resolve (STATE-DELIVERY item 9): "
                    "operator-only -- orc dispatch --run-id "
                    f"{run_id} --journal {journal_dir} --config "
                    f"{config_path or journal_dir / run_id / 'config.json'} "
                    f"--abandon-work {work_id} --abandon-reason \"<why>\""
                )
        elif key == "awaiting-candidate":
            # Issue #244/SCN-014: null identification is non-binding --
            # re-dispatch re-derives automatically once the subject exists
            # again (e.g. the configured `candidate.repo_path` is restored).
            # No operator recording action is required here (contrast
            # pending-execution/pending-assurance above); the only affordance
            # is naming the likely cause and pointing at re-dispatch, plus
            # the `--abandon-work` escape hatch (`TASK-M3B-001`) for a
            # subject that stays absent.
            lines.append(
                f"  - work(s) {ids_text}: candidate identification returned no subject -- "
                "ensure candidate.repo_path exists and re-dispatch (re-derivation is "
                "automatic); if the subject is never coming back: orc dispatch --run-id "
                f"{run_id} --journal {journal_dir} --config "
                f"{_resolved_config_token(config_path=config_path, journal_dir=journal_dir, run_id=run_id)} "
                f"--abandon-work <work_id> --abandon-reason \"<why>\""
            )
            needs_redispatch = True
        elif key == "pending-execution":
            lines.append(f"  - record the execution outcome for work(s): {ids_text}")
            needs_redispatch = True
        elif key == "pending-assurance":
            index_text = ", ".join(
                f"{work_id}{_assurance_index_suffix(projection.works[work_id], history)}".strip()
                for work_id in work_ids
            )
            lines.append(
                f"  - record the assurance verdict for work(s): {index_text} -- needs a "
                "different agent than the one that recorded the settlement "
                "(canonical playbook discipline: PLAYBOOK-AGENT-CLI)"
            )
            needs_redispatch = True
            for work_id in work_ids:
                wp = projection.works[work_id]
                if wp.current_assurance_id is None:
                    continue
                # TASK-M3B-002 (issue #92 scope extension, fix-round
                # finding 3): a positively-confirmed identity divergence
                # SETTLES as inconclusive (visible through the journal as
                # a BLOCKED root cause -- it never rests here), so a
                # pending assurance means healthy-in-flight or
                # identity-unconfirmable only; no speculative "this may
                # have diverged" framing. Name the two facts durably
                # resolvable from journal state: the opaque, adapter-owned
                # `assurance_id` (`wp.current_assurance_id`, never parsed
                # here, INV-014) and the candidate's own head when a
                # git-backed candidate identified one; mention the
                # operator abandon record (`TASK-M3B-001`, PR #115) only
                # as the recovery for a run that stays pending
                # unexpectedly long (the unconfirmable case).
                head = _candidate_head_sha(history, work_id, wp)
                head_text = head if head is not None else "(unknown)"
                lines.append(
                    f"  - work {work_id}'s bound assurance is {wp.current_assurance_id} "
                    f"(candidate head {head_text}); if it stays pending unexpectedly "
                    "long, operator recovery is: orc dispatch --run-id "
                    f"{run_id} --journal {journal_dir} --config "
                    f"{config_path or journal_dir / run_id / 'config.json'} "
                    f"--abandon-work {work_id} --abandon-reason \"<why>\""
                )
        elif key.startswith("blocked-"):
            reason = key[len("blocked-") :]
            for work_id in work_ids:
                budget = _block_budget(history, work_id)
                budget_note = ""
                if reason == BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED:
                    budget_note = " (retry budget exhausted -- no attempts remain)"
                elif budget is not None and isinstance(budget[0], int) and isinstance(budget[1], int):
                    remaining = max(0, budget[1] - budget[0])
                    assurance_budget = _block_assurance_budget(history, work_id)
                    if (
                        reason == BLOCKED_REASON_ASSURANCE_INCONCLUSIVE
                        and assurance_budget is not None
                        and isinstance(assurance_budget[1], int)
                    ):
                        budget_note = (
                            f" (assurance budget exhausted: {assurance_budget[1]} of "
                            f"{assurance_budget[1]} assurances of this candidate settled "
                            "inconclusive -- INV-021; the execution retry budget was never "
                            f"consumed, {remaining} of {budget[1]} attempts remain unused)"
                        )
                    else:
                        budget_note = (
                            f" ({remaining} of {budget[1]} attempts technically unused -- an "
                            "inconclusive verdict spends the assurance budget (INV-021), never "
                            "the execution retry budget, so no automatic retry follows)"
                        )
                lines.append(
                    f"  - work {work_id} is BLOCKED (blocked_reason={reason}){budget_note}: "
                    f"see orc history {run_id} for the root cause"
                )
        elif key == "accepted":
            lines.append(f"  - work(s) accepted: {ids_text} -- see the full run report: orc report {run_id}")
            for work_id in work_ids:
                pr = _candidate_pr(history, work_id, projection.works[work_id])
                if pr is not None:
                    lines.append(f"  - work {work_id}'s candidate carries pr {pr}: gh pr view {pr}")

    if needs_redispatch:
        lines.append(
            "  - then re-run: "
            + redispatch_command(
                intent_text=intent_text,
                config_path=config_path,
                journal_dir=journal_dir,
                run_id=run_id,
            )
        )

    return lines


@dataclass(frozen=True)
class NextEntry:
    """One structured `next:` affordance (issue #53's `--json` sibling of
    `render_next_block`'s text bullets): `description` is the human
    sentence, `command` is the exact runnable `orc`/`gh` command it names
    -- or `None` for a bullet with no command of its own (e.g. "record the
    execution outcome for work(s): ..."), never a fabricated one."""

    description: str
    command: Optional[str] = None


def next_entries(
    projection: DeliveryProjection,
    history: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    journal_dir: Path,
    config_path: Optional[Path],
    intent_text: Optional[str],
) -> list[NextEntry]:
    """Structured counterpart to `render_next_block` (issue #53 R2's `next:`
    field on `orc-status/v1`): the exact same per-state grouping
    (`_group_works`, itself keyed by `_work_group_key` -- the single
    per-state affordance map this module's docstring describes) reduced to
    `{description, command}` pairs instead of pre-formatted prose lines, so
    a structured consumer gets the runnable command as its own field
    rather than having to parse it back out of a sentence. Every branch
    below mirrors exactly one `render_next_block` branch and reuses the
    identical helper calls (`_block_budget`, `_candidate_head_sha`,
    `_candidate_pr`, `redispatch_command`, `_resolved_config_token`) --
    keep the two renderers' branches in sync when the per-state affordance
    map changes; neither one derives Work state semantics independently of
    `_work_group_key`."""
    groups, order = _group_works(projection)
    entries: list[NextEntry] = []

    if not groups:
        return entries

    needs_redispatch = False
    for key in order:
        work_ids = groups[key]
        ids_text = ", ".join(work_ids)
        if key == "candidate-conflict":
            for work_id in work_ids:
                entries.append(
                    NextEntry(
                        description=(
                            f"work {work_id} rests at a candidate-observation conflict "
                            "verdict inheritance could not resolve (STATE-DELIVERY item 9): "
                            "operator-only"
                        ),
                        command=(
                            f"orc dispatch --run-id {run_id} --journal {journal_dir} --config "
                            f"{config_path or journal_dir / run_id / 'config.json'} "
                            f'--abandon-work {work_id} --abandon-reason "<why>"'
                        ),
                    )
                )
        elif key == "awaiting-candidate":
            entries.append(
                NextEntry(
                    description=(
                        f"work(s) {ids_text}: candidate identification returned no subject -- "
                        "ensure candidate.repo_path exists and re-dispatch (re-derivation is "
                        "automatic); if the subject is never coming back"
                    ),
                    command=(
                        f"orc dispatch --run-id {run_id} --journal {journal_dir} --config "
                        f"{_resolved_config_token(config_path=config_path, journal_dir=journal_dir, run_id=run_id)} "
                        '--abandon-work <work_id> --abandon-reason "<why>"'
                    ),
                )
            )
            needs_redispatch = True
        elif key == "pending-execution":
            entries.append(NextEntry(description=f"record the execution outcome for work(s): {ids_text}"))
            needs_redispatch = True
        elif key == "pending-assurance":
            index_text = ", ".join(
                f"{work_id}{_assurance_index_suffix(projection.works[work_id], history)}".strip()
                for work_id in work_ids
            )
            entries.append(
                NextEntry(
                    description=(
                        f"record the assurance verdict for work(s): {index_text} -- needs a "
                        "different agent than the one that recorded the settlement "
                        "(canonical playbook discipline: PLAYBOOK-AGENT-CLI)"
                    )
                )
            )
            needs_redispatch = True
            for work_id in work_ids:
                wp = projection.works[work_id]
                if wp.current_assurance_id is None:
                    continue
                head = _candidate_head_sha(history, work_id, wp)
                head_text = head if head is not None else "(unknown)"
                entries.append(
                    NextEntry(
                        description=(
                            f"work {work_id}'s bound assurance is {wp.current_assurance_id} "
                            f"(candidate head {head_text}); if it stays pending unexpectedly "
                            "long, operator recovery is"
                        ),
                        command=(
                            f"orc dispatch --run-id {run_id} --journal {journal_dir} --config "
                            f"{config_path or journal_dir / run_id / 'config.json'} "
                            f'--abandon-work {work_id} --abandon-reason "<why>"'
                        ),
                    )
                )
        elif key.startswith("blocked-"):
            reason = key[len("blocked-") :]
            for work_id in work_ids:
                budget = _block_budget(history, work_id)
                budget_note = ""
                if reason == BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED:
                    budget_note = " (retry budget exhausted -- no attempts remain)"
                elif budget is not None and isinstance(budget[0], int) and isinstance(budget[1], int):
                    remaining = max(0, budget[1] - budget[0])
                    assurance_budget = _block_assurance_budget(history, work_id)
                    if (
                        reason == BLOCKED_REASON_ASSURANCE_INCONCLUSIVE
                        and assurance_budget is not None
                        and isinstance(assurance_budget[1], int)
                    ):
                        budget_note = (
                            f" (assurance budget exhausted: {assurance_budget[1]} of "
                            f"{assurance_budget[1]} assurances of this candidate settled "
                            "inconclusive -- INV-021; the execution retry budget was never "
                            f"consumed, {remaining} of {budget[1]} attempts remain unused)"
                        )
                    else:
                        budget_note = (
                            f" ({remaining} of {budget[1]} attempts technically unused -- an "
                            "inconclusive verdict spends the assurance budget (INV-021), never "
                            "the execution retry budget, so no automatic retry follows)"
                        )
                entries.append(
                    NextEntry(
                        description=f"work {work_id} is BLOCKED (blocked_reason={reason}){budget_note}",
                        command=f"orc history {run_id}",
                    )
                )
        elif key == "accepted":
            entries.append(
                NextEntry(description=f"work(s) accepted: {ids_text}", command=f"orc report {run_id}")
            )
            for work_id in work_ids:
                pr = _candidate_pr(history, work_id, projection.works[work_id])
                if pr is not None:
                    entries.append(
                        NextEntry(
                            description=f"work {work_id}'s candidate carries pr {pr}",
                            command=f"gh pr view {pr}",
                        )
                    )

    if needs_redispatch:
        entries.append(
            NextEntry(
                description="then re-run",
                command=redispatch_command(
                    intent_text=intent_text,
                    config_path=config_path,
                    journal_dir=journal_dir,
                    run_id=run_id,
                ),
            )
        )

    return entries


__all__ = ["NextEntry", "next_entries", "redispatch_command", "render_next_block"]
