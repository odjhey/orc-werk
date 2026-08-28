"""HATEOAS-style per-state affordance mapping (issue #43's watchtower
reframe of the "next-step hints" item -- the organizing principle for the
whole CLI-UX round).

The delivery state machine (`STATE-DELIVERY`,
`docs/domain/state-machines/delivery.md`) IS the hypermedia map: this
module owns the single per-state -> "next:" text mapping that `orc
dispatch`/`orc status` render from. A new transition in that state machine
must force the affordance question here -- there must be no hand-scattered
"next:" string anywhere else in this CLI.

Per-state map (issue #43, second watchtower comment):

| Work state                         | Affordance                                                              |
|-------------------------------------|--------------------------------------------------------------------------|
| PENDING @ EXECUTING (`is_pending`)  | record the execution outcome, then re-dispatch (exact command)          |
| PENDING @ ASSURING  (`is_pending`)  | record the assurance verdict -- a different agent than the settlement recorder (playbook discipline), then re-dispatch |
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
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.jsonl import layout
from orc_werk.app.orchestrator import is_pending
from orc_werk.cli.journal_reading import BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED, _awaiting_label
from orc_werk.core.decisions import DEC_BLOCK
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


def _candidate_pr(history: Sequence[Mapping[str, Any]], work_id: str, wp: WorkProjection) -> Optional[Any]:
    """The `pr` field of the accepted candidate's `subject_identity`, when
    the shipper's recorded candidate happens to carry one
    (`docs/playbooks/agent-cli-usage.md` #3's "externally resolvable
    identity" -- a PR number is the common case). Reads the same
    `FX-IDENTIFY-CANDIDATE` effect records
    `orc_werk.cli.report._candidate_subject_identities` reads; duplicated
    here narrowly (one field, one candidate) rather than importing
    `cli.report`, to avoid a `cli.report` <-> `cli.affordances` import
    cycle (`report.py` will import this module for its own `next:`
    rendering)."""
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
            if isinstance(subject_identity, Mapping) and "pr" in subject_identity:
                return subject_identity["pr"]
    return None


def _work_group_key(work_id: str, wp: WorkProjection) -> Optional[str]:
    """The grouping key for one Work's affordance, or `None` when its
    current state carries no affordance (`READY`: not actionable by an
    agent -- the kernel dispatches it, `STATE-DELIVERY` declares no agent
    action at `READY`)."""
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

    if not groups:
        return []

    lines = ["next:"]
    needs_redispatch = False
    for key in order:
        work_ids = groups[key]
        ids_text = ", ".join(work_ids)
        if key == "pending-execution":
            lines.append(f"  - record the execution outcome for work(s): {ids_text}")
            needs_redispatch = True
        elif key == "pending-assurance":
            lines.append(
                f"  - record the assurance verdict for work(s): {ids_text} -- needs a "
                "different agent than the one that recorded the settlement "
                "(playbook discipline, docs/playbooks/agent-cli-usage.md)"
            )
            needs_redispatch = True
        elif key.startswith("blocked-"):
            reason = key[len("blocked-") :]
            for work_id in work_ids:
                budget = _block_budget(history, work_id)
                budget_note = ""
                if reason == BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED:
                    budget_note = " (retry budget exhausted -- no attempts remain)"
                elif budget is not None and isinstance(budget[0], int) and isinstance(budget[1], int):
                    remaining = max(0, budget[1] - budget[0])
                    budget_note = (
                        f" ({remaining} of {budget[1]} attempts technically unused, but "
                        "STATE-DELIVERY routes an inconclusive verdict straight to BLOCKED -- "
                        "no automatic retry)"
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


__all__ = ["redispatch_command", "render_next_block"]
