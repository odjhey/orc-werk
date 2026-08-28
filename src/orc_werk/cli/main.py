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
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.app.orchestrator import Orchestrator, is_pending
from orc_werk.cli.config import build_run_config, build_scripted_adapters, load_config
from orc_werk.core.errors import CoreError
from orc_werk.core.state import STATE_ACCEPTED, STATE_ASSURING, STATE_BLOCKED, STATE_EXECUTING, WorkProjection

DEFAULT_JOURNAL_DIR = ".orc"

# TASK-M1-002/SCN-007: the distinct in-progress exit code -- additive to
# the existing 0 (all ACCEPTED) / 1 (any BLOCKED) / 2 (canonical error)
# contract in docs/playbooks/cli-usage.md, never a replacement of it.
# Reported whenever the run is non-terminal and nothing further can be
# decided without operator-recorded input (a pending Work resting at
# EXECUTING/ASSURING with an unobserved outcome, or -- degenerate v0 edge
# case, not exercised by any golden scenario -- any other non-terminal
# resting point `_advance_one_phase` cannot progress past).
EXIT_PENDING = 3


def _awaiting_label(wp: WorkProjection) -> str:
    """CLI-owned, non-normative presentation label for `status`/`dispatch`
    output naming what a pending Work is waiting on."""
    if wp.state == STATE_EXECUTING:
        return "execution-outcome"
    if wp.state == STATE_ASSURING:
        return "assurance-verdict"
    return "unknown"


def _work_line(work_id: str, wp: WorkProjection) -> str:
    fingerprint = wp.current_candidate_fingerprint() or "-"
    line = (
        f"work {work_id}: state={wp.state} attempts={wp.attempt_number} "
        f"candidate_fingerprint={fingerprint}"
    )
    if wp.blocked_reason:
        line += f" blocked_reason={wp.blocked_reason}"
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


_PATH_SEPARATORS = tuple({os.sep, os.altsep} - {None})


def _looks_like_journal_path(target: str) -> bool:
    """True when `target` looks like a filesystem path (rather than a bare
    `delivery_run_id`) even though it doesn't currently resolve to a file
    or directory: it contains a path separator, or ends in `.jsonl`."""
    return target.endswith(".jsonl") or any(sep in target for sep in _PATH_SEPARATORS)


def _derive_run_id(intent_text: str) -> str:
    """Deterministic run id from the intent text (CLAUDE.md #9-friendly:
    no randomness/wall-clock). Callers wanting a stable run id across
    reruns should pass `--run-id`/config `run_id` explicitly instead."""
    digest = hashlib.sha256(intent_text.encode("utf-8")).hexdigest()[:12]
    return f"run-{digest}"


def _resolve_journal(target: str) -> tuple[Path, str]:
    """Resolve a `status`/`history` positional argument to
    `(journal_directory, delivery_run_id)`. Accepts: a path to a
    `<run_id>.jsonl` file; a directory containing exactly one `*.jsonl`
    file; or a bare run id (resolved against `./.orc`, the `dispatch`
    default journal directory)."""
    path = Path(target)
    if path.is_file() and path.suffix == ".jsonl":
        return path.parent, path.stem
    if path.is_dir():
        candidates = sorted(path.glob("*.jsonl"))
        if len(candidates) == 1:
            return path, candidates[0].stem
        if not candidates:
            raise CoreError(
                {
                    "error": "ERR-NOT-FOUND",
                    "message": f"no *.jsonl journal files found under directory: {target}",
                    "details": {"path": target},
                }
            )
        raise CoreError(
            {
                "error": "ERR-VALIDATION",
                "message": (
                    f"directory {target!r} contains multiple journals; pass the exact "
                    "<run_id>.jsonl path or a bare run id instead"
                ),
                "details": {"path": target, "candidates": [c.name for c in candidates]},
            }
        )
    # FRICTION-5: a target that looks like a path (contains a path
    # separator, or ends in `.jsonl`) but doesn't exist must not fall
    # through into the bare-run-id branch below -- that branch hands the
    # raw string to `JSONLJournal._path_for`, whose `delivery_run_id`
    # filename-safety check then leaks an implementation detail
    # ("... is not a safe JSONL journal filename component") instead of
    # naming the actually-missing path.
    if _looks_like_journal_path(target) and not path.exists():
        raise CoreError(
            {
                "error": "ERR-NOT-FOUND",
                "message": f"journal path does not exist: {target}",
                "details": {"path": target},
            }
        )
    return Path(DEFAULT_JOURNAL_DIR), target


def _print_error(error: dict) -> None:
    print(json.dumps(error, sort_keys=True), file=sys.stderr)


def cmd_dispatch(args: argparse.Namespace) -> int:
    config = load_config(args.config) if args.config else {}
    run_id = args.run_id or config.get("run_id") or _derive_run_id(args.intent)
    journal_dir = Path(args.journal) if args.journal else Path(DEFAULT_JOURNAL_DIR)

    journal = JSONLJournal(journal_dir)
    work_graph = MemoryWorkGraph()
    execution, candidate, assurance = build_scripted_adapters(config, delivery_run_id=run_id)
    run_config = build_run_config(config, max_attempts_override=args.max_attempts)

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

    print(f"run: {run_id}")
    print(f"journal: {journal_dir / (run_id + '.jsonl')}")
    for work_id in sorted(projection.works):
        print(_work_line(work_id, projection.works[work_id]))
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
    journal = JSONLJournal(directory)
    projection = journal.load_projection(delivery_run_id=run_id)

    print(f"run: {run_id}")
    if projection.intent_id:
        print(f"intent: {projection.intent_id}")
    if not projection.works:
        print("(no work recorded yet)")
        return 0

    for work_id in sorted(projection.works):
        print(_work_line(work_id, projection.works[work_id]))
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
