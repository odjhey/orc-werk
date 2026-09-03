"""Machine-readable projections for `orc status --json` and the bare `orc
--json` index (issue #53).

## Why this exists

The dormant registry (`docs/delivery/M4-cockpit-and-clarity.md`) held
`--json` back until a named trigger fired: "the first structured
consumer... OR observed fragility in push-mode agents parsing human status
lines." Issue #53's own trigger comment observed `cat run.jsonl | jq -s`
already covers ad hoc scripting over one journal, so this module's payload
is deliberately the DERIVED per-work/index PROJECTION plus resolvable
references and affordances -- content a script would otherwise have to
replay the journal itself to reconstruct -- not a second copy of the raw
journal.

## Design

- **Versioned, not a canonical protocol shape** (`CLAUDE.md` #10 / repo
  rule 10 -- this is interchange, not core domain state): every document
  this module builds carries a top-level `"schema"` string
  (`orc-status/v1`, `orc-index/v1`). Like `orc_werk.cli.config`'s config
  schema, this is CLI-owned composition, not a `docs/contracts/` contract.
  It is documented HERE -- this docstring is the single source of truth,
  mirroring `config.py`'s own "this docstring IS the schema" convention,
  cited (not restated) from `docs/cli/README.md`'s status/index sections
  -- rather than via a new `orc json-schema` subcommand: no extra CLI
  surface is justified when the shape already has one obvious,
  discoverable code-adjacent home, and `docs/cli/README.md` is already the
  canonical per-command reference every other flag is documented from.
- **Content = what the text surface already knows, structured** (never a
  parallel derivation): every field here is read from the same
  `DeliveryProjection`/journal `history` the text renderers
  (`orc_werk.cli.main._work_line`/`_index_run_line`,
  `orc_werk.cli.refs.collect_refs`,
  `orc_werk.cli.affordances.render_next_block`) already read, through the
  SAME helper functions (`is_pending`, `_awaiting_label`, `collect_refs`,
  `orc_werk.cli.affordances.next_entries` -- the structured sibling of
  `render_next_block`, sharing its `_group_works`/`_work_group_key`
  per-state map) -- never a second, potentially-drifting source of truth
  for what a Work's state or a run's affordances actually are.
- **Byte-discipline** (issue #53 R3): a caller prints exactly one
  `dump_json(...)` document to stdout and nothing else when `--json` is
  set, with the same exit code the text surface would report; a canonical
  error still goes to stderr as today (`orc_werk.cli.main._print_error`),
  with stdout left empty (`orc_werk.cli.journal_reading._require_journal_
  file`'s own pre-error stdout prints are suppressed via its `quiet`
  parameter in `--json` mode).
- **Determinism** (issue #53 R4): `dump_json` always passes
  `sort_keys=True` and this module adds no wall-clock or random data --
  only fields already present on the projection/history/journal-dir
  arguments a caller passes in -- so two invocations against an unchanged
  journal produce byte-identical output.

## Shapes

`orc-status/v1` (`status_document`, `orc status --json`):

```json
{
  "schema": "orc-status/v1",
  "run_id": "<run id>",
  "intent": "<submitted intent text, or null>",
  "works": [
    {
      "work_id": "<work id>",
      "state": "<STATE-DELIVERY state, e.g. EXECUTING/ASSURING/ACCEPTED/BLOCKED>",
      "attempts": 1,
      "attempt": 1,
      "pending": false,
      "awaiting": null,
      "candidate_fingerprint": "fp-...",
      "blocked_reason": null
    }
  ],
  "refs": [
    {
      "kind": "session",
      "provider": "external-agent",
      "value": "sess-9f2c",
      "resolve_command": "-",
      "verdict": null
    }
  ],
  "next": [
    {"description": "work(s) accepted: work-1", "command": "orc report demo-run-1"}
  ]
}
```

`works` is sorted by `work_id` (the same order `orc status` prints).
`attempt` is `null` unless `pending` is `true` -- it mirrors the text
line, which only ever renders a separate `attempt=N` fragment alongside
`awaiting=` for a pending Work; `attempts` alone already carries the
count otherwise, so a non-pending Work's `attempt` field would be a
redundant restatement, not new information the text surface conveys.
`candidate_fingerprint`/`blocked_reason`/`awaiting` are `null` when
absent, never omitted -- a fixed key set every Work object carries, so a
consumer can destructure without a presence check. `refs` is
`orc_werk.cli.refs.collect_refs`'s row list, field for field (this is the
load-bearing part for the #65 follow-on lane: a structured consumer walks
`refs` instead of scraping `orc refs`'s text table). `next` is
`orc_werk.cli.affordances.next_entries`'s output, one entry per text
`next:` bullet; `command` is `null` for a bullet with no runnable command
of its own (e.g. "record the execution outcome for work(s): ...").

`orc-index/v1` (`index_document`, bare `orc --json`):

```json
{
  "schema": "orc-index/v1",
  "journal_dir": "/abs/path/.orc",
  "total": 2,
  "truncated": false,
  "next_page_command": null,
  "runs": [
    {
      "run_id": "demo-run-1",
      "states": {"ACCEPTED": 1},
      "flags": [],
      "works": [
        {
          "work_id": "work-1",
          "state": "ACCEPTED",
          "attempts": 1,
          "pending": false,
          "awaiting": null,
          "blocked_reason": null
        }
      ]
    }
  ]
}
```

`runs` is in the exact same most-recently-active-first order the text
index prints (`orc_werk.cli.report.ordered_run_entries`, the `TASK-M4B-001`
unified-ordering invariant) -- both surfaces are built from the SAME
already-ordered `window_entries` sequence in `orc_werk.cli.main.cmd_index`,
so the ordering can never drift between them. A run whose projection could
not be replayed (`ERR-CONFLICT`, a corrupted/hand-edited journal) appears
as `{"run_id": "...", "error": "ERR-CONFLICT"}` -- the same
degrade-per-run-not-per-listing behavior the text index gives (issue #52),
just without the parenthetical prose. `total` is the full corpus count
before `--limit` windowing (matching the text index's leading "`N` runs
in..." line); `next_page_command` is the exact `orc --limit ... --before
...` string the text index's "next (older) page" line would print, or
`null` when the listing was not truncated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.app.orchestrator import is_pending
from orc_werk.cli.affordances import next_entries
from orc_werk.cli.journal_reading import _awaiting_label
from orc_werk.cli.refs import collect_refs
from orc_werk.core.state import STATE_BLOCKED, DeliveryProjection, WorkProjection

STATUS_SCHEMA = "orc-status/v1"
INDEX_SCHEMA = "orc-index/v1"


def dump_json(document: Mapping[str, Any]) -> str:
    """The one `--json` stdout line: `sort_keys=True` (same style
    `orc_werk.cli.main._print_error` already uses for the canonical error
    channel), no wall-clock or random content added anywhere upstream of
    this call -- deterministic/byte-stable across repeated invocations
    against an unchanged journal (issue #53 R4)."""
    return json.dumps(document, sort_keys=True)


def _work_document(work_id: str, wp: WorkProjection) -> dict[str, Any]:
    pending = is_pending(wp)
    return {
        "work_id": work_id,
        "state": wp.state,
        "attempts": wp.attempt_number,
        "attempt": wp.attempt_number if pending else None,
        "pending": pending,
        "awaiting": _awaiting_label(wp) if pending else None,
        "candidate_fingerprint": wp.current_candidate_fingerprint(),
        "blocked_reason": wp.blocked_reason,
    }


def status_document(
    *,
    run_id: str,
    projection: DeliveryProjection,
    history: Sequence[Mapping[str, Any]],
    directory: Path,
    intent_text: Optional[str],
) -> dict[str, Any]:
    """`orc-status/v1` -- see this module's docstring for the full shape."""
    works = [_work_document(work_id, projection.works[work_id]) for work_id in sorted(projection.works)]
    refs = [
        {
            "kind": row.kind,
            "provider": row.provider,
            "value": row.value,
            "resolve_command": row.resolve.display,
            "verdict": row.verdict,
        }
        for row in collect_refs(directory, run_id, history)
    ]
    next_block = [
        {"description": entry.description, "command": entry.command}
        for entry in next_entries(
            projection,
            history,
            run_id=run_id,
            journal_dir=directory.resolve(),
            config_path=None,
            intent_text=intent_text,
        )
    ]
    return {
        "schema": STATUS_SCHEMA,
        "run_id": run_id,
        "intent": intent_text,
        "works": works,
        "refs": refs,
        "next": next_block,
    }


def _index_states_and_flags(projection: DeliveryProjection) -> tuple[dict[str, int], list[str]]:
    counts: dict[str, int] = {}
    for wp in projection.works.values():
        counts[wp.state] = counts.get(wp.state, 0) + 1
    flags: list[str] = []
    if any(wp.state == STATE_BLOCKED for wp in projection.works.values()):
        flags.append("blocked")
    if any(is_pending(wp) for wp in projection.works.values()):
        flags.append("pending")
    return counts, flags


def index_run_document(run_id: str, projection: DeliveryProjection) -> dict[str, Any]:
    """One `orc-index/v1` `runs[]` entry for a run whose projection loaded
    cleanly. Callers append `{"run_id": ..., "error": "ERR-..."}` directly
    for a run whose replay failed (`main.py`'s existing per-run degrade,
    issue #52) instead of calling this."""
    states, flags = _index_states_and_flags(projection)
    works = []
    for work_id in sorted(projection.works):
        wp = projection.works[work_id]
        pending = is_pending(wp)
        works.append(
            {
                "work_id": work_id,
                "state": wp.state,
                "attempts": wp.attempt_number,
                "pending": pending,
                "awaiting": _awaiting_label(wp) if pending else None,
                "blocked_reason": wp.blocked_reason,
            }
        )
    return {"run_id": run_id, "states": states, "flags": flags, "works": works}


def index_document(
    *,
    journal_dir: Path,
    runs: Sequence[Mapping[str, Any]],
    total: int,
    truncated: bool,
    next_page_command: Optional[str],
) -> dict[str, Any]:
    """`orc-index/v1` -- see this module's docstring for the full shape.
    `runs` must already be in the caller's final display order (the same
    `window_entries` the text index iterates in `orc_werk.cli.main.
    cmd_index`) -- the `TASK-M4B-001` unified-ordering invariant is
    satisfied by construction: both surfaces consume the identical ordered
    sequence, this function does not re-sort it."""
    return {
        "schema": INDEX_SCHEMA,
        "journal_dir": str(journal_dir),
        "total": total,
        "truncated": truncated,
        "next_page_command": next_page_command,
        "runs": list(runs),
    }


__all__ = [
    "INDEX_SCHEMA",
    "STATUS_SCHEMA",
    "dump_json",
    "index_document",
    "index_run_document",
    "status_document",
]
