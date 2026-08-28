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
from orc_werk.cli.config import build_run_config, build_scripted_adapters, load_config
from orc_werk.cli.journal_reading import (
    BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED,
    DEFAULT_JOURNAL_DIR,
    _awaiting_label,
    _intent_text,
    _require_journal_file,
    _resolve_journal,
    _root_cause_for_work,
)
from orc_werk.cli.report import cmd_report
from orc_werk.core.errors import CoreError, validation_error
from orc_werk.core.state import STATE_ACCEPTED, STATE_BLOCKED, WorkProjection

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
    work_graph = MemoryWorkGraph()
    execution, candidate, assurance = build_scripted_adapters(config, delivery_run_id=run_id)
    run_config = build_run_config(config, max_attempts_override=args.max_attempts)

    journal = JSONLJournal(journal_dir)

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
    return exit_code


def _compact(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def cmd_history(args: argparse.Namespace) -> int:
    directory, run_id = _resolve_journal(args.target)
    _require_journal_file(directory, run_id, target=args.target)
    journal = JSONLJournal(directory)
    for record in journal.history(delivery_run_id=run_id):
        line = f"[{record['seq']:04d}] {record['kind']:8s} {record['id']:28s} {_compact(record['data'])}"
        # FRICTION-1: the envelope's sibling `extensions` field (where e.g.
        # EXT-REVIEW-FINDINGS-V1 assurance findings travel, CONF-EXT-003)
        # is otherwise invisible in `orc history` output even though it was
        # journaled -- render it (compact, same line) when non-empty.
        extensions = record.get("extensions")
        if extensions:
            line += f" extensions={_compact(extensions)}"
        print(line)
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
    records = log.list_reports(delivery_run_id=args.run_id, execution_id=args.execution_id)
    for idx, record in enumerate(records, start=1):
        print(
            f"[{idx:04d}] execution_id={record['execution_id']} report={_compact(record['report'])}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orc", description="Orc Werk orchestration CLI (M0).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dispatch_parser = subparsers.add_parser("dispatch", help="dispatch an intent and run to terminal state")
    dispatch_parser.add_argument("intent", help="the intent text to submit")
    dispatch_parser.add_argument("--config", help="path to a portable JSON dispatch config", default=None)
    dispatch_parser.add_argument("--journal", help="journal directory (default ./.orc)", default=None)
    dispatch_parser.add_argument("--max-attempts", type=int, default=None, help="override policy max_attempts")
    dispatch_parser.add_argument("--run-id", default=None, help="explicit delivery_run_id")
    dispatch_parser.set_defaults(func=cmd_dispatch)

    status_parser = subparsers.add_parser("status", help="print per-work state from a journal")
    status_parser.add_argument("target", help="journal path (dir or <run>.jsonl) or bare run id")
    status_parser.set_defaults(func=cmd_status)

    history_parser = subparsers.add_parser("history", help="print ordered journal records")
    history_parser.add_argument("target", help="journal path (dir or <run>.jsonl) or bare run id")
    history_parser.set_defaults(func=cmd_history)

    crew_report_parser = subparsers.add_parser(
        "crew-report", help="append/list crew-report/v1 records (TASK-M1-007, EXT-CREW-REPORT-V1)"
    )
    crew_report_subparsers = crew_report_parser.add_subparsers(dest="crew_report_command", required=True)

    crew_report_append_parser = crew_report_subparsers.add_parser(
        "append", help="append one crew-report/v1 record for a run/execution"
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
        "list", help="list crew-report/v1 records for a run, in append order"
    )
    crew_report_list_parser.add_argument("run_id", help="delivery_run_id")
    crew_report_list_parser.add_argument(
        "--execution-id", default=None, help="restrict to reports for one execution_id"
    )
    crew_report_list_parser.add_argument(
        "--journal", help="journal directory the report log sits beside (default ./.orc)", default=None
    )
    crew_report_list_parser.set_defaults(func=cmd_crew_report_list)

    report_parser = subparsers.add_parser(
        "report",
        help="render a self-contained HTML run report, or a local run index (TASK-M1-008)",
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
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
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


__all__ = ["build_parser", "main"]
