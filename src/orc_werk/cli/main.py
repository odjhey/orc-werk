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

from orc_werk.adapters.jsonl.crew_report import CrewReportLog
from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.app.orchestrator import Orchestrator, is_pending
from orc_werk.cli.affordances import render_next_block
from orc_werk.cli.config import build_dispatch_ports, build_run_config, build_scripted_adapters, load_config
from orc_werk.cli.journal_reading import (
    BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED,
    DEFAULT_JOURNAL_DIR,
    _available_run_ids,
    _awaiting_label,
    _intent_text,
    _require_journal_file,
    _resolve_journal,
    _root_cause_for_work,
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


def cmd_dispatch(args: argparse.Namespace) -> int:
    config = load_config(args.config) if args.config else {}
    run_id = args.run_id or config.get("run_id") or _derive_run_id(args.intent)
    journal_dir = Path(args.journal) if args.journal else Path(DEFAULT_JOURNAL_DIR)

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
            config, delivery_run_id=run_id, intent_text=args.intent, journal=journal
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
    orchestrator.bootstrap(intent_id=run_id, text=args.intent, plan=plan)
    projection = orchestrator.run()
    history = journal.history(delivery_run_id=run_id)

    print(f"run: {run_id}")
    # #40 comment: print the RESOLVED ABSOLUTE path, not a relative one --
    # a printed relative path (e.g. `.orc/x.jsonl`) is not reliably
    # clickable in a terminal when the reader's cwd differs from the
    # process's; `.resolve()` makes it absolute and normalizes it the same
    # way `orc report`'s printed paths now do (see orc_werk.cli.report).
    print(f"journal: {(journal_dir / (run_id + '.jsonl')).resolve()}")
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
        intent_text=args.intent,
    ):
        print(line)
    return exit_code


def cmd_status(args: argparse.Namespace) -> int:
    directory, run_id = _resolve_journal(args.target)
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
    directory, run_id = _resolve_journal(args.target)
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
    journal_dir = Path(args.journal) if args.journal else Path(DEFAULT_JOURNAL_DIR)
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
    journal_dir = Path(args.journal) if args.journal else Path(DEFAULT_JOURNAL_DIR)
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
    directory = journal_dir or Path(DEFAULT_JOURNAL_DIR)
    abs_dir = directory.resolve()
    run_ids = _available_run_ids(directory)
    if not run_ids:
        # Empty-dir case (issue #43 item 1): definitive "0 runs in <abs
        # dir>" plus the dispatch affordance to create the first one.
        print(f"0 runs in {abs_dir}")
        print("next:")
        print(f'  - orc dispatch "<intent text>" --config <path-to-dispatch-config.json> --journal {abs_dir}')
        return 0

    run_paths = sorted(
        (directory / f"{run_id}.jsonl" for run_id in run_ids),
        key=lambda p: (p.stat().st_mtime, p.stem),
    )
    window_paths, total, truncated = paginate(run_paths, limit=DEFAULT_LIMIT)
    # Most-recently-active first for the at-a-glance scan (paginate keeps
    # append/chronological order, i.e. oldest-of-the-window first).
    window_paths = list(reversed(window_paths))

    journal = JSONLJournal(directory)
    noun = "run" if total == 1 else "runs"
    print(f"{total} {noun} in {abs_dir}:")
    for path in window_paths:
        run_id = path.stem
        try:
            projection = journal.load_projection(delivery_run_id=run_id)
        except CoreError as exc:
            # A many-runs-at-a-glance scan must not go dark over one run's
            # replay failure (known-issues ledger,
            # docs/playbooks/cli-usage.md: `load_projection` does not carry
            # a per-run `max_attempts`, so a run dispatched with a
            # non-default budget can fail to re-derive its own projection).
            # Content-first (axi #8) means partial, honest information beats
            # a hard crash over one bad entry -- `orc status <run_id>`
            # surfaces the same canonical error for whoever needs it.
            print(f"{run_id}: (unreadable: {exc.error.get('error', 'ERR-UNKNOWN')} -- see orc status {run_id})")
            continue
        print(_index_run_line(run_id, projection))
    if truncated:
        # Bare `orc` has no flag surface of its own to carry `--limit`
        # (issue #43 item 1 has no args at all beyond the bare invocation),
        # so its size hint names the real escape hatch instead of a
        # nonexistent flag: `orc report --index` (unpaginated).
        print(size_hint(len(window_paths), total, noun="runs", limit_flag="orc report --index"))
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orc",
        description="Orc Werk orchestration CLI.",
        epilog=_TOP_LEVEL_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    dispatch_parser = subparsers.add_parser(
        "dispatch",
        help="dispatch an intent and run to a terminal or pending state",
        description="Dispatch an intent and run the delivery state machine to a resting point "
        "(terminal, or pending awaiting operator-recorded input).",
        epilog="examples:\n"
        '  orc dispatch "ship the widget" --config cfg.json\n'
        '  orc dispatch "ship the widget" --config cfg.json --journal ./.orc --max-attempts 3\n'
        '  orc dispatch "reply with the word ping" --config acp-cfg.json  # real Pi execution:\n'
        '    # acp-cfg.json: {"execution": {"adapter": "acp", "cwd": "/abs/worktree"},\n'
        '    #                "candidate": {"adapter": "git", "repo_path": "/abs/worktree"}}\n'
        "    # exits 3 (pending) while Pi works; re-run the identical command to poll; once\n"
        "    # settled, record the assurance verdict in the config's attempts and re-run again\n\n"
        "defaults: --journal ./.orc, --max-attempts 3 (policy default), --run-id derived "
        "deterministically from the intent text when omitted; config execution.adapter="
        "scripted, candidate.adapter=scripted (see docs/playbooks/cli-usage.md for the real "
        "acp/git config schema)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    dispatch_parser.add_argument("intent", help="the intent text to submit")
    dispatch_parser.add_argument("--config", help="path to a portable JSON dispatch config", default=None)
    dispatch_parser.add_argument("--journal", help="journal directory (default ./.orc)", default=None)
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
        "defaults: a bare run id resolves against ./.orc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    status_parser.add_argument("target", help="journal path (dir or <run>.jsonl) or bare run id")
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
        "a bare run id resolves against ./.orc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    history_parser.add_argument("target", help="journal path (dir or <run>.jsonl) or bare run id")
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
        "defaults: --journal ./.orc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    crew_report_append_parser.add_argument("run_id", help="delivery_run_id")
    crew_report_append_parser.add_argument("--execution-id", required=True, help="execution_id this report describes")
    crew_report_append_parser.add_argument(
        "--payload", required=True, help="crew-report/v1 payload as a portable JSON object"
    )
    crew_report_append_parser.add_argument(
        "--journal", help="journal directory the report log sits beside (default ./.orc)", default=None
    )
    crew_report_append_parser.set_defaults(func=cmd_crew_report_append)

    crew_report_list_parser = crew_report_subparsers.add_parser(
        "list",
        help="list crew-report/v1 records for a run, in append order",
        description="List crew-report/v1 narrative records for a run, in append order.",
        epilog="examples:\n"
        "  orc crew-report list my-run-id\n"
        "  orc crew-report list my-run-id --execution-id exec-1 --limit 0\n\n"
        f"defaults: --journal ./.orc, --limit {DEFAULT_LIMIT} (last {DEFAULT_LIMIT} reports; 0 shows all)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    crew_report_list_parser.add_argument("run_id", help="delivery_run_id")
    crew_report_list_parser.add_argument(
        "--execution-id", default=None, help="restrict to reports for one execution_id"
    )
    crew_report_list_parser.add_argument(
        "--journal", help="journal directory the report log sits beside (default ./.orc)", default=None
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
        "defaults: --journal ./.orc, --match '*' (used with --all)",
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
        "--journal", help="journal directory (default ./.orc)", default=None
    )
    report_parser.add_argument(
        "--out", help="output HTML path (default: announced <journal-dir>/<run_id>.report.html or .../index.html)",
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
