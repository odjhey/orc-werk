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

from orc_werk.adapters.jsonl import layout
from orc_werk.cli.hyperlink import hyperlink_path
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

# issue #55 H2: journal dir precedence is `--journal` flag > `ORC_JOURNAL_DIR`
# env > `./.orc`. Env var only -- deliberately no new CLI config-file
# surface (the no-framework/no-new-dependency posture, PLAYBOOK-CLI-USAGE's
# "No CLI framework, by design" section).
ORC_JOURNAL_DIR_ENV = "ORC_JOURNAL_DIR"


def resolve_journal_dir(explicit: Optional[str] = None) -> Path:
    """The one place journal-dir precedence (issue #55 H2) is decided:
    `explicit` (a command's own `--journal` flag value, when it has one and
    the caller passed it) wins; otherwise `ORC_JOURNAL_DIR` when set;
    otherwise the existing `./.orc` default. Every CLI entry point that
    previously wrote `Path(args.journal) if args.journal else
    Path(DEFAULT_JOURNAL_DIR)` inline now calls this instead, so the
    precedence order can never drift between commands."""
    if explicit:
        return Path(explicit)
    env_value = os.environ.get(ORC_JOURNAL_DIR_ENV)
    if env_value:
        return Path(env_value)
    return Path(DEFAULT_JOURNAL_DIR)


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


def _is_run_journal_path(path: Path) -> bool:
    """True when `path` is a run's canonical `<run_id>.jsonl` journal, as
    opposed to one of this package's adapter-owned sidecar files beside it
    (the crew-report log `<run_id>+reports.jsonl`, `EXT-CREW-REPORT-V1`;
    the observed-at time sidecar `<run_id>+times.jsonl`, issue #39).

    The rule is structural, not a suffix list (the attempt-2 watchtower
    ruling on PR #46): `+` is the reserved sidecar separator, deliberately
    OUTSIDE the safe run-id charset (`tailsafe.SAFE_DELIVERY_RUN_ID`,
    `[A-Za-z0-9_.-]`), so a run journal is exactly any `*.jsonl` whose stem
    contains no `+`. A dot-separated suffix list (the rejected first
    attempt used `.reports.jsonl`/`.times.jsonl`) collides with legal
    dot-namespaced run ids -- run id `m1.times` yields `m1.times.jsonl`,
    which a suffix list misclassifies as a sidecar, making the run
    invisible to `--all`/`--index` and bare-directory resolution. With `+`
    the collision is structurally impossible rather than avoided by
    convention. Every directory-listing call site that enumerates run
    journals (`_resolve_journal` below, `orc_werk.cli.report`'s
    `discover_run_ids`) must filter through this predicate instead of
    globbing `*.jsonl` alone."""
    return path.name.endswith(".jsonl") and "+" not in path.stem


def _available_run_ids(directory: Path) -> list[str]:
    """Run ids under `directory` (sorted), covering BOTH the new per-run
    directory layout and the legacy flat-file layout (issue #55 H1
    read-fallback) via `orc_werk.adapters.jsonl.layout.discover_run_ids`.
    Read-only: a missing directory returns `[]` rather than raising or
    creating anything. Shared by the `ERR-NOT-FOUND(run)` affordance below,
    `orc_werk.cli.report.discover_run_ids`, and the bare-`orc` index
    (issue #43) so all call sites can never drift on what counts as "a
    run"."""
    return layout.discover_run_ids(directory)


_PATH_SEPARATORS = tuple({os.sep, os.altsep} - {None})


def _looks_like_journal_path(target: str) -> bool:
    """True when `target` looks like a filesystem path (rather than a bare
    `delivery_run_id`) even though it doesn't currently resolve to a file
    or directory: it contains a path separator, or ends in `.jsonl`."""
    return target.endswith(".jsonl") or any(sep in target for sep in _PATH_SEPARATORS)


def _resolve_journal(target: str) -> tuple[Path, str]:
    """Resolve a `status`/`history`/`report` positional argument to
    `(journal_directory, delivery_run_id)`. Accepts: a path to a
    `<run_id>.jsonl` file (legacy layout); a path to a run's own new-layout
    directory (`.orc/<run_id>/`, issue #55 H1); a directory containing
    exactly one legacy `*.jsonl` file; or a bare run id (resolved against
    `ORC_JOURNAL_DIR`/`./.orc` per `resolve_journal_dir`'s precedence,
    issue #55 H2 -- these commands have no `--journal` flag of their own,
    so the env var is the only way to override the default here)."""
    path = Path(target)
    if path.is_file() and path.suffix == ".jsonl":
        return path.parent, path.stem
    if path.is_dir():
        # issue #55 H1: `target` may itself be one run's own new-layout
        # directory -- resolve directly to that run rather than falling
        # into the "directory containing exactly one run" branch below,
        # which would otherwise miscount this run's own times.jsonl/
        # reports.jsonl sidecars (also `*.jsonl`) as competing candidates.
        if (path / layout.JOURNAL_FILENAME).exists():
            return path.parent, path.name
        # `layout.discover_run_ids` already covers both layouts (new-layout
        # subdirectories containing journal.jsonl, and legacy flat *.jsonl
        # files minus sidecars) -- the same single source of truth the
        # bare-`orc` index and --all/--match use, so "a directory containing
        # exactly one run" resolves identically for both layouts here too.
        run_ids = layout.discover_run_ids(path)
        if len(run_ids) == 1:
            return path, run_ids[0]
        if not run_ids:
            raise CoreError(
                {
                    "error": "ERR-NOT-FOUND",
                    "message": f"no run journals found under directory: {target}",
                    "details": {"path": target},
                }
            )
        raise CoreError(
            {
                "error": "ERR-VALIDATION",
                "message": (
                    f"directory {target!r} contains multiple journals; pass the exact "
                    "run path or a bare run id instead"
                ),
                "details": {"path": target, "candidates": run_ids},
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
    return resolve_journal_dir(None), target


def _require_journal_file(directory: Path, run_id: str, *, target: str) -> Path:
    """#18 CLI fix: `status`/`history`/`report` must fail closed with
    canonical `ERR-NOT-FOUND` naming the run id when the resolved journal
    file does not exist on disk, instead of the old fail-open "(no work
    recorded yet)" exit 0. Checked *before* `JSONLJournal` is constructed
    (its `__init__` unconditionally `mkdir`s the journal directory) so a
    read-only command against an unknown run id never creates a stray
    `.orc/` directory as a side effect. `layout.journal_path` resolves new
    vs. legacy layout the same way `JSONLJournal` itself does (issue #55
    H1), so this check agrees with what a subsequent `JSONLJournal.history`
    call would actually read."""
    path = layout.journal_path(directory, run_id)
    if not path.exists():
        # ERR-NOT-FOUND(run) affordance (issue #43's HATEOAS reframe): print
        # a definitive list of what *does* exist under this journal dir --
        # or, when empty, the dispatch affordance to create one -- to
        # stdout before the canonical error propagates on stderr/exit 2
        # (both unchanged). This is presentation only: the error value
        # `status`/`history`/`report` ultimately raise is identical to
        # before this round.
        abs_dir = directory.resolve()
        # issue #55 OSC-8 scope addition: this is a standalone "index"
        # line (a directory-path listing), so it gets the clickable-path
        # treatment -- see orc_werk.cli.hyperlink's module docstring for
        # what does and does not qualify.
        abs_dir_display = hyperlink_path(abs_dir)
        available = _available_run_ids(directory)
        if available:
            print(f"available runs in {abs_dir_display}: {', '.join(available)}")
        else:
            print(f"0 runs in {abs_dir_display}")
        print("next:")
        print(
            f'  - orc dispatch "<intent text>" --config <path-to-dispatch-config.json> '
            f"--journal {abs_dir}"
        )
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
    "ORC_JOURNAL_DIR_ENV",
    "_available_run_ids",
    "_awaiting_label",
    "_intent_text",
    "_is_run_journal_path",
    "_looks_like_journal_path",
    "_require_journal_file",
    "_resolve_journal",
    "_root_cause_for_work",
    "resolve_journal_dir",
]
