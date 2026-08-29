"""`orc show <run> [work]` (`TASK-M3C-001`, `M3-HARDEN-THE-LOOP` Phase M3c):
the terminal narrative view -- the operator's four-question review
staircase's levels two ("this run in depth") and three ("briefs and
hand-offs per turn"). Bare `orc` (level one) says what happened; `orc refs
--resolve` (`TASK-M3C-002`, level four) shells out to adapter-native
tooling; this command is the gap between them -- composing the journal,
this run's persisted dispatch config, the observed-at times sidecar, and
journaled extension payloads into one per-work, per-attempt story, so a
reviewer answers "what was asked, who did it, what was produced, what was
judged, where's the full content" without hand-correlating four sources.

Pure composition of existing readers (CLAUDE.md #6/#7, the task card's
first non-negotiable): no new storage, no new recording, nothing this
command journals or persists itself. It reuses:

- `orc_werk.cli.journal_reading`'s target resolution / `ERR-NOT-FOUND`
  affordance (same as `status`/`history`/`report`/`refs`);
- `orc_werk.cli.refs`'s per-source ref-row builders (`_execution_session_
  rows`, `_evidence_ref_rows`, `_candidate_rows`, `_load_persisted_config`)
  for the NEXT/DEEPER resolve commands and the persisted-config read --
  imported and scoped per attempt, never reimplemented;
- `orc_werk.cli.report`'s `_load_times_sidecar` for attempt duration;
- `orc_werk.cli.affordances.render_next_block` for the run-level `next:`
  block.

**Prompt provenance (issue #111's "briefs footgun" incident, the task
card's second non-negotiable).** `orc_werk.cli.config._IntentPromptExecution.
_filled_request` derives an ACP execution's prompt as
`self._briefs.get(work_id, self._intent_text)` -- a `briefs[work_id]` entry,
however short, always wins over the run's own intent text (the issue #82/
#83 precedence rule). This module mirrors that exact `dict.get` semantics
against the run's own persisted config (`<journal-dir>/<run_id>/
config.json`) to derive which text ACTUALLY became the prompt, rather than
guessing: `work_id in briefs` -> `"briefs.<work_id> (persisted config)"`,
absent -> `"run intent (fallback)"`. When `execution.adapter` is not
`"acp"` (the default `"scripted"`, or any other non-ACP adapter), no
per-work request is ever filled in -- `orc_werk.app.Orchestrator` always
calls `start()` with an opaque, empty `execution_request`, and only the ACP
composition wrapper fills in a prompt -- so this renders the honest
`"scripted execution -- no prompt sent to the executor"` rather than
inventing one. The full prompt/intent text is never dumped here (a
narrative view, not a payload viewer): a preview is shown, truncated with a
definitive count and a pointer at the full text's actual source (the
persisted config path for a brief, `orc status <run>` for the intent
fallback) -- never an ambiguous "...more" (issue #113's listing
convention, `PLAYBOOK-CLI-USAGE`'s Design principles).

**Attempt segmentation.** A Work's per-attempt story is read by slicing its
journaled records at each `FX-START-EXECUTION` effect record, whose own
`data.attempt_number` (`orc_werk.core.policy.decide`'s `DEC-DISPATCH`/
`DEC-RETRY` derivation) is the canonical attempt counter -- never
re-derived by counting records by hand.

**Verdict inheritance (`STATE-DELIVERY` item 8, the issue #76/#115
specimen).** A re-observed candidate whose fingerprint already has a
settled assurance in this Work's lineage resolves *mechanically* -- no new
`FACT-ASSURE-SETTLED` is journaled (`INV-003`), and for the READY-bound
(rejected, budget available) case not even a `DEC-*` is journaled for the
fold itself (confirmed against the real `trivia-sweep`/`fix-69-status-
resolver` specimens: attempt 2 ends at `FACT-CANDIDATE-OBSERVED` with no
following decision). This module detects inheritance the same way the
task card's basis note directs: an attempt whose candidate fingerprint
matches an EARLIER attempt's already-settled fingerprint, with no fresh
`FACT-ASSURE-SETTLED`/`FACT-ASSURE-STARTED` of its own, inherits that
earlier attempt's verdict -- rendered as "verdict inherited from attempt
N's settlement", citing `STATE-DELIVERY` item 8 rather than presenting it
as a fresh judgment.
"""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.jsonl import layout
from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.app.orchestrator import has_candidate_conflict, is_pending
from orc_werk.cli.affordances import render_next_block
from orc_werk.cli.journal_reading import (
    _diagnose_replay_conflict,
    _intent_text,
    _require_journal_file,
    _resolve_journal,
)
from orc_werk.cli.refs import (
    _candidate_rows,
    _evidence_ref_rows,
    _execution_session_rows,
    _load_persisted_config,
    _row_line,
)
from orc_werk.cli.report import _load_times_sidecar
from orc_werk.core.effects import FX_IDENTIFY_CANDIDATE, FX_START_EXECUTION
from orc_werk.core.errors import CoreError, not_found_error
from orc_werk.core.facts import (
    FACT_ASSURE_SETTLED,
    FACT_ASSURE_STARTED,
    FACT_ATTEMPT_ABANDONED,
    FACT_CANDIDATE_OBSERVED,
    FACT_EXEC_SETTLED,
    FACT_EXEC_STARTED,
    FACT_WORK_CREATED,
)
from orc_werk.core.state import STATE_ACCEPTED, STATE_BLOCKED, DeliveryProjection, WorkProjection

# Read-only presentation exit-code mirror of `status`'s contract
# (`docs/playbooks/cli-usage.md`): `show` presents per-work state the same
# way `status` does, so it carries the same 0/1/3 disposition rather than
# `refs`/`report`'s unconditional 0 (those are pure reference/artifact
# projections with no per-work disposition to report). Duplicated locally
# rather than imported from `orc_werk.cli.main` (which imports this module
# for its own subcommand wiring) to avoid a cycle -- `orc_werk.cli.report`
# carries its own `_summarize_states` for the identical reason.
_EXIT_PENDING = 3

# Narrative preview cap for a prompt's shown text (issue #113 listing
# convention: a definitive count plus a same-content escape hatch -- here,
# the pointer at the actual full-text source -- never an ambiguous
# "...more"). Chosen to keep a per-attempt block terminal-scannable while
# still showing enough of a brief/intent to judge whether it looks like the
# issue #111 "stub brief" shape.
_PROMPT_PREVIEW_CHARS = 200

# Findings-list cap per attempt (issue #113 listing convention applied to
# `review-findings/v1`'s otherwise-unbounded `findings` array -- the one
# source this card's own docs note as needing a bound, unlike `attempts`,
# which the retry budget already bounds). A count plus a pointer at `orc
# history <run> --limit 0` (where the full, unsummarized extension payload
# already lives, `FRICTION-1`) is the escape hatch.
_FINDINGS_PREVIEW_LIMIT = 5

_TIMES_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


# ---------------------------------------------------------------------------
# Small journal-record helpers (read-only lookups over an already-loaded,
# already-filtered record slice; no new semantics).
# ---------------------------------------------------------------------------


def _first(records: Sequence[Mapping[str, Any]], kind: str, record_id: str) -> Optional[Mapping[str, Any]]:
    for record in records:
        if record.get("kind") == kind and record.get("id") == record_id:
            return record
    return None


def _work_ids_in_order(history: Sequence[Mapping[str, Any]]) -> list[str]:
    """Every `work_id` this run ever created, in the order `FACT-WORK-
    CREATED` journaled them (plan-declaration order, `FX-CREATE-WORK`)."""
    ids: list[str] = []
    for record in history:
        if record.get("kind") != "fact" or record.get("id") != FACT_WORK_CREATED:
            continue
        work_id = record.get("data", {}).get("work_id")
        if work_id and work_id not in ids:
            ids.append(work_id)
    return ids


def _work_records(history: Sequence[Mapping[str, Any]], work_id: str) -> list[Mapping[str, Any]]:
    return [record for record in history if record.get("data", {}).get("work_id") == work_id]


def _segment_attempts(work_records: Sequence[Mapping[str, Any]]) -> list[tuple[Any, list[Mapping[str, Any]]]]:
    """Slice one Work's records into `(attempt_number, records)` groups, one
    per attempt, split at each `FX-START-EXECUTION` effect -- whose own
    `data.attempt_number` is the canonical counter (`INV-018`), never
    re-derived by counting. Records preceding the first attempt (`FACT-
    WORK-CREATED`/`CLAIMED`/`READY`, the first `DEC-DISPATCH`) belong to no
    attempt slice and are not needed by this view."""
    attempts: list[tuple[Any, list[Mapping[str, Any]]]] = []
    current: Optional[list[Mapping[str, Any]]] = None
    for record in work_records:
        if record.get("kind") == "effect" and record.get("id") == FX_START_EXECUTION:
            current = []
            attempts.append((record.get("data", {}).get("attempt_number"), current))
        if current is not None:
            current.append(record)
    return attempts


def _parse_observed_at(value: Any) -> Optional[datetime.datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.strptime(value, _TIMES_FORMAT)
    except ValueError:
        return None


def _duration_text(
    times: Mapping[int, str],
    started: Optional[Mapping[str, Any]],
    settled: Optional[Mapping[str, Any]],
) -> Optional[str]:
    """`started`->`settled` observed-at delta (the times sidecar, `report.
    py`'s `_load_times_sidecar`) -- `None` (never fabricated) when either
    record is missing, the sidecar has no entry for its `seq`, or an entry
    exists but does not parse."""
    if started is None or settled is None:
        return None
    start_dt = _parse_observed_at(times.get(started.get("seq")))
    end_dt = _parse_observed_at(times.get(settled.get("seq")))
    if start_dt is None or end_dt is None:
        return None
    delta = (end_dt - start_dt).total_seconds()
    return f"{delta:.3f}s ({times[started['seq']]} -> {times[settled['seq']]})"


# ---------------------------------------------------------------------------
# ASKED: prompt provenance (issue #111)
# ---------------------------------------------------------------------------


def _truncate(text: str, *, limit: int = _PROMPT_PREVIEW_CHARS) -> tuple[str, bool, int]:
    total = len(text)
    if total <= limit:
        return text, False, total
    return text[:limit], True, total


def prompt_provenance(config: Optional[Mapping[str, Any]], work_id: str, intent_text: Optional[str]) -> dict:
    """The derived source of the text that actually became (or would
    become) this work's ACP execution prompt -- mirroring `orc_werk.cli.
    config._IntentPromptExecution._filled_request`'s own `self._briefs.
    get(work_id, self._intent_text)` precedence exactly (issue #82/#83),
    read from the run's own persisted config rather than guessed. Returns
    one of:

    - `{"kind": "unavailable"}` -- no persisted config found for this run
      (a legacy pre-#55H2 run, or a best-effort persist that never wrote).
    - `{"kind": "no-prompt", "adapter": <str>}` -- `execution.adapter` is
      not `"acp"` (default `"scripted"`): no per-work request is ever
      filled in, so no prompt is sent at all.
    - `{"kind": "brief", "text": <str>}` -- `work_id` is a key in the
      persisted config's `briefs` mapping (`dict.get` semantics: present,
      however short or empty, always wins).
    - `{"kind": "intent", "text": <str-or-None>}` -- no `briefs` entry for
      `work_id`: falls back to the run's own intent text.
    """
    if config is None:
        return {"kind": "unavailable"}
    execution_cfg = config.get("execution")
    adapter = execution_cfg.get("adapter", "scripted") if isinstance(execution_cfg, Mapping) else "scripted"
    if adapter != "acp":
        return {"kind": "no-prompt", "adapter": adapter}
    briefs = config.get("briefs")
    if isinstance(briefs, Mapping) and work_id in briefs and isinstance(briefs[work_id], str):
        return {"kind": "brief", "text": briefs[work_id]}
    return {"kind": "intent", "text": intent_text}


def _render_asked(
    provenance: Mapping[str, Any], *, work_id: str, run_id: str, config_path: Path
) -> list[str]:
    kind = provenance["kind"]
    if kind == "unavailable":
        return ["  ASKED: prompt provenance unavailable -- no persisted dispatch config found for this run"]
    if kind == "no-prompt":
        return [f"  ASKED: scripted execution ({provenance['adapter']}) -- no prompt sent to the executor"]
    text = provenance.get("text")
    if kind == "brief":
        lines = [f"  ASKED: prompt = briefs.{work_id} (persisted config)"]
        pointer = f"{config_path} (key: briefs.{work_id})"
    else:
        lines = ["  ASKED: prompt = run intent (fallback)"]
        pointer = f"orc status {run_id}"
    if text is None:
        lines.append("    text: (no intent text recorded)")
        return lines
    shown, truncated, total = _truncate(text)
    shown = " ".join(shown.split())
    if truncated:
        lines.append(f"    text: {shown}... [truncated, showing {len(shown)} of {total} chars; full text: {pointer}]")
    else:
        lines.append(f"    text: {shown}")
    return lines


# ---------------------------------------------------------------------------
# EXECUTED / PRODUCED / JUDGED
# ---------------------------------------------------------------------------


def _render_executed(records: Sequence[Mapping[str, Any]], times: Mapping[int, str]) -> list[str]:
    started = _first(records, "fact", FACT_EXEC_STARTED)
    settled = _first(records, "fact", FACT_EXEC_SETTLED)
    if settled is None:
        return ["  EXECUTED: (pending -- execution outcome not yet recorded)"]
    data = settled.get("data", {})
    session_payload = (settled.get("extensions") or {}).get("execution-session/v1")
    provider = session_payload.get("provider") if isinstance(session_payload, Mapping) else None
    lines = [f"  EXECUTED: provider={provider or '-'} execution_id={data.get('execution_id', '-')}"]
    if isinstance(session_payload, Mapping):
        native_session_id = session_payload.get("native_session_id")
        if native_session_id is not None:
            lines.append(f"    session: {native_session_id}")
        resume = session_payload.get("resume")
        if isinstance(resume, Mapping) and resume.get("ref") is not None:
            lines.append(f"    resume: {resume['ref']}")
    duration = _duration_text(times, started, settled)
    if duration is not None:
        lines.append(f"    duration: {duration}")
    lines.append(f"    outcome: {data.get('outcome', '-')}")
    return lines


def _render_produced(records: Sequence[Mapping[str, Any]]) -> list[str]:
    observed = _first(records, "fact", FACT_CANDIDATE_OBSERVED)
    if observed is None:
        return ["  PRODUCED: (no candidate observed this attempt)"]
    data = observed.get("data", {})
    lines = [f"  PRODUCED: candidate={data.get('candidate_id', '-')} fingerprint={data.get('fingerprint', '-')}"]
    identify_effect = _first(records, "effect", FX_IDENTIFY_CANDIDATE)
    subject_identity = None
    if identify_effect is not None:
        candidate = identify_effect.get("data", {}).get("dispatch_result", {}).get("candidate")
        if isinstance(candidate, Mapping):
            subject_identity = candidate.get("subject_identity")
    if isinstance(subject_identity, Mapping):
        for key in ("head_sha", "pr", "repo_path"):
            if key in subject_identity:
                lines.append(f"    {key}: {subject_identity[key]}")
    return lines


def _finding_id(entry: Mapping[str, Any], index: int) -> str:
    value = entry.get("id")
    return value if isinstance(value, str) and value else f"finding-{index}"


def _finding_severity(entry: Mapping[str, Any]) -> str:
    value = entry.get("severity")
    return value if isinstance(value, str) and value else "-"


def _one_line(text: str, *, limit: int = 140) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rstrip() + "..."


def _finding_summary(entry: Mapping[str, Any]) -> str:
    for key in ("summary", "title"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return _one_line(value)
    detail = entry.get("detail")
    if isinstance(detail, str) and detail:
        return _one_line(detail)
    return "-"


def _render_findings(findings: Sequence[Any], *, run_id: str) -> list[str]:
    total = len(findings)
    lines = [f"    findings: {total}"]
    for index, entry in enumerate(findings[:_FINDINGS_PREVIEW_LIMIT], start=1):
        if not isinstance(entry, Mapping):
            continue
        lines.append(f"      [{_finding_severity(entry)}] {_finding_id(entry, index)}: {_finding_summary(entry)}")
    if total > _FINDINGS_PREVIEW_LIMIT:
        lines.append(
            f"      ... showing {_FINDINGS_PREVIEW_LIMIT} of {total} findings; "
            f"orc history {run_id} --limit 0 for the full payload"
        )
    return lines


def _render_judged(
    records: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    inherited_from: Optional[tuple[Any, Mapping[str, Any]]],
    wp: Optional[WorkProjection],
) -> list[str]:
    abandoned = _first(records, "fact", FACT_ATTEMPT_ABANDONED)
    if abandoned is not None:
        data = abandoned.get("data", {})
        attribution = abandoned.get("attribution") or {}
        by = attribution.get("by", "-") if isinstance(attribution, Mapping) else "-"
        return [
            f"  JUDGED: attempt abandoned by operator (reason: {data.get('reason', '-')}, by: {by}) "
            "-- STATE-DELIVERY item 9 (DEC-ABANDON-ATTEMPT/FACT-ATTEMPT-ABANDONED)"
        ]

    settled = _first(records, "fact", FACT_ASSURE_SETTLED)
    if settled is not None:
        data = settled.get("data", {})
        lines = [f"  JUDGED: assurance={data.get('assurance_id', '-')} verdict={data.get('verdict', '-')}"]
        evidence_refs = data.get("evidence_refs")
        if evidence_refs:
            lines.append(f"    evidence_refs: {evidence_refs}")
        findings_payload = (settled.get("extensions") or {}).get("review-findings/v1")
        if isinstance(findings_payload, Mapping):
            findings = findings_payload.get("findings")
            if isinstance(findings, list) and findings:
                lines.extend(_render_findings(findings, run_id=run_id))
        return lines

    if inherited_from is not None:
        attempt_number, prior_settled = inherited_from
        data = prior_settled.get("data", {})
        lines = [
            f"  JUDGED: verdict inherited from attempt {attempt_number}'s settlement "
            f"(assurance={data.get('assurance_id', '-')} verdict={data.get('verdict', '-')}) "
            "-- STATE-DELIVERY item 8 (verdict inheritance): no fresh assurance was requested "
            "for this attempt because the re-observed candidate's fingerprint already had a "
            "settled verdict in this work's lineage"
        ]
        findings_payload = (prior_settled.get("extensions") or {}).get("review-findings/v1")
        if isinstance(findings_payload, Mapping):
            findings = findings_payload.get("findings")
            if isinstance(findings, list) and findings:
                lines.extend(_render_findings(findings, run_id=run_id))
        return lines

    started = _first(records, "fact", FACT_ASSURE_STARTED)
    if started is not None:
        assurance_id = started.get("data", {}).get("assurance_id", "-")
        return [f"  JUDGED: (pending -- assurance {assurance_id} in flight, verdict not yet recorded)"]

    if wp is not None and has_candidate_conflict(wp) and _first(records, "fact", FACT_CANDIDATE_OBSERVED) is not None:
        return [
            "  JUDGED: candidate-observation conflict -- the re-observed candidate's fingerprint "
            "does not match a settled prior attempt, so neither a fresh assurance request nor "
            "verdict inheritance applies (STATE-DELIVERY item 9); operator resolution: orc "
            f"dispatch --run-id {wp.delivery_run_id} --abandon-work {wp.work_id} "
            '--abandon-reason "<why>"'
        ]

    if _first(records, "fact", FACT_CANDIDATE_OBSERVED) is None:
        return ["  JUDGED: (no candidate produced this attempt -- nothing to assure)"]
    return ["  JUDGED: (not yet assured this attempt)"]


def _render_next_deeper(records: Sequence[Mapping[str, Any]]) -> list[str]:
    rows = []
    settled = _first(records, "fact", FACT_EXEC_SETTLED)
    rows.extend(_execution_session_rows([settled] if settled is not None else []))
    assure_settled = _first(records, "fact", FACT_ASSURE_SETTLED)
    rows.extend(_evidence_ref_rows([assure_settled] if assure_settled is not None else []))
    identify_effect = _first(records, "effect", FX_IDENTIFY_CANDIDATE)
    rows.extend(_candidate_rows([identify_effect] if identify_effect is not None else []))
    if not rows:
        return []
    lines = ["  NEXT/DEEPER:"]
    lines.extend(f"    {_row_line(row)}" for row in rows)
    return lines


# ---------------------------------------------------------------------------
# Per-work rendering
# ---------------------------------------------------------------------------


def _render_work(
    work_id: str,
    *,
    history: Sequence[Mapping[str, Any]],
    projection: DeliveryProjection,
    times: Mapping[int, str],
    config: Optional[Mapping[str, Any]],
    intent_text: Optional[str],
    run_id: str,
    config_path: Path,
) -> None:
    wp = projection.works.get(work_id)
    records = _work_records(history, work_id)
    attempts = _segment_attempts(records)

    print(f"work {work_id}:")
    provenance = prompt_provenance(config, work_id, intent_text)

    # fingerprint -> (attempt_number, FACT-ASSURE-SETTLED record) for every
    # attempt already walked, in attempt order -- verdict inheritance
    # (STATE-DELIVERY item 8) looks a re-observed candidate's fingerprint
    # up against this map; a later match overwrites an earlier one, since
    # `_settled_assurance_for_candidate` (the reducer's own inheritance
    # source) takes the *most recent* settled assurance for that candidate.
    settled_by_fingerprint: dict[str, tuple[Any, Mapping[str, Any]]] = {}

    for attempt_number, attempt_records in attempts:
        print(f"  attempt {attempt_number}:")
        for line in _render_asked(provenance, work_id=work_id, run_id=run_id, config_path=config_path):
            print(line)
        for line in _render_executed(attempt_records, times):
            print(line)
        for line in _render_produced(attempt_records):
            print(line)

        candidate_observed = _first(attempt_records, "fact", FACT_CANDIDATE_OBSERVED)
        own_settled = _first(attempt_records, "fact", FACT_ASSURE_SETTLED)
        inherited_from = None
        if own_settled is None and candidate_observed is not None:
            fingerprint = candidate_observed.get("data", {}).get("fingerprint")
            if isinstance(fingerprint, str) and fingerprint in settled_by_fingerprint:
                inherited_from = settled_by_fingerprint[fingerprint]

        for line in _render_judged(attempt_records, run_id=run_id, inherited_from=inherited_from, wp=wp):
            print(line)
        for line in _render_next_deeper(attempt_records):
            print(line)

        if own_settled is not None and isinstance(candidate_observed, Mapping):
            fingerprint = candidate_observed.get("data", {}).get("fingerprint")
            if isinstance(fingerprint, str):
                settled_by_fingerprint[fingerprint] = (attempt_number, own_settled)

    if wp is not None:
        trailer = f"  now at {wp.state} (attempts={wp.attempt_number}"
        if wp.blocked_reason:
            trailer += f", blocked_reason={wp.blocked_reason}"
        trailer += ")"
        print(trailer)


# ---------------------------------------------------------------------------
# Run-level rendering + CLI entry point
# ---------------------------------------------------------------------------


def _summarize_states(projection: DeliveryProjection) -> tuple[bool, bool]:
    any_blocked = any(wp.state == STATE_BLOCKED for wp in projection.works.values())
    any_non_accepted = any(wp.state != STATE_ACCEPTED for wp in projection.works.values())
    return any_blocked, any_non_accepted


def _exit_code_for(any_blocked: bool, any_non_accepted: bool) -> int:
    if any_blocked:
        return 1
    if any_non_accepted:
        return _EXIT_PENDING
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    directory, run_id = _resolve_journal(args.run, args.journal)
    _require_journal_file(directory, run_id, target=args.run)
    journal = JSONLJournal(directory)
    try:
        history = journal.history(delivery_run_id=run_id)
        projection = journal.load_projection(delivery_run_id=run_id)
    except CoreError as exc:
        raise _diagnose_replay_conflict(exc, run_id=run_id) from exc

    all_work_ids = _work_ids_in_order(history)
    if args.work is not None:
        if args.work not in all_work_ids:
            raise not_found_error(
                f"work {args.work!r} not found in run {run_id!r}",
                run_id=run_id,
                work_id=args.work,
                next_steps=[
                    f"orc status {run_id} for this run's actual work ids"
                    + (f": {', '.join(sorted(all_work_ids))}" if all_work_ids else " (none recorded yet)"),
                    f"orc show {run_id} for every work",
                ],
            )
        work_ids = [args.work]
    else:
        work_ids = sorted(all_work_ids)

    intent_text = _intent_text(history)
    times, _skipped = _load_times_sidecar(directory, run_id)
    config = _load_persisted_config(directory, run_id)
    config_path = layout.config_path(directory, run_id).resolve()

    print(f"run: {run_id}")
    if intent_text is not None:
        first_line = intent_text.splitlines()[0] if intent_text else ""
        suffix = " (...)" if len(intent_text) > len(first_line) else ""
        print(f"intent: {first_line}{suffix}")
    else:
        print("intent: (no intent text recorded)")
    if projection.works:
        summary = ", ".join(
            f"{wid}={projection.works[wid].state} attempts={projection.works[wid].attempt_number}"
            for wid in sorted(projection.works)
        )
        print(f"works: {summary}")
    else:
        print("(no work recorded yet)")

    for work_id in work_ids:
        _render_work(
            work_id,
            history=history,
            projection=projection,
            times=times,
            config=config,
            intent_text=intent_text,
            run_id=run_id,
            config_path=config_path,
        )

    any_blocked, any_non_accepted = _summarize_states(projection)
    exit_code = _exit_code_for(any_blocked, any_non_accepted)
    if exit_code == _EXIT_PENDING:
        pending_ids = [wid for wid, wp in projection.works.items() if is_pending(wp)]
        print(
            "pending: run is non-terminal, awaiting operator-recorded input for: "
            + ", ".join(sorted(pending_ids) if pending_ids else sorted(projection.works))
        )
    for line in render_next_block(
        projection,
        history,
        run_id=run_id,
        journal_dir=directory.resolve(),
        config_path=None,
        intent_text=intent_text,
    ):
        print(line)
    return exit_code


__all__ = ["cmd_show", "prompt_provenance"]
