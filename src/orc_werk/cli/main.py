"""`orc` CLI (`TASK-M0-005`, `TASK-M1-002`): `dispatch`, `status`, `history`
over the M0 orchestrator with the dependency-free memory/scripted/JSONL
adapters.

Exit codes (`docs/playbooks/cli-usage.md`): `0` on an ACCEPTED-terminal
(all Work accepted); `1` when any Work is BLOCKED (or otherwise reaches a
non-accepted terminal state); `2` on a canonical error; `3` when the run is
non-terminal and pending operator input -- a Work is resting at
`EXECUTING`/`ASSURING` because its current attempt's outcome has not been
recorded yet (`SCN-007`, `STATE-DELIVERY` mechanical fact sequencing item
7). `3` is the M1a pending/incremental-mode default's distinct in-progress
exit code, additive to the `0`/`1`/`2` contract, never a replacement of
it. Errors print the canonical error value (`CONTRACT-ERRORS`) as JSON to
stderr, never a Python traceback.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.metadata
import json
import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.jsonl import layout
from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.app.orchestrator import Orchestrator, is_pending
from orc_werk.cli.affordances import redispatch_command, render_next_block
from orc_werk.cli import config as config_module
from orc_werk.cli.config import (
    _ASSURANCE_ADAPTERS,
    _CANDIDATE_ADAPTERS,
    _EXECUTION_ADAPTERS,
    _MIRROR_ADAPTERS,
    build_dispatch_ports,
    build_mirror,
    build_run_config,
    build_scripted_adapters,
    deep_merge_config,
    load_config,
    load_config_overlay,
    load_repo_profile,
    record_assurance_entry,
    validate_config,
)
from orc_werk.cli.hyperlink import hyperlink_path
from orc_werk.cli.journal_reading import (
    BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED,
    _available_run_ids,
    _awaiting_label,
    _diagnose_replay_conflict,
    _intent_text,
    _require_journal_file,
    _resolve_journal,
    _root_cause_for_work,
    resolve_journal_dir,
)
from orc_werk.cli.onboard import DEFAULT_AGENTS_FILE, cmd_onboard
from orc_werk.cli.pagination import DEFAULT_LIMIT, paginate, size_hint, window_before
from orc_werk.cli.refs import FACT_ASSURE_SETTLED, cmd_refs
from orc_werk.cli.report import _index_state_rollup, cmd_report, ordered_run_entries
from orc_werk.cli.show import _render_findings, cmd_show
from orc_werk.core.errors import CoreError, conflict_error, not_found_error, validation_error
from orc_werk.core.state import STATE_ACCEPTED, STATE_ASSURING, STATE_BLOCKED, STATE_EXECUTING, WorkProjection
from orc_werk.ports.capabilities import validate_capabilities

# TASK-M1-002/SCN-007: the distinct in-progress exit code -- additive to
# the existing 0 (all ACCEPTED) / 1 (any BLOCKED) / 2 (canonical error)
# contract in docs/playbooks/cli-usage.md, never a replacement of it.
# Reported whenever the run is non-terminal and nothing further can be
# decided without operator-recorded input (a pending Work resting at
# EXECUTING/ASSURING with an unobserved outcome, or -- degenerate v0 edge
# case, not exercised by any golden scenario -- any other non-terminal
# resting point `_advance_one_phase` cannot progress past).
EXIT_PENDING = 3


def _work_line(work_id: str, wp: WorkProjection, history: Sequence[Mapping[str, Any]]) -> str:
    fingerprint = wp.current_candidate_fingerprint() or "-"
    line = (
        f"work {work_id}: state={wp.state} attempts={wp.attempt_number} "
        f"candidate_fingerprint={fingerprint}"
    )
    if wp.blocked_reason:
        line += f" blocked_reason={wp.blocked_reason}"
        if wp.blocked_reason == BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED:
            # #16: a statically-doomed run burns the whole retry budget and
            # reports this same generic reason as an organically flaky one
            # -- surface the underlying cause from the journaled effect
            # records alongside it. Mixed causes across attempts: show the
            # most recent (`_root_cause_for_work`).
            root_cause = _root_cause_for_work(history, work_id)
            if root_cause:
                line += f" (root_cause={root_cause})"
    if is_pending(wp):
        # SCN-007: legible per-work pending presentation -- which attempt,
        # and awaiting an execution settlement or an assurance verdict.
        line += f" pending=true awaiting={_awaiting_label(wp)} attempt={wp.attempt_number}"
    return line


def _summarize_works(projection) -> tuple[bool, bool]:
    """Return `(any_blocked, any_non_accepted)` over `projection.works`."""
    any_blocked = False
    any_non_accepted = False
    for wp in projection.works.values():
        if wp.state == STATE_BLOCKED:
            any_blocked = True
        if wp.state != STATE_ACCEPTED:
            any_non_accepted = True
    return any_blocked, any_non_accepted


def _exit_code_for(any_blocked: bool, any_non_accepted: bool) -> int:
    if any_blocked:
        return 1
    if any_non_accepted:
        # Non-terminal and not (yet) blocked: SCN-007 pending, or -- the
        # only other v0 way to reach this branch -- some other resting
        # point the run loop could not progress past (no golden scenario
        # exercises that case; see orchestrator.py's `_identify_candidate`
        # docstring). Either way, "0" would be a lie (not every Work is
        # ACCEPTED), so this reports the distinct in-progress code rather
        # than silently reusing "1" (BLOCKED implies a confirmed terminal
        # outcome, which this is not).
        return EXIT_PENDING
    return 0


def _derive_run_id(intent_text: str) -> str:
    """Deterministic run id from the intent text (CLAUDE.md #9-friendly:
    no randomness/wall-clock). Callers wanting a stable run id across
    reruns should pass `--run-id`/config `run_id` explicitly instead."""
    digest = hashlib.sha256(intent_text.encode("utf-8")).hexdigest()[:12]
    return f"run-{digest}"


def _print_error(error: dict) -> None:
    print(json.dumps(error, sort_keys=True), file=sys.stderr)


def _persist_effective_config(path: Path, config: Mapping[str, Any]) -> None:
    """Issue #55 H2 config persistence: durably copy the effective dispatch
    config into the run's own directory (`<journal_dir>/<run_id>/
    config.json`) so a later dispatch of the same run -- a fresh session
    with no memory of the original `--config` path included -- can resume
    with just the run id (`cmd_dispatch`'s own load-time fallback below).
    Called only after `orchestrator.run()` has already durably journaled
    something for this dispatch, so a config that fails validation, or a
    dispatch that never reaches a journal write, never leaves a stray
    config.json (or run directory) behind.

    Best-effort, mirroring `JSONLJournal`'s own observed-at sidecar stance
    (`orc_werk.adapters.jsonl.journal`'s module docstring): a dispatch that
    has already durably succeeded must never be reported as failed --or,
    worse, retried and duplicated-- merely because this convenience copy
    could not be written (permissions, a full disk, whatever)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(config), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _package_version(package_dir: Path) -> str:
    """Return installed metadata first, then a source-checkout fallback."""
    try:
        return importlib.metadata.version("orc-werk")
    except Exception:  # noqa: BLE001 -- identity reporting must always degrade
        pass

    try:
        # Source layout is <repo>/src/orc_werk. Keep the fallback local to
        # that shape so a wheel cannot borrow an unrelated ancestor's
        # pyproject version.
        for parent in (package_dir, *package_dir.parents[:2]):
            pyproject = parent / "pyproject.toml"
            if pyproject.is_file():
                project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
                version = project.get("version")
                if isinstance(version, str):
                    return version
    except Exception:  # noqa: BLE001 -- malformed/unreadable source metadata degrades
        pass
    return "unknown (not installed)"


def _git_identity(package_dir: Path) -> str:
    """Describe the checkout containing package_dir, without requiring git."""
    command = ["git", "-C", str(package_dir)]
    try:
        sha = subprocess.run(
            [*command, "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:  # noqa: BLE001 -- absent/broken git must not break a wheel
        return "git unavailable"
    if sha.returncode != 0 or not sha.stdout.strip():
        return "git: not a checkout"
    try:
        status = subprocess.run(
            [*command, "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:  # noqa: BLE001 -- the known commit remains honest
        return f"git {sha.stdout.strip()}"
    dirty = "+dirty" if status.returncode == 0 and status.stdout else ""
    return f"git {sha.stdout.strip()}{dirty}"


def _version_report(package_dir: Optional[Path] = None) -> str:
    source = (package_dir or Path(__file__).resolve().parent.parent).resolve()
    return f"orc {_package_version(source)} (source {source}, {_git_identity(source)})"


def cmd_version(_args: argparse.Namespace) -> int:
    """Print package and source-checkout identity without touching the ledger."""
    print(_version_report())
    return 0


def cmd_config_schema(_args: argparse.Namespace) -> int:
    """Print the single-source dispatch config reference verbatim."""
    sys.stdout.write(config_module.__doc__ or "")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate and preview a composed dispatch config without run machinery."""
    journal_dir = resolve_journal_dir(args.journal)
    explicit = load_config_overlay(args.config)
    profile_path = journal_dir.resolve() / "profile.json"
    profile = None if args.no_profile else load_repo_profile(journal_dir)
    config = validate_config(deep_merge_config(profile or {}, explicit))

    plan = config.get("plan")
    if isinstance(plan, Mapping):
        works = [str(work.get("work_id")) for work in plan.get("works", ()) if isinstance(work, Mapping)]
    else:
        works = ["work-1 (default)"]
    print(f"PASS: {args.config}")
    if profile is not None:
        profile_keys = ", ".join(sorted(profile)) or "empty"
        print(f"layers: profile: {profile_path} ({profile_keys}) + config: {args.config}")
    else:
        print(f"layers: config: {args.config}")
    print(f"plan works: {', '.join(works) if works else '(none)'}")
    print(
        "adapters: "
        f"execution={(config.get('execution') or {}).get('adapter', 'scripted')} "
        f"candidate={(config.get('candidate') or {}).get('adapter', 'scripted')} "
        f"assurance={(config.get('assurance') or {}).get('adapter', 'scripted')}"
    )
    for work_id, entries in (config.get("attempts") or {}).items():
        for index, entry in enumerate(entries):
            print(f"attempts.{work_id}[{index}]: keys=[{', '.join(sorted(entry))}]")
            assurance = entry.get("assurance")
            if isinstance(assurance, Mapping):
                verdict = assurance.get("verdict", "(absent)")
                extensions = assurance.get("extensions") or {}
                print(
                    f"attempts.{work_id}[{index}].assurance: verdict={verdict}, "
                    f"extensions=[{', '.join(sorted(extensions))}]"
                )
    return 0


def _candidate_identity(value: Any) -> Any:
    """Return the operator-facing identity from a configured/bound candidate."""
    if isinstance(value, Mapping):
        subject = value.get("subject_identity")
        if isinstance(subject, Mapping):
            return dict(subject)
        return dict(value)
    return value


def _candidate_identity_text(value: Any) -> str:
    identity = _candidate_identity(value)
    if isinstance(identity, Mapping) and identity.get("head_sha") is not None:
        return str(identity["head_sha"])
    return json.dumps(identity, sort_keys=True, separators=(",", ":"))


def _warn_candidate_divergence(
    config: Mapping[str, Any], projection: Any, history: Sequence[Mapping[str, Any]], *,
    run_id: str, config_path: Path,
) -> None:
    """Warn when an edited scripted attempt disagrees with its journal binding."""
    attempts = config.get("attempts") or {}
    for work_id, wp in projection.works.items():
        if wp.current_candidate_id is None or wp.attempt_number < 1:
            continue
        entries = attempts.get(work_id) or []
        if len(entries) < wp.attempt_number:
            continue
        configured = entries[wp.attempt_number - 1].get("candidate")
        if configured is None:
            continue
        bound = None
        for record in reversed(history):
            candidate = record.get("data", {}).get("dispatch_result", {}).get("candidate")
            if (
                record.get("kind") == "effect"
                and record.get("data", {}).get("work_id") == work_id
                and isinstance(candidate, Mapping)
                and candidate.get("id") == wp.current_candidate_id
            ):
                bound = candidate
                break
        if bound is None or _candidate_identity(configured) == _candidate_identity(bound):
            continue
        configured_text = _candidate_identity_text(configured)
        bound_text = _candidate_identity_text(bound)
        print(
            f"warning: config candidate ({configured_text}) differs from the bound "
            f"attempt-{wp.attempt_number} candidate ({bound_text}); candidates are immutable "
            "per attempt -- to open a fresh attempt: orc dispatch "
            f"--run-id {run_id} --config {config_path} --abandon-work {work_id} "
            '--abandon-reason "<why>"',
            file=sys.stderr,
        )


def cmd_dispatch(args: argparse.Namespace) -> int:
    journal_dir = resolve_journal_dir(args.journal)
    existing_run_ids = set(layout.discover_run_ids(journal_dir))

    if args.intent is None:
        if not args.run_id or args.run_id not in existing_run_ids:
            raise validation_error(
                "intent is required when dispatching a new run; to resume an existing run use "
                "orc dispatch --run-id <id>",
                run_id=args.run_id,
                next_steps=[
                    f"ORC_JOURNAL_DIR={journal_dir.resolve()} orc to list existing run ids",
                    'orc dispatch "<intent text>" --config <path-to-dispatch-config.json> to start new work',
                ],
            )
        existing_history = JSONLJournal(journal_dir).history(delivery_run_id=args.run_id)
        intent_text = _intent_text(existing_history)
        if intent_text is None:
            raise validation_error(
                f"run {args.run_id!r} has no journaled intent; supply the positional intent",
                run_id=args.run_id,
                next_steps=[
                    f'orc dispatch "<intent text>" --config <path-to-dispatch-config.json> '
                    f"--run-id {args.run_id} --journal {journal_dir.resolve()}",
                ],
            )
    else:
        intent_text = args.intent

    # TASK-M4A-001 config layering.  The profile is discovered only at
    # <resolved-journal-dir>/profile.json (normally <repo>/.orc/profile.json).
    # Each higher layer recursively overrides the one below it.
    profile = load_repo_profile(journal_dir) or {}
    explicit = load_config_overlay(args.config) if args.config else {}
    run_id = args.run_id or explicit.get("run_id") or _derive_run_id(intent_text)
    persisted_config_path = layout.config_path(journal_dir, run_id)
    persisted = load_config(str(persisted_config_path)) if persisted_config_path.exists() else {}
    config = validate_config(
        deep_merge_config(deep_merge_config(profile, persisted), explicit)
    )
    run_id = args.run_id or config.get("run_id") or run_id

    if run_id not in existing_run_ids and intent_text in existing_run_ids:
        raise validation_error(
            f"intent {intent_text!r} is also existing run id {intent_text!r}: to resume, run "
            f"orc dispatch --run-id {intent_text}; if this is genuinely new work, reword the intent",
            intent=intent_text,
            existing_run_id=intent_text,
            next_steps=[f"orc dispatch --run-id {intent_text} --journal {journal_dir.resolve()}"],
        )

    # #17 comment fix: finish every config-derived validation
    # (`build_scripted_adapters`/`build_run_config`, e.g. BUG-2's
    # max_attempts check) *before* constructing `JSONLJournal`, whose
    # `__init__` `mkdir`s the journal directory as a side effect -- a
    # rejected config must never leave a stray empty `.orc/` behind.
    # `TASK-M1-005` CLI wiring: `validate_capabilities` here is a
    # deliberate pre-check duplicate of the one `build_scripted_adapters`/
    # `build_dispatch_ports` perform internally -- it is pure (no side
    # effect) and lets an invalid `execution_capabilities` id fail closed
    # before the journal mkdir on *every* adapter-selection path below,
    # including the real-port path, which (per `build_dispatch_ports`'s own
    # docstring) needs the journal to already exist so it can read the
    # run's own history for the real-candidate assurance script.
    work_graph = MemoryWorkGraph()
    validate_capabilities(config.get("execution_capabilities", ()))
    run_config = build_run_config(config, max_attempts_override=args.max_attempts)

    execution_adapter = (config.get("execution") or {}).get("adapter", "scripted")
    candidate_adapter = (config.get("candidate") or {}).get("adapter", "scripted")
    if args.abandon_work is not None or (
        execution_adapter == "scripted" and candidate_adapter == "scripted"
    ):
        execution, candidate, assurance = build_scripted_adapters(config, delivery_run_id=run_id)
        journal = JSONLJournal(journal_dir)
    else:
        journal = JSONLJournal(journal_dir)
        execution, candidate, assurance = build_dispatch_ports(
            config, delivery_run_id=run_id, intent_text=intent_text, journal=journal
        )

    orchestrator = Orchestrator(
        delivery_run_id=run_id,
        journal=journal,
        work_graph=work_graph,
        execution=execution,
        candidate=candidate,
        assurance=assurance,
        config=run_config,
    )
    plan = config.get("plan")
    # issue #55 H2 config persistence: whether to persist/refresh below is
    # decided from the journal's *pre-dispatch* state -- "first dispatch"
    # means this run had no history at all before this call, checked here
    # (read-only, before bootstrap's own first append) rather than after,
    # since bootstrap/run below will have already written records by then.
    is_first_dispatch = not journal.history(delivery_run_id=run_id)
    orchestrator.bootstrap(intent_id=run_id, text=intent_text, plan=plan)

    abandoned_attempt: Optional[int] = None
    if args.abandon_work is not None:
        # TASK-M3B-001 (issues #76/#95): operator-only surface, never the
        # ship/verify agent observation path. This invocation stops at the
        # READY/BLOCKED resting state produced by the journal-only abandon;
        # a later real-config dispatch owns the next port effect (#165).
        if not args.abandon_reason:
            raise validation_error(
                "--abandon-work requires --abandon-reason",
                next_steps=[
                    f'orc dispatch --run-id {run_id} --journal {journal_dir.resolve()} '
                    f'--abandon-work {args.abandon_work} --abandon-reason "<why>"'
                ],
            )
        by = args.abandon_by or os.environ.get("USER") or getpass.getuser()
        wp = orchestrator.projection().works.get(args.abandon_work)
        abandoned_attempt = wp.attempt_number if wp else None
        orchestrator.abandon_attempt(work_id=args.abandon_work, reason=args.abandon_reason, by=by)

    # Snapshot the durable boundary so the output below can identify only
    # assurance settlements folded by this dispatch invocation.
    history_before_advance = journal.history(delivery_run_id=run_id)
    pre_advance_projection = orchestrator.projection()
    _warn_candidate_divergence(
        config,
        pre_advance_projection,
        history_before_advance,
        run_id=run_id,
        config_path=persisted_config_path.resolve(),
    )
    projection = pre_advance_projection if args.abandon_work is not None else orchestrator.run()
    history = journal.history(delivery_run_id=run_id)

    # `TASK-M2-006`: optional, write-only Beads mirror -- absent `mirror`
    # config (the default) means `build_mirror` returns `None` and this
    # block never runs at all, so every existing config's dispatch output
    # is byte-identical to before this task. Placed AFTER `orchestrator.
    # run()` so it only ever projects durable, already-journaled state
    # (module docstring, `orc_werk.adapters.beads.mirror`: a projection
    # consumer of journal-derived state, never a driver of dispatch
    # decisions). A degraded mirror (one or more `bd` calls failed) is
    # reported to stderr only -- never a dispatch failure, never a change
    # to `exit_code` (mirror failures MUST NEVER break the delivery loop,
    # per the task card).
    mirror = build_mirror(config)
    if mirror is not None:
        mirror_report = mirror.project_run(
            delivery_run_id=run_id,
            history=history,
            projection=projection,
            briefs=config.get("briefs"),
            intent_text=intent_text,
        )
        if mirror_report.degraded:
            failed = len(mirror_report.errors)
            total = len(mirror_report.calls)
            print(
                f"mirror: degraded ({failed} of {total} bd call(s) failed) -- "
                "kernel/journal state is unaffected; see stderr detail below",
                file=sys.stderr,
            )
            for call in mirror_report.errors:
                print(f"mirror: bd {' '.join(call.argv[1:])} -> exit {call.returncode}: {call.stderr.strip()}", file=sys.stderr)

    if is_first_dispatch or args.config:
        # "on first dispatch" (always persist once) OR "explicit --config
        # still wins and refreshes the persisted copy" (issue #55 H2).
        # Placed after orchestrator.run() so the run's own directory (new
        # layout) already exists by the time this writes into it -- never
        # created ahead of a successful dispatch.
        _persist_effective_config(layout.config_path(journal_dir, run_id), config)

    print(f"run: {run_id}")
    # #40 comment: print the RESOLVED ABSOLUTE path, not a relative one --
    # a printed relative path (e.g. `.orc/x.jsonl`) is not reliably
    # clickable in a terminal when the reader's cwd differs from the
    # process's; `.resolve()` makes it absolute and normalizes it the same
    # way `orc report`'s printed paths now do (see orc_werk.cli.report).
    # issue #55 H1: resolve via `layout.journal_path` (new per-run-dir
    # layout, or legacy flat file for a pre-#55 run) instead of assuming
    # the old flat `<run_id>.jsonl` shape; issue #55 OSC-8 scope addition:
    # this "journal:" line is a standalone printed path, so it gets the
    # clickable-path treatment (`orc_werk.cli.hyperlink`).
    print(f"journal: {hyperlink_path(layout.journal_path(journal_dir, run_id).resolve())}")
    for work_id in sorted(projection.works):
        print(_work_line(work_id, projection.works[work_id], history))
    any_blocked, any_non_accepted = _summarize_works(projection)
    exit_code = _exit_code_for(any_blocked, any_non_accepted)
    if exit_code == EXIT_PENDING:
        pending_ids = [wid for wid, wp in projection.works.items() if is_pending(wp)]
        print(
            "pending: run is non-terminal, awaiting settlement observation or operator-recorded input for: "
            + ", ".join(sorted(pending_ids) if pending_ids else sorted(projection.works))
        )
    if args.abandon_work is not None:
        state = projection.works[args.abandon_work].state
        redispatch = (
            f"orc dispatch --run-id {run_id} --journal {journal_dir.resolve()} "
            f"--config {persisted_config_path.resolve()}"
        )
        if state == "READY":
            print(
                f"attempt {abandoned_attempt} abandoned ({args.abandon_reason}); work "
                f"{args.abandon_work} now READY -- next attempt starts on the next dispatch "
                f"with the run's real config: {redispatch}"
            )
        else:
            print(
                f"attempt {abandoned_attempt} abandoned ({args.abandon_reason}); work "
                f"{args.abandon_work} now {state}"
            )

    # Issues #147/#150: report only settlements durably appended by this
    # invocation.  Reading the canonical records back makes this proof of
    # ingestion rather than an echo of the config input.
    previous_seq = max((record["seq"] for record in history_before_advance), default=0)
    new_records = [record for record in history if record["seq"] > previous_seq]
    settled_assurances = [
        record
        for record in new_records
        if record.get("kind") == "fact" and record.get("id") == FACT_ASSURE_SETTLED
    ]
    for record in settled_assurances:
        data = record["data"]
        extension_keys = ", ".join(sorted(record.get("extensions", {})))
        corroborated = any(
            "derived_identity" in (attempt.get("assurance") or {})
            for attempt in (config.get("attempts") or {}).get(data["work_id"], [])
        )
        corroboration_note = " -- derived_identity corroborated" if corroborated else ""
        print(
            f"assurance recorded: work {data['work_id']!r} verdict={data['verdict']} "
            f"extensions=[{extension_keys}] (seq {record['seq']}){corroboration_note}"
        )
        retry = next(
            (
                item
                for item in new_records
                if item["seq"] > record["seq"]
                and item.get("kind") == "decision"
                and item.get("id") == "DEC-RETRY"
                and item.get("data", {}).get("work_id") == data["work_id"]
            ),
            None,
        )
        work = projection.works.get(data["work_id"])
        if (
            data["verdict"] == "rejected"
            and retry is not None
            and work is not None
            and work.state == STATE_EXECUTING
            and is_pending(work)
        ):
            attempt = retry["data"]["attempt_number"]
            print(
                f"assurance verdict recorded (rejected); attempt {attempt} opened -- "
                "the next action belongs to the EXECUTION seat, not the verifier."
            )

    # issue #43: HATEOAS-style "next:" block, one mapping
    # (orc_werk.cli.affordances) shared by dispatch/status. `dispatch`
    # knows the config path it was actually invoked with, so its
    # re-dispatch command is fully concrete.
    for line in render_next_block(
        projection,
        history,
        run_id=run_id,
        journal_dir=journal_dir.resolve(),
        config_path=Path(args.config).resolve() if args.config else None,
        intent_text=intent_text,
    ):
        print(line)
    return exit_code


def cmd_record(args: argparse.Namespace) -> int:
    """Record, but never dispatch, the current requested assurance verdict."""
    directory, run_id = _resolve_journal(args.target, args.journal)
    _require_journal_file(directory, run_id, target=args.target)
    journal = JSONLJournal(directory)
    history = journal.history(delivery_run_id=run_id)
    projection = journal.load_projection(delivery_run_id=run_id)
    work = projection.works.get(args.work)
    if work is None:
        raise not_found_error(
            f"no work {args.work!r} in run {run_id!r}",
            delivery_run_id=run_id,
            work_id=args.work,
            next_steps=[f"actual work ids: {', '.join(sorted(projection.works))}"],
        )
    if work.state != STATE_ASSURING or not is_pending(work):
        actual = _awaiting_label(work) if is_pending(work) else work.state
        raise conflict_error(
            f"work {args.work!r} is not awaiting an assurance verdict (actual pending state: {actual})",
            delivery_run_id=run_id,
            work_id=args.work,
            actual_pending_state=actual,
        )

    derived = None
    if args.derived_identity is not None:
        try:
            derived = json.loads(args.derived_identity)
        except json.JSONDecodeError as exc:
            raise validation_error("--derived-identity must be a JSON object", value=args.derived_identity) from exc
        if not isinstance(derived, Mapping):
            raise validation_error("--derived-identity must be a JSON object", value=args.derived_identity)

    extensions: dict[str, Any] = {}
    if args.finding:
        extensions["review-findings/v1"] = {"findings": list(args.finding)}
    identity = {
        key: value for key, value in (
            ("model", args.model), ("session_ref", args.session_ref), ("seat_ref", args.seat_ref)
        ) if value is not None
    }
    if identity:
        identity["role"] = "verify"
        extensions["executor-identity/v1"] = identity
    assurance: dict[str, Any] = {"verdict": args.verdict}
    if args.evidence_ref:
        assurance["evidence_refs"] = list(args.evidence_ref)
    if extensions:
        assurance["extensions"] = extensions
    if derived is not None:
        assurance["derived_identity"] = derived

    config_path = layout.config_path(directory, run_id)
    if not config_path.exists():
        raise not_found_error(
            f"run {run_id!r} has no persisted backing config",
            delivery_run_id=run_id,
            path=str(config_path),
        )
    record_assurance_entry(
        config_path, work_id=args.work, attempt_number=work.attempt_number, assurance=assurance
    )
    extension_names = ",".join(sorted(extensions)) or "none"
    print(
        f"recorded assurance: run={run_id} work={args.work} verdict={args.verdict} "
        f"extensions=[{extension_names}]"
    )
    print("next:")
    print("  - " + redispatch_command(
        run_id=run_id,
        journal_dir=directory.resolve(),
        config_path=config_path.resolve(),
        intent_text=_intent_text(history),
    ))
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    directory, run_id = _resolve_journal(args.target, args.journal)
    _require_journal_file(directory, run_id, target=args.target)
    if not args.reason:
        raise validation_error(
            "orc cancel requires --reason",
            next_steps=[f'orc cancel {run_id} --work {args.work} --reason "<why>"'],
        )
    journal = JSONLJournal(directory)
    history = journal.history(delivery_run_id=run_id)
    intent_text = _intent_text(history) or ""
    profile = load_repo_profile(directory) or {}
    persisted_path = layout.config_path(directory, run_id)
    persisted = load_config(str(persisted_path)) if persisted_path.exists() else {}
    config = validate_config(deep_merge_config(profile, persisted))
    run_config = build_run_config(config, max_attempts_override=None)
    work_graph = MemoryWorkGraph()
    execution, candidate, assurance = build_scripted_adapters(config, delivery_run_id=run_id)
    orchestrator = Orchestrator(
        delivery_run_id=run_id,
        journal=journal,
        work_graph=work_graph,
        execution=execution,
        candidate=candidate,
        assurance=assurance,
        config=run_config,
    )
    by = os.environ.get("USER") or getpass.getuser()
    orchestrator.cancel_work(work_id=args.work, reason=args.reason, by=by)
    state = orchestrator.projection().works[args.work].state
    print(f"cancelled work {args.work} in run {run_id}: state={state}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    directory, run_id = _resolve_journal(args.target, args.journal)
    _require_journal_file(directory, run_id, target=args.target)
    journal = JSONLJournal(directory)
    try:
        history = journal.history(delivery_run_id=run_id)
        projection = journal.load_projection(delivery_run_id=run_id)
    except CoreError as exc:
        raise _diagnose_replay_conflict(exc, run_id=run_id, self_is_status=True) from exc

    print(f"run: {run_id}")
    intent_text = _intent_text(history)
    if intent_text is not None:
        print(f"intent: {intent_text}")
    if not projection.works:
        print("(no work recorded yet)")
        return 0

    for work_id in sorted(projection.works):
        print(_work_line(work_id, projection.works[work_id], history))
    any_blocked, any_non_accepted = _summarize_works(projection)
    exit_code = _exit_code_for(any_blocked, any_non_accepted)
    if exit_code == EXIT_PENDING:
        pending_ids = [wid for wid, wp in projection.works.items() if is_pending(wp)]
        print(
            "pending: run is non-terminal, awaiting settlement observation or operator-recorded input for: "
            + ", ".join(sorted(pending_ids) if pending_ids else sorted(projection.works))
        )
    # issue #43: same shared "next:" mapping as dispatch. `status` never
    # received a `--config`, so its re-dispatch command (when one is
    # needed) renders the config path as an explicit placeholder rather
    # than inventing one (CLAUDE.md #3).
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


def _compact(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def cmd_verdict(args: argparse.Namespace) -> int:
    """Print each Work's latest journaled assurance outcome, without writing."""
    directory, run_id = _resolve_journal(args.target, args.journal)
    _require_journal_file(directory, run_id, target=args.target)
    journal = JSONLJournal(directory)
    history = journal.history(delivery_run_id=run_id)
    projection = journal.load_projection(delivery_run_id=run_id)
    latest: dict[str, Mapping[str, Any]] = {}
    for record in history:
        if record.get("kind") == "fact" and record.get("id") == FACT_ASSURE_SETTLED:
            work_id = record.get("data", {}).get("work_id")
            if isinstance(work_id, str):
                latest[work_id] = record

    print(f"run: {run_id}")
    for work_id in sorted(projection.works):
        record = latest.get(work_id)
        if record is None:
            print(f"work {work_id}: (no verdict yet)")
            continue
        data = record.get("data", {})
        print(
            f"work {work_id}: verdict={data.get('verdict', '-')} "
            f"candidate_fingerprint={data.get('candidate_fingerprint', '-')}"
        )
        if data.get("evidence_refs"):
            print(f"  evidence_refs={_compact(data['evidence_refs'])}")
        extensions = record.get("extensions") or {}
        if extensions:
            print(f"  extensions={','.join(sorted(extensions))}")
        findings = extensions.get("review-findings/v1")
        if isinstance(findings, Mapping) and isinstance(findings.get("findings"), list):
            for line in _render_findings(findings["findings"], run_id=run_id):
                print(line)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    directory, run_id = _resolve_journal(args.target, args.journal)
    _require_journal_file(directory, run_id, target=args.target)
    journal = JSONLJournal(directory)
    # `history()` reads raw envelopes only -- it never replays through
    # `core/reducer.py`, so it cannot raise `ERR-CONFLICT` (only
    # `load_projection`, wrapped with `_diagnose_replay_conflict`
    # elsewhere, can); nothing to enrich here.
    records = list(journal.history(delivery_run_id=run_id))
    print(f"run: {run_id}")
    # issue #43 pagination addendum: --since-seq filters first (an explicit
    # "what's new since I last looked" query), then the default/--limit
    # window applies to the (possibly filtered) result -- the size hint's
    # "of N" always names the exact count of what --limit 0 would show.
    if args.since_seq is not None:
        records = [r for r in records if r["seq"] > args.since_seq]
    window, total, truncated = window_before(
        records,
        limit=args.limit,
        before=args.before_seq,
        cursor_of=lambda record: str(record["seq"]),
        cursor_name="before-seq",
    )
    for record in window:
        line = f"[{record['seq']:04d}] {record['kind']:8s} {record['id']:28s} {_compact(record['data'])}"
        # FRICTION-1: the envelope's sibling `extensions` field (where e.g.
        # EXT-REVIEW-FINDINGS-V1 assurance findings travel, CONF-EXT-003)
        # is otherwise invisible in `orc history` output even though it was
        # journaled -- render it (compact, same line) when non-empty.
        extensions = record.get("extensions")
        if extensions:
            line += f" extensions={_compact(extensions)}"
        print(line)
    if truncated:
        print(size_hint(len(window), total, noun="records"))
        oldest_seq = window[0]["seq"]
        command = (
            f"orc history {shlex.quote(run_id)} --journal {shlex.quote(str(directory.resolve()))} "
            f"--limit {args.limit} --before-seq {oldest_seq}"
        )
        if args.since_seq is not None:
            command += f" --since-seq {args.since_seq}"
        print(f"next (older) page: {command}")
    return 0


def _index_work_summary(work_id: str, wp: WorkProjection) -> str:
    """One Work's compact index-line fragment: state, attempts, and a
    pending/blocked flag when relevant (issue #43 item 1: "run id, per-work
    state, attempts, pending flags"). Deliberately terser than
    `_work_line` (which also carries the candidate fingerprint) -- the bare
    index is a many-runs-at-a-glance scan, not a single-run detail view."""
    parts = [f"{work_id}={wp.state}", f"attempts={wp.attempt_number}"]
    if is_pending(wp):
        parts.append(f"pending={_awaiting_label(wp)}")
    if wp.blocked_reason:
        parts.append(f"blocked_reason={wp.blocked_reason}")
    return " ".join(parts)


def _index_run_line(run_id: str, projection) -> str:
    rollup, _active = _index_state_rollup(projection)
    if not projection.works:
        return f"{run_id}: states={rollup} (no work recorded yet)"
    summary = ", ".join(_index_work_summary(wid, projection.works[wid]) for wid in sorted(projection.works))
    return f"{run_id}: states={rollup} | {summary}"


def cmd_index(
    journal_dir: Optional[Path] = None,
    *,
    limit: int = DEFAULT_LIMIT,
    before: str | None = None,
    state: str | None = None,
) -> int:
    """`orc` with no arguments (issue #43 item 1, "content first" -- axi
    #8): a live text index of the default journal dir instead of an
    argparse usage error. Strictly read-only: never constructs
    `JSONLJournal` (whose `__init__` `mkdir`s the journal directory) unless
    the directory already exists and already has at least one run journal
    in it, so a bare `orc` in a fresh checkout creates nothing.

    Paginated the same way as `orc history` (issue #43 pagination
    addendum), most-recently-active runs first (by journal file mtime).
    `--limit 0` is the same-surface escape hatch; `orc report --index` is
    only the explicitly secondary HTML view.
    """
    # Validate before the empty-state fast return so an invalid bound is
    # rejected consistently even when there are no runs to list.
    paginate((), limit=limit)
    if state not in (None, "active"):
        raise validation_error(
            f"unsupported index state filter: {state}",
            state=state,
            next_steps=["orc --state active", "orc without --state to list every run"],
        )
    directory = journal_dir if journal_dir is not None else resolve_journal_dir(None)
    abs_dir = directory.resolve()
    # issue #55 OSC-8 scope addition: these two "N runs in <abs dir>"/"0
    # runs in <abs dir>" lines are standalone index lines.
    abs_dir_display = hyperlink_path(abs_dir)
    run_ids = _available_run_ids(directory)
    if not run_ids:
        if before is not None:
            window_before((), limit=limit, before=before, cursor_of=str, cursor_name="before")
        # Empty-dir case (issue #43 item 1): definitive "0 runs in <abs
        # dir>" plus the dispatch affordance to create the first one.
        print(f"0 runs in {abs_dir_display}")
        print("next:")
        print(f'  - orc dispatch "<intent text>" --config <path-to-dispatch-config.json> --journal {abs_dir}')
        return 0

    # issue #55 H1: a run_id's journal may live at either layout's path
    # (`layout.journal_path` resolves per run_id, new or legacy) -- unlike
    # the old flat-only assumption, `run_id` can no longer be recovered
    # from `path.stem` (a new-layout path's stem is always "journal"), so
    # entries carry the run_id alongside its resolved path explicitly.
    # `window_before` consumes oldest-first and the display reverses its
    # window, so reverse the one shared newest-first order at this boundary.
    run_entries = list(reversed(ordered_run_entries(directory)))
    journal = JSONLJournal(directory)
    projections: dict[str, Any] = {}
    if state == "active":
        filtered_entries = []
        for run_id, path in run_entries:
            try:
                projection = journal.load_projection(delivery_run_id=run_id)
            except CoreError:
                # Preserve per-run degradation: unknown state must remain
                # visible rather than silently hiding an unreadable run.
                filtered_entries.append((run_id, path))
                continue
            projections[run_id] = projection
            _rollup, active = _index_state_rollup(projection)
            if active:
                filtered_entries.append((run_id, path))
        run_entries = filtered_entries
    corpus_total = len(run_entries)
    window_entries, total, truncated = window_before(
        run_entries,
        limit=limit,
        before=before,
        cursor_of=lambda entry: entry[0],
        cursor_name="before",
    )
    # Most-recently-active first for the at-a-glance scan (paginate keeps
    # append/chronological order, i.e. oldest-of-the-window first).
    window_entries = list(reversed(window_entries))

    noun = "run" if corpus_total == 1 else "runs"
    print(f"{corpus_total} {noun} in {abs_dir_display}:")
    for run_id, _path in window_entries:
        try:
            projection = projections.get(run_id) or journal.load_projection(delivery_run_id=run_id)
        except CoreError as exc:
            # A many-runs-at-a-glance scan must not go dark over one run's
            # replay failure. As of issue #52's fix, `load_projection`
            # folds under the run's own recorded `max_attempts`
            # (`FX-CREATE-WORK`'s effect data, `CONTRACT-DURABILITY`), so
            # this should no longer trigger for that specific defect --
            # this remains defense-in-depth for any other future replay
            # defect. Content-first (axi #8) means partial, honest
            # information beats a hard crash over one bad entry -- `orc
            # status <run_id>` surfaces the same canonical error for
            # whoever needs it.
            print(f"{run_id}: (unreadable: {exc.error.get('error', 'ERR-UNKNOWN')} -- see orc status {run_id})")
            continue
        print(_index_run_line(run_id, projection))
    if truncated:
        print(size_hint(len(window_entries), total, noun="runs", limit_flag="orc --limit 0"))
        oldest_run_id = window_entries[-1][0]
        print(f"next (older) page: orc --limit {limit} --before {oldest_run_id}")
    print(f"orc status <run-id> for next-step guidance on one run; orc report --index for the secondary full HTML index over {abs_dir}.")
    return 0


# issue #43 item 2 ("help quality"): the top-level epilog is the one place
# the exit-code contract, the canonical-error-JSON promise, the
# idempotent-re-dispatch/crash-recovery guarantee, and the
# no-interactive-prompts guarantee are stated for `--help` -- the full
# normative version of each lives in docs/playbooks/cli-usage.md
# (`PLAYBOOK-CLI-USAGE`)/docs/playbooks/agent-cli-usage.md
# (`PLAYBOOK-AGENT-CLI`); this is deliberately the short, self-sufficient
# summary an agent or operator gets without leaving the terminal.
_TOP_LEVEL_EPILOG = """\
exit codes:
  0   all Work ACCEPTED
  1   some Work BLOCKED (or another non-accepted terminal state)
  2   usage/config error (canonical error JSON on stderr)
  3   run non-terminal, pending settlement observation or operator-recorded
      input -- safe to re-check; re-dispatch itself observes and journals
      adapter-observed settlements (e.g. acp) once the provider's turn ends

- errors are always canonical JSON on stderr, never a Python traceback:
  {"error": "ERR-*", "message": "...", "details": {...}}.
- mutations are idempotent: re-running the exact same `orc dispatch`
  command is always safe, and is the crash-recovery move (replaying after a
  crash reproduces identical facts, never duplicates one).
- orc never prompts interactively -- every input comes from flags/config,
  so it is safe to run unattended.

canonical references: PLAYBOOK-CLI-USAGE (commands, config, exit codes),
                      PLAYBOOK-AGENT-CLI (agent settlement/verdict protocol)
"""


def _adapter_values(values: frozenset[str], *, default: Optional[str] = None) -> str:
    ordered = ([default] if default is not None else []) + sorted(values - ({default} if default else set()))
    return "|".join(ordered)


_DISPATCH_CONFIG_EPILOG = f"""\
config blocks:
  execution  selects the execution seat ({_adapter_values(_EXECUTION_ADAPTERS, default='scripted')})
  candidate  selects candidate identification ({_adapter_values(_CANDIDATE_ADAPTERS, default='scripted')})
  assurance  selects the assurance seat ({_adapter_values(_ASSURANCE_ADAPTERS, default='scripted')})
  mirror     selects the optional state projection ({_adapter_values(_MIRROR_ADAPTERS)})
  briefs     supplies per-work prompts and mirror descriptions
  plan       declares the work graph and dependencies
  attempts   records per-work scripted outcomes and verdicts
  orc config-schema for the full reference
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orc",
        description="Orc Werk orchestration CLI.",
        epilog=_TOP_LEVEL_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    version_parser = subparsers.add_parser(
        "version",
        help="print package and source-checkout identity",
        description="Print the installed package version, imported source path, and git identity when available.",
    )
    version_parser.set_defaults(func=cmd_version)

    config_schema_parser = subparsers.add_parser(
        "config-schema",
        help="print the canonical dispatch config reference",
        description="Print the canonical dispatch config reference.",
    )
    config_schema_parser.set_defaults(func=cmd_config_schema)

    validate_parser = subparsers.add_parser(
        "validate",
        help="validate and preview a dispatch config without journaling",
        description="Compose the repo profile and a portable JSON dispatch config with dispatch's "
        "precedence, apply the same schema checks, then preview the plan, adapters, and attempt "
        "entries. Read-only: creates no journal, ports, or orchestrator.",
        epilog="example:\n  orc validate ./.orc/my-run/config.json\n\n"
        "defaults: --journal $ORC_JOURNAL_DIR or ./.orc; profile composition enabled",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    validate_parser.add_argument("config", help="path to a portable JSON dispatch config overlay")
    validate_parser.add_argument(
        "--journal", help="journal directory used to locate profile.json (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    validate_parser.add_argument(
        "--no-profile", action="store_true", help="validate the config file alone, without the repo profile"
    )
    validate_parser.set_defaults(func=cmd_validate)

    dispatch_parser = subparsers.add_parser(
        "dispatch",
        help="dispatch an intent and run to a terminal or pending state",
        description="Dispatch an intent and run the delivery state machine to a resting point "
        "(terminal, or pending awaiting settlement observation or operator-recorded input).",
        epilog="examples:\n"
        '  orc dispatch "ship the widget" --config cfg.json\n'
        '  orc dispatch "ship the widget" --config cfg.json --journal ./.orc --max-attempts 3\n'
        "  orc dispatch --run-id demo-run --journal ./.orc  # resume an existing run\n"
        '  orc dispatch "reply with the word ping" --config acp-cfg.json  # real Pi execution:\n'
        '    # acp-cfg.json: {"execution": {"adapter": "acp", "cwd": "/abs/worktree"},\n'
        '    #                "candidate": {"adapter": "git", "repo_path": "/abs/worktree"}}\n'
        "    # exits 3 (pending) while Pi works; re-run the identical command to poll --\n"
        "    # the re-dispatch itself observes and journals Pi's settlement once the turn\n"
        "    # ends (no hand-recorded outcome needed; issue #210); then record the\n"
        "    # assurance verdict in the config's attempts and re-run again\n\n"
        "  orc dispatch --run-id demo-run --journal ./.orc \\\n"
        '    --abandon-work work-1 --abandon-reason "adapter session orphaned"  # TASK-M3B-001:\n'
        "    # operator-only. Legal only when work-1 rests at an unresolved candidate-\n"
        "    # observation conflict, or at ASSURING awaiting an assurance you know (out-of-\n"
        "    # band) will never settle; --abandon-by defaults to $USER\n\n"
        + _DISPATCH_CONFIG_EPILOG
        + "\ndefaults: --journal $ORC_JOURNAL_DIR or ./.orc, --max-attempts 3 (policy default), --run-id derived "
        "deterministically from the intent text when omitted; config execution.adapter="
        "scripted, candidate.adapter=scripted",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    dispatch_parser.add_argument(
        "intent",
        nargs="?",
        help="intent text to submit (optional only with --run-id naming an existing run)",
    )
    dispatch_parser.add_argument("--config", help="path to a portable JSON dispatch config", default=None)
    dispatch_parser.add_argument("--journal", help="journal directory (default $ORC_JOURNAL_DIR or ./.orc)", default=None)
    dispatch_parser.add_argument("--max-attempts", type=int, default=None, help="override policy max_attempts")
    dispatch_parser.add_argument("--run-id", default=None, help="explicit delivery_run_id")
    dispatch_parser.add_argument(
        "--abandon-work",
        default=None,
        metavar="WORK_ID",
        help="operator-only (TASK-M3B-001): record DEC-ABANDON-ATTEMPT for this work before "
        "continuing dispatch -- requires --abandon-reason",
    )
    dispatch_parser.add_argument(
        "--abandon-reason", default=None, metavar="TEXT", help="required with --abandon-work: why"
    )
    dispatch_parser.add_argument(
        "--abandon-by",
        default=None,
        metavar="WHO",
        help="operator identity for --abandon-work (default: $USER)",
    )
    dispatch_parser.set_defaults(func=cmd_dispatch)

    record_parser = subparsers.add_parser(
        "record",
        help="record the current requested assurance verdict without dispatching",
        description="Atomically merge an assurance verdict into a run's persisted config; never dispatches.",
        epilog="example:\n  orc record my-run --work work-1 --verdict accepted --evidence-ref audit.log",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    record_parser.add_argument("target", help="run id")
    record_parser.add_argument("--work", required=True, metavar="WORK_ID", help="work awaiting assurance")
    record_parser.add_argument("--verdict", required=True, choices=("accepted", "rejected"))
    record_parser.add_argument("--evidence-ref", action="append", default=[], metavar="REF")
    record_parser.add_argument("--finding", action="append", default=[], metavar="TEXT")
    record_parser.add_argument("--derived-identity", default=None, metavar="JSON")
    record_parser.add_argument("--model", default=None, metavar="M")
    record_parser.add_argument("--session-ref", default=None, metavar="S")
    record_parser.add_argument("--seat-ref", default=None, metavar="S")
    record_parser.add_argument(
        "--journal", help="journal directory (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    record_parser.set_defaults(func=cmd_record)

    cancel_parser = subparsers.add_parser(
        "cancel",
        help="operator-only terminal closure of non-terminal Work",
        description="Record DEC-CANCEL and FACT-WORK-CANCELLED as a journal-only terminal closure.",
        epilog='example:\n  orc cancel my-run-id --work work-1 --reason "operator closed healed specimen"',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cancel_parser.add_argument("target", help="journal path (dir or <run>.jsonl) or bare run id")
    cancel_parser.add_argument("--work", required=True, metavar="WORK_ID", help="work id to cancel")
    cancel_parser.add_argument("--reason", default=None, metavar="TEXT", help="required free-form reason")
    cancel_parser.add_argument(
        "--journal", help="journal directory (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    cancel_parser.set_defaults(func=cmd_cancel)

    status_parser = subparsers.add_parser(
        "status",
        help="print per-work state from a journal",
        description="Print per-work state (state, attempts, candidate fingerprint, pending/blocked "
        "detail, next-step affordances) for one run.",
        epilog="examples:\n"
        "  orc status my-run-id\n"
        "  orc status ./.orc/my-run-id.jsonl\n\n"
        "defaults: a bare run id resolves against --journal, $ORC_JOURNAL_DIR, or ./.orc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    status_parser.add_argument("target", help="journal path (dir or <run>.jsonl) or bare run id")
    status_parser.add_argument(
        "--journal", help="journal directory (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    status_parser.set_defaults(func=cmd_status)

    refs_parser = subparsers.add_parser(
        "refs",
        help="list every resolvable reference in a run, or resolve one/all inline",
        description="Pure journal projection: list every resolvable reference recorded for one "
        "run (execution-session/v1 session/transcript refs, assurance evidence_refs, candidate "
        "identity, the Beads mirror when configured), each indexed and shown with a resolve "
        "command. --resolve/--resolve-all (TASK-M3C-002) execute that SAME command -- never a "
        "second command vocabulary -- vetted read-only at construction (cat; git show/--stat; "
        "acpx sessions history/show; bd list/show; no-mistakes axi status/logs -- nothing else); "
        "an unvetted or malformed command REFUSES to execute and prints the manual command "
        "instead. A resolution failure (refused, missing binary, nonzero exit, timeout after 30s) "
        "never fails this command -- the ref itself remains valid; exit stays 0. Plain listing is "
        "unchanged: still read-only, still never shells out "
        "(canonical: CONTRACT-DURABILITY).",
        epilog="examples:\n"
        "  orc refs my-run-id\n"
        "  orc refs ./.orc/my-run-id.jsonl\n"
        "  orc refs my-run-id --resolve 2            # by the [N] index the plain listing prints\n"
        "  orc refs my-run-id --resolve transcript    # by kind, when exactly one row matches\n"
        "  orc refs my-run-id --resolve-all           # every row with a resolve command, headered\n\n"
        "defaults: a bare run id resolves against --journal, $ORC_JOURNAL_DIR, or ./.orc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    refs_parser.add_argument("target", help="journal path (dir or <run>.jsonl) or bare run id")
    refs_parser.add_argument(
        "--journal", help="journal directory (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    refs_resolve_group = refs_parser.add_mutually_exclusive_group()
    refs_resolve_group.add_argument(
        "--resolve",
        metavar="SELECTOR",
        default=None,
        help="resolve one ref inline: the [N] index from the plain listing, or '<kind>[:<substring>]'",
    )
    refs_resolve_group.add_argument(
        "--resolve-all",
        action="store_true",
        help="resolve every ref that carries a resolve command, each under its own header",
    )
    refs_parser.set_defaults(func=cmd_refs)

    verdict_parser = subparsers.add_parser(
        "verdict",
        help="print each work's latest assurance verdict and findings",
        description="Read-only journal projection of each Work's latest assurance verdict, "
        "candidate fingerprint, evidence references, and extension findings.",
        epilog="examples:\n  orc verdict my-run-id\n  orc verdict my-run-id --journal ./.orc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    verdict_parser.add_argument("target", help="journal path (dir or <run>.jsonl) or bare run id")
    verdict_parser.add_argument(
        "--journal", help="journal directory (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    verdict_parser.set_defaults(func=cmd_verdict)

    history_parser = subparsers.add_parser(
        "history",
        help="print ordered journal records",
        description="Print the ordered fact/decision/effect record log for one run -- root-cause "
        "detail (dispatch-gate errors, decision basis) lives here.",
        epilog="examples:\n"
        "  orc history my-run-id\n"
        "  orc history my-run-id --limit 0\n"
        "  orc history my-run-id --since-seq 12\n"
        "  orc history my-run-id --limit 30 --before-seq 16\n\n"
        f"defaults: --limit {DEFAULT_LIMIT} (last {DEFAULT_LIMIT} records; 0 shows all); "
        "a bare run id resolves against --journal, $ORC_JOURNAL_DIR, or ./.orc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    history_parser.add_argument("target", help="journal path (dir or <run>.jsonl) or bare run id")
    history_parser.add_argument(
        "--journal", help="journal directory (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    history_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"show at most N most-recent records, 0 for all (default {DEFAULT_LIMIT})",
    )
    history_parser.add_argument(
        "--since-seq", type=int, default=None, help="only show records with seq greater than SEQ"
    )
    history_parser.add_argument(
        "--before-seq", default=None, help="show the page of records older than sequence cursor SEQ"
    )
    history_parser.set_defaults(func=cmd_history)

    show_parser = subparsers.add_parser(
        "show",
        help="the run narrative: per work, per attempt -- asked/executed/produced/judged, next",
        description="Terminal narrative view of one run (TASK-M3C-001): for each work (or the one "
        "named), per attempt -- ASKED (derived prompt provenance, briefs vs intent fallback, "
        "issue #111), EXECUTED (provider/session/duration), PRODUCED (candidate identity), "
        "JUDGED (verdict, findings summary, or inheritance basis per STATE-DELIVERY item 8), and "
        "NEXT/DEEPER (resolve commands, reusing orc refs's builders). Pure composition of the "
        "journal, this run's persisted dispatch config, and the times sidecar -- no new "
        "recording, no full-payload dumps.",
        epilog="examples:\n"
        "  orc show my-run-id\n"
        "  orc show my-run-id work-1\n"
        "  orc show my-run-id --journal ./.orc\n\n"
        "defaults: a bare run id resolves against --journal, $ORC_JOURNAL_DIR, or ./.orc; "
        "omitting the work positional shows every work",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    show_parser.add_argument("run", help="journal path (dir or <run>.jsonl) or bare run id")
    show_parser.add_argument("work", nargs="?", default=None, help="show only this work id (default: every work)")
    show_parser.add_argument(
        "--journal", help="journal directory (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    show_parser.set_defaults(func=cmd_show)

    report_parser = subparsers.add_parser(
        "report",
        help="render a self-contained HTML run report, or a local run index",
        description="Render a self-contained HTML run report, or a local index page over a "
        "journal directory's runs.",
        epilog="examples:\n"
        "  orc report my-run-id\n"
        "  orc report --index\n"
        "  orc report --all --match 'm1.*'\n\n"
        "defaults: --journal $ORC_JOURNAL_DIR or ./.orc, --match '*' (used with --all)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    report_parser.add_argument(
        "run", nargs="?", default=None, help="journal path (dir or <run>.jsonl) or bare run id"
    )
    report_parser.add_argument(
        "--index", action="store_true", help="render an index page over the journal directory's runs instead"
    )
    report_parser.add_argument(
        "--all", action="store_true",
        help="render every run whose run_id matches --match (default '*') to its own file plus a scoped index",
    )
    report_parser.add_argument(
        "--match", default=None,
        help="fnmatch glob over run_id, used with --all (default '*', e.g. 'm1.*' selects a namespace)",
    )
    report_parser.add_argument(
        "--journal", help="journal directory (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    report_parser.add_argument(
        "--out", help="output HTML path (default: announced <journal-dir>/<run_id>/report.html "
        "for a new-layout run, <journal-dir>/<run_id>.report.html for a legacy-layout run, or "
        ".../index.html for --index)",
        default=None,
    )
    report_parser.add_argument(
        "--out-dir", default=None,
        help="output directory for --all (default: the journal directory)",
    )
    report_parser.set_defaults(func=cmd_report)

    onboard_parser = subparsers.add_parser(
        "onboard",
        help="mechanically scaffold an adopting repo: gitignore, skill install, agents-block, install verification",
        description="Scaffold an adopting repository (TASK-M3D-001): ensure a .orc/ .gitignore entry, "
        "install the orc-ledger skill (content sourced from THIS installed package, one canonical "
        "origin), write/print a copy-pasteable '## Delivery ledger (orc)' agents-onboarding block, "
        "and honestly report install verification (orc on PATH vs module form, journal dir "
        "resolution, optional bd presence). Idempotent re-run; never silently overwrites a file it "
        "did not create -- an operator-modified target is skip-with-note unless --force.",
        epilog="examples:\n"
        "  orc onboard --path /path/to/adopting-repo\n"
        "  orc onboard --path . --force              # re-run, overwriting operator-modified targets\n"
        "  orc onboard --print-agents-block           # prints only, writes nothing\n\n"
        "defaults: --path . ; --agents-file AGENTS.md ; --journal $ORC_JOURNAL_DIR or ./.orc "
        "(verification report only -- onboard never creates a journal)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    onboard_parser.add_argument("--path", default=".", help="target repository directory (default: .)")
    onboard_parser.add_argument(
        "--print-agents-block",
        action="store_true",
        help="print the agents-onboarding block to stdout and exit; performs no other step, writes nothing",
    )
    onboard_parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite/replace a target that already exists with different content (default: skip-with-note)",
    )
    onboard_parser.add_argument(
        "--agents-file",
        default=DEFAULT_AGENTS_FILE,
        metavar="NAME",
        help=f"agent-instructions file (relative to --path) to write the Delivery ledger block into (default: {DEFAULT_AGENTS_FILE})",
    )
    onboard_parser.add_argument(
        "--journal",
        default=None,
        help="journal directory to report on in the verification step (default: $ORC_JOURNAL_DIR or ./.orc, anchored at --path)",
    )
    onboard_parser.add_argument(
        "--agents-block",
        choices=("slim", "full"),
        default="slim",
        help="agents block detail: slim points to the installed skill (default); full inlines it for harnesses without skill support",
    )
    onboard_parser.add_argument(
        "--ledger",
        choices=("local", "committed"),
        default="local",
        help="ledger placement: local adds .orc/ to .gitignore (default); committed leaves gitignore unchanged",
    )
    onboard_parser.set_defaults(func=cmd_onboard)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args or raw_args[:1] in (["--limit"], ["--before"], ["--state"]):
        # The content-first index is intentionally a promoted fast path,
        # not an argparse subcommand. Give that surface its own tiny parser
        # so `orc --limit N` retains the bare invocation while ordinary
        # top-level flags/subcommands (including `--help`) remain unchanged.
        index_parser = argparse.ArgumentParser(prog="orc", add_help=False)
        index_parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
        index_parser.add_argument("--before", default=None)
        index_parser.add_argument("--state", default=None)
        index_args = index_parser.parse_args(raw_args)
        call = lambda: cmd_index(  # noqa: E731
            limit=index_args.limit, before=index_args.before, state=index_args.state
        )
    else:
        parser = build_parser()
        args = parser.parse_args(raw_args)
        call = lambda: args.func(args)  # noqa: E731 -- shares the except block below with cmd_index
    try:
        return call()
    except CoreError as exc:
        _print_error(exc.to_canonical())
        return 2
    except FileNotFoundError as exc:
        _print_error(
            {
                "error": "ERR-NOT-FOUND",
                "message": str(exc),
                "details": {},
                # issue #94: genuinely generic here (this branch has no run
                # id/journal-dir context of its own -- e.g. a --config path
                # that does not exist) -- still worth two honest, non-
                # fabricated navigational pointers rather than nothing.
                "next": [
                    "double check the path was typed correctly",
                    "orc (bare) lists every run id under the default journal dir",
                ],
            }
        )
        return 2
    except Exception as exc:  # noqa: BLE001 -- last-resort per module docstring contract
        # BUG-1 audit: this module's docstring promises errors print the
        # canonical error value as JSON to stderr, "never a Python
        # traceback" -- unconditionally, not just for the two exception
        # types above. `CoreError`/`FileNotFoundError` are the *known*
        # ways a command can fail; this catch-all is the CLI's defense in
        # depth against an *unknown* one (a bug in this CLI, an adapter, or
        # core reaching a state its own contract didn't anticipate) still
        # honoring that promise instead of leaking a traceback. It
        # deliberately reports only `str(exc)` and the exception's type
        # name -- never a formatted traceback/frame data -- staying within
        # the portable canonical-error shape (CLAUDE.md #9). `ERR-PERMANENT`
        # ("operation cannot succeed without changing intent/state/
        # provider", CONTRACT-ERRORS) is the closest canonical fit for an
        # unclassified failure: retrying the exact same command is not
        # expected to help.
        _print_error(
            {
                "error": "ERR-PERMANENT",
                "message": f"unexpected internal error ({type(exc).__name__}): {exc}",
                "details": {},
                # issue #94: this catch-all has no reliable run/command
                # context of its own (it fires for a bug in this CLI, an
                # adapter, or a core state its own contract did not
                # anticipate) -- the honest, non-fabricated guidance is to
                # look at what WAS journaled so far, not a guessed fix.
                "next": [
                    "orc history <run-id> for what was journaled before this failure, if a run id is involved",
                    "this may be a defect in orc itself -- consider filing an issue",
                ],
            }
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["build_parser", "cmd_index", "main"]
