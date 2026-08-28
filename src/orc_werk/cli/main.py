"""`orc` CLI (`TASK-M0-005`): `dispatch`, `status`, `history` over the M0
orchestrator with the dependency-free memory/scripted/JSONL adapters.

Exit codes: `0` on an ACCEPTED-terminal (all Work accepted), nonzero (`1`)
when any Work is BLOCKED, nonzero (`2`) on a canonical error. Errors print
the canonical error value (`CONTRACT-ERRORS`) as JSON to stderr, never a
Python traceback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.app.orchestrator import Orchestrator
from orc_werk.cli.config import build_run_config, build_scripted_adapters, load_config
from orc_werk.core.errors import CoreError
from orc_werk.core.state import STATE_BLOCKED

DEFAULT_JOURNAL_DIR = ".orc"


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
    any_blocked = False
    for work_id in sorted(projection.works):
        wp = projection.works[work_id]
        if wp.state == STATE_BLOCKED:
            any_blocked = True
        fingerprint = wp.current_candidate_fingerprint() or "-"
        print(
            f"work {work_id}: state={wp.state} attempts={wp.attempt_number} "
            f"candidate_fingerprint={fingerprint}"
            + (f" blocked_reason={wp.blocked_reason}" if wp.blocked_reason else "")
        )
    return 1 if any_blocked else 0


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

    any_blocked = False
    for work_id in sorted(projection.works):
        wp = projection.works[work_id]
        if wp.state == STATE_BLOCKED:
            any_blocked = True
        fingerprint = wp.current_candidate_fingerprint() or "-"
        print(
            f"work {work_id}: state={wp.state} attempts={wp.attempt_number} "
            f"candidate_fingerprint={fingerprint}"
            + (f" blocked_reason={wp.blocked_reason}" if wp.blocked_reason else "")
        )
    return 1 if any_blocked else 0


def _compact(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def cmd_history(args: argparse.Namespace) -> int:
    directory, run_id = _resolve_journal(args.target)
    journal = JSONLJournal(directory)
    for record in journal.history(delivery_run_id=run_id):
        print(f"[{record['seq']:04d}] {record['kind']:8s} {record['id']:28s} {_compact(record['data'])}")
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


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["build_parser", "main"]
