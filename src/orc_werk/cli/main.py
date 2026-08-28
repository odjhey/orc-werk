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
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.jsonl import layout
from orc_werk.adapters.jsonl.crew_report import CrewReportLog
from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.app.orchestrator import Orchestrator, is_pending
from orc_werk.cli.affordances import render_next_block
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
    load_config,
)
from orc_werk.cli.hyperlink import hyperlink_path
from orc_werk.cli.journal_reading import (
    BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED,
    _available_run_ids,
    _awaiting_label,
    _intent_text,
    _require_journal_file,
    _resolve_journal,
    _root_cause_for_work,
    resolve_journal_dir,
)
from orc_werk.cli.pagination import DEFAULT_LIMIT, paginate, size_hint
from orc_werk.cli.report import cmd_report
from orc_werk.core.errors import CoreError, validation_error
from orc_werk.core.state import STATE_ACCEPTED, STATE_BLOCKED, WorkProjection
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


def cmd_config_schema(_args: argparse.Namespace) -> int:
    """Print the single-source dispatch config reference verbatim."""
    sys.stdout.write(config_module.__doc__ or "")
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    journal_dir = resolve_journal_dir(args.journal)
    existing_run_ids = set(layout.discover_run_ids(journal_dir))

    if args.intent is None:
        if not args.run_id or args.run_id not in existing_run_ids:
            raise validation_error(
                "intent is required when dispatching a new run; to resume an existing run use "
                "orc dispatch --run-id <id>",
                run_id=args.run_id,
            )
        existing_history = JSONLJournal(journal_dir).history(delivery_run_id=args.run_id)
        intent_text = _intent_text(existing_history)
        if intent_text is None:
            raise validation_error(
                f"run {args.run_id!r} has no journaled intent; supply the positional intent",
                run_id=args.run_id,
            )
    else:
        intent_text = args.intent

    if args.config:
        config = load_config(args.config)
        run_id = args.run_id or config.get("run_id") or _derive_run_id(intent_text)
    else:
        # issue #55 H2 config persistence: no --config given -- before
        # falling back to the bare-scripted default ({}), check whether
        # this run already has an effective config durably persisted in
        # its own run dir from an earlier dispatch (run-id-only
        # re-dispatch; docs/playbooks/agent-cli-usage.md's fresh-session
        # protocol). `run_id` must be resolvable without a config to
        # consult in this branch -- exactly the same derivation `--config`
        # would otherwise fall back to (`--run-id` flag, else the
        # deterministic intent-text hash).
        run_id = args.run_id or _derive_run_id(intent_text)
        persisted_config_path = layout.config_path(journal_dir, run_id)
        if persisted_config_path.exists():
            config = load_config(str(persisted_config_path))
            run_id = args.run_id or config.get("run_id") or run_id
        else:
            config = {}

    if run_id not in existing_run_ids and intent_text in existing_run_ids:
        raise validation_error(
            f"intent {intent_text!r} is also existing run id {intent_text!r}: to resume, run "
            f"orc dispatch --run-id {intent_text}; if this is genuinely new work, reword the intent",
            intent=intent_text,
            existing_run_id=intent_text,
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
    if execution_adapter == "scripted" and candidate_adapter == "scripted":
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
    projection = orchestrator.run()
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
            "pending: run is non-terminal, awaiting operator-recorded input for: "
            + ", ".join(sorted(pending_ids) if pending_ids else sorted(projection.works))
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


def cmd_status(args: argparse.Namespace) -> int:
    directory, run_id = _resolve_journal(args.target, args.journal)
    _require_journal_file(directory, run_id, target=args.target)
    journal = JSONLJournal(directory)
    history = journal.history(delivery_run_id=run_id)
    projection = journal.load_projection(delivery_run_id=run_id)

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
            "pending: run is non-terminal, awaiting operator-recorded input for: "
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


def cmd_history(args: argparse.Namespace) -> int:
    directory, run_id = _resolve_journal(args.target, args.journal)
    _require_journal_file(directory, run_id, target=args.target)
    journal = JSONLJournal(directory)
    records = list(journal.history(delivery_run_id=run_id))
    # issue #43 pagination addendum: --since-seq filters first (an explicit
    # "what's new since I last looked" query), then the default/--limit
    # window applies to the (possibly filtered) result -- the size hint's
    # "of N" always names the exact count of what --limit 0 would show.
    if args.since_seq is not None:
        records = [r for r in records if r["seq"] > args.since_seq]
    window, total, truncated = paginate(records, limit=args.limit)
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
    return 0


def cmd_crew_report_append(args: argparse.Namespace) -> int:
    """`TASK-M1-007` CLI surface: append one `crew-report/v1` record
    (`EXT-CREW-REPORT-V1-SCHEMA`) to the run's adapter-owned log
    (`orc_werk.adapters.jsonl.crew_report.CrewReportLog`), distinct from
    -- and never merged into -- the run's `JournalPort` journal file. This
    is narrative self-report, never a canonical settlement/candidate/
    verdict recording (`docs/playbooks/agent-cli-usage.md` section 7)."""
    journal_dir = resolve_journal_dir(args.journal)
    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        raise validation_error(f"--payload is not valid JSON: {exc}", payload=args.payload) from exc
    log = CrewReportLog(journal_dir)
    record = log.append(delivery_run_id=args.run_id, execution_id=args.execution_id, report=payload)
    print(_compact(record))
    return 0


def cmd_crew_report_list(args: argparse.Namespace) -> int:
    """`TASK-M1-007` CLI surface: list `crew-report/v1` records for a run
    in append order (the log's own ordering key, distinct from
    `PORT-JOURNAL-ENVELOPE`'s `seq`), optionally filtered to one
    `execution_id`."""
    journal_dir = resolve_journal_dir(args.journal)
    log = CrewReportLog(journal_dir)
    records = list(log.list_reports(delivery_run_id=args.run_id, execution_id=args.execution_id))
    # issue #43 pagination addendum: same last-N-with-a-definitive-hint
    # shape as `orc history`. Indices in the printed `[NNNN]` prefix keep
    # naming each report's real 1-based position in the full (unfiltered
    # by --limit) list, not a 1..len(window) renumbering, so a truncated
    # listing's indices stay meaningful against the untruncated list.
    window, total, truncated = paginate(records, limit=args.limit)
    start_index = total - len(window) + 1
    for idx, record in enumerate(window, start=start_index):
        print(
            f"[{idx:04d}] execution_id={record['execution_id']} report={_compact(record['report'])}"
        )
    if truncated:
        print(size_hint(len(window), total, noun="reports"))
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
    if not projection.works:
        return f"{run_id}: (no work recorded yet)"
    summary = ", ".join(_index_work_summary(wid, projection.works[wid]) for wid in sorted(projection.works))
    return f"{run_id}: {summary}"


def cmd_index(journal_dir: Optional[Path] = None) -> int:
    """`orc` with no arguments (issue #43 item 1, "content first" -- axi
    #8): a live text index of the default journal dir instead of an
    argparse usage error. Strictly read-only: never constructs
    `JSONLJournal` (whose `__init__` `mkdir`s the journal directory) unless
    the directory already exists and already has at least one run journal
    in it, so a bare `orc` in a fresh checkout creates nothing.

    Paginated the same way as `orc history`/`orc crew-report list` (issue
    #43 pagination addendum), most-recently-active runs first (by journal
    file mtime); bare `orc` has no flag surface of its own to carry a
    `--limit`, so its escape hatch to the full set is the already-shipped
    `orc report --index` (an unpaginated HTML index over every run) rather
    than an invented flag.
    """
    directory = journal_dir if journal_dir is not None else resolve_journal_dir(None)
    abs_dir = directory.resolve()
    # issue #55 OSC-8 scope addition: these two "N runs in <abs dir>"/"0
    # runs in <abs dir>" lines are standalone index lines.
    abs_dir_display = hyperlink_path(abs_dir)
    run_ids = _available_run_ids(directory)
    if not run_ids:
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
    run_entries = sorted(
        ((run_id, layout.journal_path(directory, run_id)) for run_id in run_ids),
        key=lambda entry: (entry[1].stat().st_mtime, entry[0]),
    )
    window_entries, total, truncated = paginate(run_entries, limit=DEFAULT_LIMIT)
    # Most-recently-active first for the at-a-glance scan (paginate keeps
    # append/chronological order, i.e. oldest-of-the-window first).
    window_entries = list(reversed(window_entries))

    journal = JSONLJournal(directory)
    noun = "run" if total == 1 else "runs"
    print(f"{total} {noun} in {abs_dir_display}:")
    for run_id, _path in window_entries:
        try:
            projection = journal.load_projection(delivery_run_id=run_id)
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
        # Bare `orc` has no flag surface of its own to carry `--limit`
        # (issue #43 item 1 has no args at all beyond the bare invocation),
        # so its size hint names the real escape hatch instead of a
        # nonexistent flag: `orc report --index` (unpaginated).
        print(size_hint(len(window_entries), total, noun="runs", limit_flag="orc report --index"))
    print(f"orc status <run-id> for next-step guidance on one run; orc report --index for the full unpaginated HTML index over {abs_dir}.")
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
  3   run non-terminal, pending operator-recorded input -- safe to re-check

- errors are always canonical JSON on stderr, never a Python traceback:
  {"error": "ERR-*", "message": "...", "details": {...}}.
- mutations are idempotent: re-running the exact same `orc dispatch`
  command is always safe, and is the crash-recovery move (replaying after a
  crash reproduces identical facts, never duplicates one).
- orc never prompts interactively -- every input comes from flags/config,
  so it is safe to run unattended.

docs: docs/playbooks/cli-usage.md (commands, config, exit codes),
      docs/playbooks/agent-cli-usage.md (agent settlement/verdict protocol)
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

    config_schema_parser = subparsers.add_parser(
        "config-schema",
        help="print the canonical dispatch config reference",
        description="Print the canonical dispatch config reference.",
    )
    config_schema_parser.set_defaults(func=cmd_config_schema)

    dispatch_parser = subparsers.add_parser(
        "dispatch",
        help="dispatch an intent and run to a terminal or pending state",
        description="Dispatch an intent and run the delivery state machine to a resting point "
        "(terminal, or pending awaiting operator-recorded input).",
        epilog="examples:\n"
        '  orc dispatch "ship the widget" --config cfg.json\n'
        '  orc dispatch "ship the widget" --config cfg.json --journal ./.orc --max-attempts 3\n'
        "  orc dispatch --run-id demo-run --journal ./.orc  # resume an existing run\n"
        '  orc dispatch "reply with the word ping" --config acp-cfg.json  # real Pi execution:\n'
        '    # acp-cfg.json: {"execution": {"adapter": "acp", "cwd": "/abs/worktree"},\n'
        '    #                "candidate": {"adapter": "git", "repo_path": "/abs/worktree"}}\n'
        "    # exits 3 (pending) while Pi works; re-run the identical command to poll; once\n"
        "    # settled, record the assurance verdict in the config's attempts and re-run again\n\n"
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
    dispatch_parser.set_defaults(func=cmd_dispatch)

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

    history_parser = subparsers.add_parser(
        "history",
        help="print ordered journal records",
        description="Print the ordered fact/decision/effect record log for one run -- root-cause "
        "detail (dispatch-gate errors, decision basis) lives here.",
        epilog="examples:\n"
        "  orc history my-run-id\n"
        "  orc history my-run-id --limit 0\n"
        "  orc history my-run-id --since-seq 12\n\n"
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
    history_parser.set_defaults(func=cmd_history)

    crew_report_parser = subparsers.add_parser(
        "crew-report",
        help="append/list crew-report/v1 narrative records for a run",
        description="Append or list crew-report/v1 narrative records for a run/execution -- claims "
        "about progress, never a canonical settlement/candidate/verdict.",
    )
    crew_report_subparsers = crew_report_parser.add_subparsers(dest="crew_report_command", required=True)

    crew_report_append_parser = crew_report_subparsers.add_parser(
        "append",
        help="append one crew-report/v1 record for a run/execution",
        description="Append one crew-report/v1 narrative record for a run/execution.",
        epilog="example:\n"
        "  orc crew-report append my-run-id --execution-id exec-1 "
        "--payload '{\"turn\": 1, \"claimed_verdict\": \"waiting\"}'\n\n"
        "defaults: --journal $ORC_JOURNAL_DIR or ./.orc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    crew_report_append_parser.add_argument("run_id", help="delivery_run_id")
    crew_report_append_parser.add_argument("--execution-id", required=True, help="execution_id this report describes")
    crew_report_append_parser.add_argument(
        "--payload", required=True, help="crew-report/v1 payload as a portable JSON object"
    )
    crew_report_append_parser.add_argument(
        "--journal", help="journal directory the report log sits beside (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    crew_report_append_parser.set_defaults(func=cmd_crew_report_append)

    crew_report_list_parser = crew_report_subparsers.add_parser(
        "list",
        help="list crew-report/v1 records for a run, in append order",
        description="List crew-report/v1 narrative records for a run, in append order.",
        epilog="examples:\n"
        "  orc crew-report list my-run-id\n"
        "  orc crew-report list my-run-id --execution-id exec-1 --limit 0\n\n"
        f"defaults: --journal $ORC_JOURNAL_DIR or ./.orc, --limit {DEFAULT_LIMIT} (last {DEFAULT_LIMIT} reports; 0 shows all)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    crew_report_list_parser.add_argument("run_id", help="delivery_run_id")
    crew_report_list_parser.add_argument(
        "--execution-id", default=None, help="restrict to reports for one execution_id"
    )
    crew_report_list_parser.add_argument(
        "--journal", help="journal directory the report log sits beside (default $ORC_JOURNAL_DIR or ./.orc)", default=None
    )
    crew_report_list_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"show at most N most-recent reports, 0 for all (default {DEFAULT_LIMIT})",
    )
    crew_report_list_parser.set_defaults(func=cmd_crew_report_list)

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

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args:
        # issue #43 item 1 ("content first", axi #8): bare `orc` (no
        # subcommand, no flags) prints a live text index of the default
        # journal dir instead of argparse's usage error. `orc --help`
        # remains the unchanged reference (any non-empty argv, including
        # `--help` alone, still goes through the ordinary parser below).
        call = cmd_index
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
        _print_error({"error": "ERR-NOT-FOUND", "message": str(exc), "details": {}})
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
            }
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["build_parser", "cmd_index", "main"]
