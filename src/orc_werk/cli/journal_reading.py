"""Shared read-side helpers for CLI commands that resolve a journal target
and present per-work state (`status`, `history`, `report` -- `TASK-M1-002`,
`TASK-M1-003`, `TASK-M1-008`).

Extracted from `orc_werk.cli.main` (which re-imports and re-exports these
names, so existing imports of e.g. `orc_werk.cli.main._root_cause_for_work`
keep working unchanged) so `orc_werk.cli.report` can reuse the exact same
target-resolution/presentation logic `status`/`history` already use instead
of re-deriving it by hand (CLAUDE.md #3: do not invent missing semantics;
this module invents none -- it is pure CLI presentation composition over
`JournalPort`'s public `history`/`load_projection`). No behavior change:
this is a pure code-motion refactor, not a semantic one.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.core.effects import FX_START_EXECUTION
from orc_werk.core.errors import CoreError, not_found_error
from orc_werk.core.facts import FACT_INTENT_SUBMITTED
from orc_werk.core.state import STATE_ASSURING, STATE_EXECUTING, WorkProjection

# core/policy.py's `_block_reason` returns this literal with no exported
# constant (CLAUDE.md #7/#8: core stays minimal, this string is not part of
# any canonical registry) -- duplicated here, CLI-presentation-only, to key
# the #16 root-cause suffix off the same block reason `status`/`dispatch`
# already print verbatim.
BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED = "retry-budget-exhausted"

DEFAULT_JOURNAL_DIR = ".orc"


def _awaiting_label(wp: WorkProjection) -> str:
    """CLI-owned, non-normative presentation label for `status`/`dispatch`/
    `report` output naming what a pending Work is waiting on."""
    if wp.state == STATE_EXECUTING:
        return "execution-outcome"
    if wp.state == STATE_ASSURING:
        return "assurance-verdict"
    return "unknown"


def _root_cause_for_work(history: Sequence[Mapping[str, Any]], work_id: str) -> Optional[str]:
    """#16: read this Work's journaled `FX-START-EXECUTION` effect records
    for a dispatch-time canonical error (`dispatch_result.error`) and
    return the most recent one, or `None` if every attempt started
    cleanly. `history` is `seq`-ordered ascending, so the last matching
    record encountered is the most recent -- CLI presentation only, reads
    the same journaled effect records `history` already exposes
    (`docs/delivery/M1-delivery-ledger.md` #16, no contract change)."""
    latest_error: Optional[str] = None
    for record in history:
        if record.get("kind") != "effect" or record.get("id") != FX_START_EXECUTION:
            continue
        data = record.get("data", {})
        if data.get("work_id") != work_id:
            continue
        dispatch_result = data.get("dispatch_result")
        if isinstance(dispatch_result, Mapping) and "error" in dispatch_result:
            latest_error = dispatch_result["error"]
    return latest_error


def _intent_text(history: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """#23: the submitted intent text (`FACT-INTENT-SUBMITTED.data.text`),
    not the run/intent id -- the run id is already shown separately under
    `run:`."""
    for record in history:
        if record.get("kind") == "fact" and record.get("id") == FACT_INTENT_SUBMITTED:
            return record.get("data", {}).get("text")
    return None


# Non-journal `*.jsonl`-suffixed sidecars this package writes beside a
# run's canonical `<run_id>.jsonl` in the same directory: the crew-report
# log (`<run_id>.reports.jsonl`, `EXT-CREW-REPORT-V1`) and the observed-at
# time sidecar (`<run_id>.times.jsonl`, issue #39,
# `orc_werk.adapters.jsonl.journal`'s "Observed-at time sidecar" section).
# Both also match a naive `*.jsonl` glob, so every directory-listing call
# site that enumerates run journals (`_resolve_journal` below,
# `orc_werk.cli.report`'s `render_index`/`render_all`) must filter through
# `_is_run_journal_path` instead of globbing `*.jsonl` alone -- otherwise a
# run with a crew-report or times sidecar looks like "two journals" to
# directory-based resolution.
_SIDECAR_SUFFIXES = (".reports.jsonl", ".times.jsonl")


def _is_run_journal_path(path: Path) -> bool:
    name = path.name
    return name.endswith(".jsonl") and not name.endswith(_SIDECAR_SUFFIXES)


_PATH_SEPARATORS = tuple({os.sep, os.altsep} - {None})


def _looks_like_journal_path(target: str) -> bool:
    """True when `target` looks like a filesystem path (rather than a bare
    `delivery_run_id`) even though it doesn't currently resolve to a file
    or directory: it contains a path separator, or ends in `.jsonl`."""
    return target.endswith(".jsonl") or any(sep in target for sep in _PATH_SEPARATORS)


def _resolve_journal(target: str) -> tuple[Path, str]:
    """Resolve a `status`/`history`/`report` positional argument to
    `(journal_directory, delivery_run_id)`. Accepts: a path to a
    `<run_id>.jsonl` file; a directory containing exactly one `*.jsonl`
    file; or a bare run id (resolved against `./.orc`, the `dispatch`
    default journal directory)."""
    path = Path(target)
    if path.is_file() and path.suffix == ".jsonl":
        return path.parent, path.stem
    if path.is_dir():
        candidates = sorted(p for p in path.glob("*.jsonl") if _is_run_journal_path(p))
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


def _require_journal_file(directory: Path, run_id: str, *, target: str) -> Path:
    """#18 CLI fix: `status`/`history`/`report` must fail closed with
    canonical `ERR-NOT-FOUND` naming the run id when the resolved journal
    file does not exist on disk, instead of the old fail-open "(no work
    recorded yet)" exit 0. Checked *before* `JSONLJournal` is constructed
    (its `__init__` unconditionally `mkdir`s the journal directory) so a
    read-only command against an unknown run id never creates a stray
    `.orc/` directory as a side effect."""
    path = directory / f"{run_id}.jsonl"
    if not path.exists():
        raise not_found_error(
            f"no journal found for run id: {run_id}",
            delivery_run_id=run_id,
            path=str(path),
            target=target,
        )
    return path


__all__ = [
    "BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED",
    "DEFAULT_JOURNAL_DIR",
    "_awaiting_label",
    "_intent_text",
    "_is_run_journal_path",
    "_looks_like_journal_path",
    "_require_journal_file",
    "_resolve_journal",
    "_root_cause_for_work",
]
