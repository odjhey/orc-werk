"""`orc report` (`TASK-M1-008`; round 2 -- issues #39, #40): read-only,
stdlib-only, self-contained HTML renderer for one DeliveryRun's journal
(`PORT-JOURNAL-ENVELOPE`) and observed-at time sidecar
(`CONTRACT-DURABILITY`'s "record observation wall-clock times" row), for
async human review by a reader who did not watch the run happen; a small
local index page over a journal directory's runs (`--index`); and
wildcard/namespace rendering of every run whose `run_id` `fnmatch`es a glob
plus a scoped index (`--all [--match GLOB] [--out-dir DIR]`, issue #40).
Every path this module prints is the resolved absolute path (issue #40
comment), OSC-8-clickable when stdout is a TTY (issue #55,
`orc_werk.cli.hyperlink`). A single run's default output now lands inside
that run's own per-run directory when it uses the new layout (issue #55
H1, `orc_werk.adapters.jsonl.layout.report_html_path`).

This module is CLI-owned composition, not product semantics
(`docs/delivery/task-cards/TASK-M1-008-run-report-renderer.md`): it
displays exactly what the journal/report log already recorded, computing
no derived judgments the kernel did not make. It reuses:

- the reducer projection (`orc_werk.core.reducer` via
  `JSONLJournal.load_projection`) for per-work state, never re-deriving it
  by hand;
- the same target-resolution/presentation helpers `status`/`history`
  already use (`orc_werk.cli.journal_reading`), so a missing run fails
  closed with canonical `ERR-NOT-FOUND` the same way;
- the public `JournalPort` adapter API for all reads -- never raw file
  parsing.

Presentation rules (normative for this surface, from the task card):
status colors are reserved for canonical delivery
state/verdict/outcome and always paired with a text label (icon + word,
never color alone -- `dataviz` skill's status-palette/marks-and-anatomy
guidance); output is self-contained (inline CSS only, no external
requests), light+dark via `prefers-color-scheme`; all dynamic text is
`html.escape`d; wide content scrolls in its own container. Hard
constraints: stdlib-only string templating (no template engine); strictly
read-only except the one announced output HTML file.
"""

from __future__ import annotations

import argparse
import fnmatch
import html
import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.jsonl import layout
from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.app.orchestrator import is_pending
from orc_werk.cli.hyperlink import hyperlink_path
from orc_werk.cli.journal_reading import (
    _available_run_ids,
    _awaiting_label,
    _intent_text,
    _require_journal_file,
    _resolve_journal,
    _root_cause_for_work,
    resolve_journal_dir,
)
from orc_werk.core.errors import CoreError, not_found_error, validation_error
from orc_werk.core.state import (
    STATE_ACCEPTED,
    STATE_ASSURING,
    STATE_BLOCKED,
    STATE_EXECUTING,
    STATE_READY,
    DeliveryProjection,
    WorkProjection,
)

# ---------------------------------------------------------------------------
# Status-color mapping (dataviz skill's status palette: good/warning/
# serious/critical, "fixed -- never themed"; reserved for canonical
# delivery state/verdict/outcome only).
# ---------------------------------------------------------------------------

_STATE_STATUS: Mapping[str, str] = {
    STATE_ACCEPTED: "good",
    STATE_BLOCKED: "critical",
    STATE_EXECUTING: "warning",
    STATE_ASSURING: "warning",
    STATE_READY: "neutral",
}
_VERDICT_STATUS: Mapping[str, str] = {
    "accepted": "good",
    "rejected": "critical",
    "inconclusive": "warning",
}
_OUTCOME_STATUS: Mapping[str, str] = {
    "completed": "good",
    "failed": "critical",
}
_STATUS_ICON: Mapping[str, str] = {
    "good": "✓",
    "warning": "⏳",
    "serious": "⚠",
    "critical": "✕",
    "neutral": "○",
}


def _compact_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _esc_json(data: Any) -> str:
    return f"<code>{html.escape(_compact_json(data))}</code>"


def _chip(label: str, status: str) -> str:
    """A status chip: icon + word, never color-alone (marks-and-anatomy:
    "labels+icons never color-alone"; "text never wears the data color" --
    the colored icon carries the status, the label text stays in the ink
    token)."""
    icon = _STATUS_ICON.get(status, _STATUS_ICON["neutral"])
    return (
        f'<span class="chip chip-{html.escape(status)}">'
        f'<span class="chip-icon" aria-hidden="true">{icon}</span>'
        f'<span class="chip-label">{html.escape(label)}</span>'
        "</span>"
    )


def _state_chip(work_id: str, wp: WorkProjection) -> str:
    status = _STATE_STATUS.get(wp.state, "neutral")
    return _chip(f"{work_id}: {wp.state}", status)


# ---------------------------------------------------------------------------
# Journal-record helpers (read-only derivations over already-loaded
# history; no new semantics -- pure presentation lookups).
# ---------------------------------------------------------------------------


def _work_id_of(record: Mapping[str, Any]) -> Optional[str]:
    return record.get("data", {}).get("work_id") or None


def _load_times_sidecar(directory: Path, run_id: str) -> tuple[dict[int, str], int]:
    """Best-effort read of the observed-at time sidecar (issue #39,
    `CONTRACT-DURABILITY`'s "record observation wall-clock times" row,
    `orc_werk.adapters.jsonl.journal`'s "Observed-at time sidecar"
    section), joined into the timeline by `seq`. This is the sidecar's
    *only* reader -- `JSONLJournal.history`/`load_projection` never touch
    it, so this function is never called on the replay/projection path,
    only from this module's rendering.

    Absence is not an error: a missing sidecar (e.g. any run recorded
    through `MemoryJournal`, which never writes one) returns an empty map
    -- the report renders cleanly with no per-record/header times at all.

    A corrupt or partially-written sidecar also never blocks rendering:
    unlike the canonical journal (which fails closed on a malformed
    non-final line, `PORT-JOURNAL`'s durable-journal recovery clause),
    this reader degrades per *line* -- a line that isn't valid JSON, or
    that doesn't carry the two expected fields in the expected shape, is
    skipped and counted, not raised. That asymmetry is deliberate: a
    malformed journal line risks silently losing canonical orchestration
    truth, which must fail loudly; a malformed *times* line only ever
    costs one record's presentation timestamp, and refusing to render an
    entire report over one bad enrichment line would be a strictly worse
    operator experience than rendering with that one time simply omitted.

    Returns `(seq -> observed_at, skipped_line_count)` so the caller can
    surface a "N corrupt sidecar record(s) skipped" note (skip-with-note,
    never skip-silently) alongside the times.
    """
    # issue #55 H1: new-layout `<run_id>/times.jsonl`, or legacy
    # `<run_id>+times.jsonl` -- the same discriminator JSONLJournal uses.
    path = layout.times_path(directory, run_id)
    times: dict[int, str] = {}
    skipped = 0
    if not path.exists():
        return times, skipped
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return times, skipped
    for raw_line in raw_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
            seq = record["seq"]
            observed_at = record["observed_at"]
            if isinstance(seq, bool) or not isinstance(seq, int) or not isinstance(observed_at, str):
                raise ValueError("malformed times sidecar record shape")
        except (ValueError, KeyError, TypeError):
            skipped += 1
            continue
        times[seq] = observed_at
    return times, skipped


def _fact_seq_index(history: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], int]:
    """Map `(fact_id, compact-json(data))` -> `seq`, so a decision's
    embedded `basis` fact snapshots (which carry no `seq` of their own --
    `PORT-JOURNAL-ENVELOPE`'s basis snapshots are plain fact dicts) can be
    linked back to the exact journaled record that quotes the same id+data,
    when one exists in this run's history."""
    index: dict[tuple[str, str], int] = {}
    for record in history:
        if record.get("kind") == "fact":
            key = (record.get("id", ""), _compact_json(record.get("data", {})))
            index[key] = record.get("seq", 0)
    return index


def _candidate_subject_identities(
    history: Sequence[Mapping[str, Any]], work_id: str
) -> dict[str, Any]:
    """Portable `subject_identity` per `candidate_id`, read from this
    Work's journaled `FX-IDENTIFY-CANDIDATE` effect records --
    `FACT-CANDIDATE-OBSERVED` itself only carries the fingerprint, not the
    subject identity (`PROTOCOL-FACTS`)."""
    result: dict[str, Any] = {}
    for record in history:
        if record.get("kind") != "effect" or record.get("id") != "FX-IDENTIFY-CANDIDATE":
            continue
        if _work_id_of(record) != work_id:
            continue
        candidate = record.get("data", {}).get("dispatch_result", {}).get("candidate")
        if isinstance(candidate, Mapping):
            candidate_id = candidate.get("id")
            if candidate_id:
                result[candidate_id] = candidate.get("subject_identity")
    return result


def _verdict_evidence_refs(
    history: Sequence[Mapping[str, Any]], work_id: str, assurance_id: Optional[str]
) -> Any:
    """`evidence_refs`, when the journaled `FACT-ASSURE-SETTLED` record
    happens to carry one -- read defensively (`.get`), never invented: the
    v0 orchestrator does not currently transport `AssuranceObservation.
    evidence_refs` into the canonical fact, so this is commonly absent, and
    absence renders as absence, not a fabricated value."""
    for record in history:
        if record.get("kind") != "fact" or record.get("id") != "FACT-ASSURE-SETTLED":
            continue
        data = record.get("data", {})
        if data.get("work_id") == work_id and data.get("assurance_id") == assurance_id:
            return data.get("evidence_refs")
    return None


def _find_create_work_plan(history: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """The run's topology, read from the journaled `FX-CREATE-WORK` effect
    record's `data.plan` (`PORT-WORK-001` plan shape) -- never from a
    dispatch config, which this report never reads and the kernel does not
    durably own (`CONTRACT-DURABILITY`'s "delegated work specification"
    row). `CONTRACT-DURABILITY`'s "Run topology" row (operator ruling,
    issue #41) makes this effect record the normative durable owner of
    topology -- a journal from which it cannot be reconstructed is
    non-conformant -- and names this report's dependency-tree view as a
    presentation surface that MAY rely on it. Mirrors
    `tests/scenarios/test_topology_durability.py`'s own reconstruction
    helper, which pins the same record as the regression target."""
    for record in history:
        if record.get("kind") == "effect" and record.get("id") == "FX-CREATE-WORK":
            plan = record.get("data", {}).get("plan")
            if isinstance(plan, Mapping):
                return plan
    return None


def _plan_topology(plan: Mapping[str, Any]) -> tuple[list[str], dict[str, list[str]]]:
    """`(order, deps_by_work)` read directly off the recorded plan's own
    `works` list -- `order` is plan-declaration order (never re-sorted;
    that order is itself part of the recorded plan and is what "first
    blocker" placement below is defined against), `deps_by_work[work_id]`
    is that work's dep ids in the order the plan declared them. Malformed
    entries (missing/non-string `work_id`, non-list `deps`) are skipped
    defensively rather than raised -- this is a read-only presentation
    derivation over already-durable data, not a validator; a malformed
    plan is a foreign-journal/adapter-bug concern, not something this
    report should crash on."""
    order: list[str] = []
    deps_by_work: dict[str, list[str]] = {}
    works = plan.get("works")
    if not isinstance(works, list):
        return order, deps_by_work
    for entry in works:
        if not isinstance(entry, Mapping):
            continue
        work_id = entry.get("work_id")
        if not isinstance(work_id, str) or not work_id:
            continue
        order.append(work_id)
        deps: list[str] = []
        raw_deps = entry.get("deps")
        if isinstance(raw_deps, list):
            for dep in raw_deps:
                if isinstance(dep, Mapping):
                    dep_id = dep.get("work_id")
                    if isinstance(dep_id, str) and dep_id:
                        deps.append(dep_id)
        deps_by_work[work_id] = deps
    return order, deps_by_work


def _build_dependency_tree(
    order: Sequence[str], deps_by_work: Mapping[str, Sequence[str]]
) -> tuple[list[str], dict[str, list[str]]]:
    """Placement rule (issue #41 scope item 1, justified here): every work
    is placed under exactly one parent -- its *first* declared blocker
    (`deps[0]`) -- so the rendered structure is a true tree (one
    indentation site per node, no duplication) even for a diamond/fan-in
    shape (e.g. `a->b,c->d`: `d` depends on both `b` and `c`, so it is
    placed once, under `b`, its first-declared blocker). No dependency
    edge is ever hidden by this choice: the *full* dep list still appears
    in that node's "unlocked by accepted completion of: ..." annotation
    (`_render_dependency_node` below) -- only the *indentation* site is
    singular, not the recorded semantics. "First" means first in the
    plan's own declared `deps` order, a property of the durably recorded
    plan itself (`_plan_topology`'s `order`-preserving read), never an
    invented health/priority judgment about which blocker "matters more".

    Returns `(roots, children)`: `roots` are works with no deps, in plan
    order; `children[parent]` are the works whose first blocker is
    `parent`, in plan order. A work whose first blocker is itself absent
    from `order` (a dangling/malformed dep reference) is simply never
    added to any parent's children list here -- `_render_dependency_graph_section`'s
    orphan sweep still renders it, flat, rather than silently dropping it.
    """
    roots: list[str] = []
    children: dict[str, list[str]] = {}
    for work_id in order:
        deps = deps_by_work.get(work_id) or []
        if not deps:
            roots.append(work_id)
        else:
            children.setdefault(deps[0], []).append(work_id)
    return roots, children


def _render_dependency_node(
    work_id: str,
    projection: DeliveryProjection,
    deps_by_work: Mapping[str, Sequence[str]],
    children: Mapping[str, Sequence[str]],
    visited: set[str],
) -> list[str]:
    """One dependency-tree node: the work's existing state chip (reused
    verbatim from `_state_chip` -- no new palette, no new judgment) plus
    its attempt count, an "unlocked by" annotation naming every recorded
    dep (not just the one it's indented under) when it has any, and its
    children nested underneath. `visited` guards against ever re-rendering
    (or infinite-looping on) a node twice -- defensive only, for a
    malformed/cyclic plan; a well-formed plan visits each work exactly
    once by construction."""
    visited.add(work_id)
    wp = projection.works.get(work_id)
    if wp is not None:
        head = _state_chip(work_id, wp)
        head += f' <span class="dep-attempts">attempts: {wp.attempt_number}</span>'
    else:
        # Defensive only: every plan-declared work_id gets a
        # FACT-WORK-CREATED immediately after FX-CREATE-WORK, so this
        # should be unreachable in practice -- never invent a chip for a
        # work the projection has no state for.
        head = f"<code>{html.escape(work_id)}</code>"
    parts = ['<li class="dep-node">', f'<div class="dep-node-head">{head}</div>']

    deps = deps_by_work.get(work_id) or []
    if deps:
        dep_list = ", ".join(f"<code>{html.escape(d)}</code>" for d in deps)
        parts.append(
            '<div class="dep-unlocked-by">unlocked by accepted completion of: '
            f"{dep_list}</div>"
        )

    child_ids = [c for c in children.get(work_id, ()) if c not in visited]
    if child_ids:
        parts.append('<ul class="dep-tree">')
        for child_id in child_ids:
            parts.extend(_render_dependency_node(child_id, projection, deps_by_work, children, visited))
        parts.append("</ul>")

    parts.append("</li>")
    return parts


def _render_dependency_graph_section(
    history: Sequence[Mapping[str, Any]], projection: DeliveryProjection
) -> str:
    """"Dependency graph" section (issue #41): an indented nested list,
    roots first, ordered purely by the recorded plan's own depth/edges --
    reusing this module's existing chip/escape/section machinery, never
    computing a health/ordering judgment the plan itself doesn't carry.

    Two distinct degradation shapes, deliberately different:

    - A journal with no `FX-CREATE-WORK` plan record at all (shouldn't
      happen post-#44, but an old or foreign journal might lack one,
      `CONTRACT-DURABILITY`) -- the section is omitted, but with a small
      visible note, because this journal *should* have had a topology and
      didn't: that is worth surfacing to the reader, not silently hiding.
    - A single-work run (plan has 0 or 1 declared works, the common case
      -- `orc_werk.app.default_single_work_plan()`) -- omitted entirely,
      no note at all: a one-node "tree" is noise, and there is nothing
      degraded about a single-work run lacking a topology to show.
    """
    plan = _find_create_work_plan(history)
    if plan is None:
        return (
            '<p class="meta-line muted">dependency graph: unavailable -- '
            "no FX-CREATE-WORK plan recorded in this journal (pre-topology-durability "
            "or a foreign journal)</p>"
        )

    order, deps_by_work = _plan_topology(plan)
    if len(order) <= 1:
        return ""

    roots, children = _build_dependency_tree(order, deps_by_work)
    visited: set[str] = set()
    parts = [
        '<section class="dependency-graph"><h2>Dependency graph</h2>',
        '<ul class="dep-tree dep-tree-root">',
    ]
    for root_id in roots:
        if root_id not in visited:
            parts.extend(_render_dependency_node(root_id, projection, deps_by_work, children, visited))
    # Defensive orphan sweep: a work never reached from a root (a dangling
    # first-blocker reference, or a cycle, in a malformed plan) still
    # renders -- flat, at the top level -- rather than silently vanishing.
    # This never invents a placement for it beyond "shown somewhere".
    for work_id in order:
        if work_id not in visited:
            parts.extend(_render_dependency_node(work_id, projection, deps_by_work, children, visited))
    parts.append("</ul></section>")
    return "\n".join(parts)


def _summarize_states(projection: DeliveryProjection) -> tuple[bool, bool]:
    any_blocked = False
    any_non_accepted = False
    for wp in projection.works.values():
        if wp.state == STATE_BLOCKED:
            any_blocked = True
        if wp.state != STATE_ACCEPTED:
            any_non_accepted = True
    return any_blocked, any_non_accepted


# ---------------------------------------------------------------------------
# Rendering: run report
# ---------------------------------------------------------------------------


def _render_basis_citation(item: Mapping[str, Any], seq_index: Mapping[tuple[str, str], int]) -> str:
    """`DEC-*`'s `basis` visibly linked to the fact(s) it cites (task
    card): when the cited fact snapshot matches a record already in this
    run's `seq`-ordered history, link to it in-page; otherwise render the
    quoted id+data inline (still a citation, just not one this run's
    history can anchor)."""
    fact_id = item.get("id", "")
    data = item.get("data", {})
    key = (fact_id, _compact_json(data))
    seq = seq_index.get(key)
    if seq is not None:
        return (
            f'<a class="citation" href="#seq-{seq:04d}">'
            f"cites [{seq:04d}] {html.escape(fact_id)}</a>"
        )
    return (
        f'<span class="citation citation-unlinked">cites {html.escape(fact_id)} '
        f"{_esc_json(data)}</span>"
    )


def _render_timeline_record(
    record: Mapping[str, Any],
    seq_index: Mapping[tuple[str, str], int],
    times: Mapping[int, str] = {},
) -> str:
    seq = record.get("seq", 0)
    kind = record.get("kind", "")
    record_id = record.get("id", "")
    parts = [f'<li id="seq-{seq:04d}" class="record record-{html.escape(kind)}">']
    observed_at = times.get(seq)
    time_span = (
        f' <span class="record-time">{html.escape(observed_at)}</span>' if observed_at else ""
    )
    parts.append(
        '<div class="record-head">'
        f'<span class="record-seq">[{seq:04d}]</span> '
        f'<span class="record-kind">{html.escape(kind)}</span> '
        f'<span class="record-id">{html.escape(record_id)}</span>'
        f"{time_span}"
        "</div>"
    )
    if kind == "decision":
        basis = record.get("data", {}).get("basis") or []
        if basis:
            parts.append('<div class="basis"><span class="basis-label">basis</span><ul>')
            for item in basis:
                if isinstance(item, Mapping):
                    parts.append(f"<li>{_render_basis_citation(item, seq_index)}</li>")
            parts.append("</ul></div>")
    parts.append(
        f'<div class="scroll"><pre class="record-data">{html.escape(_compact_json(record.get("data", {})))}</pre></div>'
    )
    extensions = record.get("extensions")
    if extensions:
        parts.append(
            '<div class="scroll"><pre class="record-extensions">extensions: '
            f'{html.escape(_compact_json(extensions))}</pre></div>'
        )
    parts.append("</li>")
    return "\n".join(parts)


def _render_candidates_table(history: Sequence[Mapping[str, Any]], work_id: str, wp: WorkProjection) -> str:
    if not wp.candidates:
        return ""
    subject_identities = _candidate_subject_identities(history, work_id)
    rows = []
    for candidate_id, candidate in wp.candidates.items():
        subject_identity = subject_identities.get(candidate_id)
        subject_text = _esc_json(subject_identity) if subject_identity is not None else "-"
        rows.append(
            "<tr>"
            f'<td><code>{html.escape(candidate_id)}</code></td>'
            f'<td><code>{html.escape(str(candidate.get("fingerprint", "")))}</code></td>'
            f'<td><code>{html.escape(str(candidate.get("execution_id", "")))}</code></td>'
            f"<td>{subject_text}</td>"
            "</tr>"
        )
    return (
        "<h3>Candidates</h3>"
        '<div class="scroll"><table class="data-table"><thead><tr>'
        "<th>candidate_id</th><th>fingerprint</th><th>execution_id</th><th>subject_identity</th>"
        "</tr></thead><tbody>" + "\n".join(rows) + "</tbody></table></div>"
    )


def _render_verdicts_table(history: Sequence[Mapping[str, Any]], work_id: str, wp: WorkProjection) -> str:
    if not wp.assurances:
        return ""
    rows = []
    for assurance in wp.assurances:
        verdict = assurance.get("verdict")
        evidence_refs = _verdict_evidence_refs(history, work_id, assurance.get("assurance_id"))
        evidence_text = _esc_json(evidence_refs) if evidence_refs else "-"
        if verdict:
            verdict_cell = _chip(verdict, _VERDICT_STATUS.get(verdict, "neutral"))
        else:
            verdict_cell = '<span class="muted">pending</span>'
        rows.append(
            "<tr>"
            f'<td><code>{html.escape(str(assurance.get("assurance_id", "")))}</code></td>'
            f'<td><code>{html.escape(str(assurance.get("candidate_id", "")))}</code></td>'
            f"<td>{verdict_cell}</td>"
            f"<td>{evidence_text}</td>"
            "</tr>"
        )
    return (
        "<h3>Assurance verdicts</h3>"
        '<div class="scroll"><table class="data-table"><thead><tr>'
        "<th>assurance_id</th><th>candidate_id</th><th>verdict</th><th>evidence_refs</th>"
        "</tr></thead><tbody>" + "\n".join(rows) + "</tbody></table></div>"
    )


def _render_work_section(
    work_id: str,
    wp: WorkProjection,
    history: Sequence[Mapping[str, Any]],
    seq_index: Mapping[tuple[str, str], int],
    times: Mapping[int, str] = {},
) -> str:
    status = _STATE_STATUS.get(wp.state, "neutral")
    parts = [f'<section class="work" id="work-{html.escape(work_id)}">']
    parts.append(f"<h2>Work {html.escape(work_id)} {_chip(wp.state, status)}</h2>")
    parts.append(f'<p class="meta-line">attempts: {wp.attempt_number}</p>')

    if wp.blocked_reason:
        root_cause = _root_cause_for_work(history, work_id)
        detail = f"blocked_reason={html.escape(wp.blocked_reason)}"
        if root_cause:
            detail += f" (root_cause={html.escape(root_cause)})"
        parts.append(
            '<div class="callout callout-critical">'
            '<span class="callout-icon" aria-hidden="true">✕</span>'
            f"<span><strong>Blocked</strong> — {detail}</span></div>"
        )

    if is_pending(wp):
        awaiting = _awaiting_label(wp)
        parts.append(
            '<div class="callout callout-warning">'
            '<span class="callout-icon" aria-hidden="true">⏳</span>'
            f"<span><strong>Pending</strong> — awaiting {html.escape(awaiting)}, "
            f"attempt {wp.attempt_number}</span></div>"
        )

    parts.append(_render_candidates_table(history, work_id, wp))
    parts.append(_render_verdicts_table(history, work_id, wp))

    parts.append("<h3>Timeline</h3>")
    parts.append('<ol class="timeline">')
    for record in history:
        if _work_id_of(record) != work_id:
            continue
        parts.append(_render_timeline_record(record, seq_index, times))
    parts.append("</ol>")

    parts.append("</section>")
    return "\n".join(part for part in parts if part)


def _render_run_level_section(
    history: Sequence[Mapping[str, Any]], times: Mapping[int, str] = {}
) -> str:
    records = [r for r in history if _work_id_of(r) is None]
    if not records:
        return ""
    seq_index = _fact_seq_index(history)
    parts = ['<section class="run-level"><h2>Run-level records</h2><ol class="timeline">']
    for record in records:
        parts.append(_render_timeline_record(record, seq_index, times))
    parts.append("</ol></section>")
    return "\n".join(parts)


def _render_run_header(
    run_id: str,
    intent_text: Optional[str],
    projection: DeliveryProjection,
    times: Mapping[int, str] = {},
    skipped_times: int = 0,
) -> str:
    parts = ['<header class="run-header">']
    parts.append(f"<h1>orc report — {html.escape(run_id)}</h1>")
    if intent_text is not None:
        parts.append(f'<div class="intent-text">{html.escape(intent_text)}</div>')
    else:
        parts.append('<div class="intent-text muted">(no intent text recorded)</div>')
    parts.append(f'<p class="meta-line">run: <code>{html.escape(run_id)}</code></p>')

    if times:
        # Lexicographic min/max is correct here: _observed_at_now's fixed
        # "%Y-%m-%dT%H:%M:%S.%fZ" format is zero-padded/fixed-width in
        # every field, so string ordering matches chronological ordering.
        started = min(times.values())
        last_activity = max(times.values())
        parts.append(
            '<p class="meta-line">observed: started '
            f"<code>{html.escape(started)}</code> &middot; last activity "
            f"<code>{html.escape(last_activity)}</code></p>"
        )
    if skipped_times:
        parts.append(
            '<p class="meta-line muted">times: '
            f"{skipped_times} corrupt sidecar record(s) skipped</p>"
        )

    if projection.works:
        any_blocked, any_non_accepted = _summarize_states(projection)
        if any_blocked:
            disposition, dstatus = "blocked", "critical"
        elif any_non_accepted:
            disposition, dstatus = "in progress", "warning"
        else:
            disposition, dstatus = "accepted", "good"
        parts.append(f'<p class="meta-line">exit disposition: {_chip(disposition, dstatus)}</p>')
        chips = " ".join(_state_chip(wid, wp) for wid, wp in sorted(projection.works.items()))
        parts.append(f'<p class="meta-line">works: {chips}</p>')
    else:
        parts.append('<p class="meta-line">(no work recorded yet)</p>')
    parts.append("</header>")
    return "\n".join(parts)


def render_run_report(directory: Path, run_id: str) -> str:
    """Render one DeliveryRun's journal into a self-contained HTML
    document. Raises canonical `ERR-NOT-FOUND` (via `_require_journal_file`)
    for a missing run, checked before any adapter is constructed -- no side
    effect on a failed lookup."""
    _require_journal_file(directory, run_id, target=run_id)
    journal = JSONLJournal(directory)
    history = journal.history(delivery_run_id=run_id)
    projection = journal.load_projection(delivery_run_id=run_id)
    times, skipped_times = _load_times_sidecar(directory, run_id)

    intent_text = _intent_text(history)
    seq_index = _fact_seq_index(history)

    body_parts = [_render_run_header(run_id, intent_text, projection, times, skipped_times)]
    body_parts.append(_render_run_level_section(history, times))
    body_parts.append(_render_dependency_graph_section(history, projection))
    for work_id in sorted(projection.works):
        body_parts.append(
            _render_work_section(
                work_id,
                projection.works[work_id],
                history,
                seq_index,
                times,
            )
        )

    body = "\n".join(part for part in body_parts if part)
    return _PAGE_TEMPLATE.format(
        title=html.escape(f"orc report — {run_id}"), css=_CSS, body=body
    )


# ---------------------------------------------------------------------------
# Rendering: index
# ---------------------------------------------------------------------------


def _render_index_row(
    run_id: str, history: Sequence[Mapping[str, Any]], projection: DeliveryProjection, *, href: str
) -> str:
    intent_text = _intent_text(history) or ""
    if projection.works:
        chips = " ".join(_state_chip(wid, wp) for wid, wp in sorted(projection.works.items()))
        attempts = ", ".join(
            f"{html.escape(wid)}: {wp.attempt_number}" for wid, wp in sorted(projection.works.items())
        )
    else:
        chips = '<span class="muted">(no work)</span>'
        attempts = "-"
    return (
        "<tr>"
        f'<td><code>{html.escape(run_id)}</code></td>'
        f"<td>{html.escape(intent_text)}</td>"
        f"<td>{chips}</td>"
        f"<td>{attempts}</td>"
        f'<td><a href="{html.escape(href)}">{html.escape(href)}</a></td>'
        "</tr>"
    )


def _render_unreadable_index_row(run_id: str, exc: CoreError) -> str:
    error_code = str(exc.error.get("error", "ERR-UNKNOWN"))
    affordance = f"see orc status {run_id}"
    return (
        "<tr>"
        f'<td><code>{html.escape(run_id)}</code></td>'
        f'<td><span class="muted">(unreadable)</span></td>'
        f"<td>{_chip(error_code, 'critical')}</td>"
        "<td>-</td>"
        f"<td>{html.escape(affordance)}</td>"
        "</tr>"
    )


def _render_index_table(rows: Sequence[str], *, empty_message: str) -> str:
    if not rows:
        return f'<p class="meta-line">{html.escape(empty_message)}</p>'
    return (
        '<div class="scroll"><table class="index-table"><thead><tr>'
        "<th>run</th><th>intent</th><th>works</th><th>attempts</th><th>report</th>"
        "</tr></thead><tbody>" + "\n".join(rows) + "</tbody></table></div>"
    )


def discover_run_ids(directory: Path, *, match: str = "*") -> list[str]:
    """Run ids under `directory` whose id `fnmatch`es `match` (`--all`/
    `--match`, issue #40), sorted. Strictly read-only: only lists
    `directory`'s entries, never opens or writes anything. Built on
    `orc_werk.cli.journal_reading._available_run_ids` (issue #43), the same
    sidecar-filtering run-id listing the ERR-NOT-FOUND(run) affordance and
    the bare-`orc` index also use, so all three call sites agree on what
    counts as "a run"."""
    return [run_id for run_id in _available_run_ids(directory) if fnmatch.fnmatch(run_id, match)]


def render_index(
    directory: Path, *, run_ids: Optional[Sequence[str]] = None, flat_hrefs: bool = False
) -> str:
    """Render a small local index page over `directory`'s run journals.
    `run_ids`, when given, scopes the index to exactly that set (in the
    order given) instead of discovering every run under `directory` --
    used by `render_all`'s scoped index (issue #40). Strictly read-only
    over the journal directory: it only ever reads `history`/
    `load_projection` for each listed run, never writes anything but its
    own announced output file.

    `flat_hrefs` (issue #55 H1): `render_all` always writes its per-run
    report files flat as `<out_dir>/<run_id>.report.html` regardless of
    that run's own journal layout (`--all`'s output directory need not
    even be a journal directory at all) -- pass `True` from there so this
    index's links match what it actually wrote. The plain `--index` case
    (this function's own default, `False`) instead links to wherever `orc
    report <run_id>` would itself write by default -- `layout.
    report_html_path`, layout-aware -- since no `--all` render has
    necessarily happened yet."""
    if not directory.is_dir():
        raise not_found_error(
            f"journal directory does not exist: {directory}", path=str(directory)
        )
    journal = JSONLJournal(directory)
    scoped = run_ids is not None
    ids = list(run_ids) if scoped else discover_run_ids(directory)
    rows = []
    for run_id in ids:
        if flat_hrefs:
            href = f"{run_id}.report.html"
        else:
            href = layout.report_html_path(directory, run_id).relative_to(directory).as_posix()
        try:
            history = journal.history(delivery_run_id=run_id)
            projection = journal.load_projection(delivery_run_id=run_id)
        except CoreError as exc:
            # Portfolio views degrade per run: one replay defect must remain
            # visible without poisoning every healthy run's report (#78).
            rows.append(_render_unreadable_index_row(run_id, exc))
            continue
        rows.append(_render_index_row(run_id, history, projection, href=href))
    empty_message = (
        "(no runs matched this filter)" if scoped else "(no runs found under this journal directory)"
    )
    table = _render_index_table(rows, empty_message=empty_message)

    body = (
        '<header class="run-header">'
        f"<h1>orc report index — {html.escape(str(directory))}</h1>"
        "</header>" + table
    )
    return _PAGE_TEMPLATE.format(title=html.escape("orc report index"), css=_CSS, body=body)


def render_all(directory: Path, *, match: str, out_dir: Path) -> tuple[list[tuple[str, Path]], Path]:
    """Render every run under `directory` whose run_id `fnmatch`es `match`
    (`--all`/`--match`, issue #40; `match` default `'*'` renders every
    run) to its own `<out_dir>/<run_id>.report.html`, plus one scoped
    `<out_dir>/index.html` over exactly that matched set. Read-only over
    `directory` except the announced outputs under `out_dir` (created if
    missing, since it is itself an announced output location -- mirrors
    `--out`'s existing single-run behavior of writing wherever asked).
    Missing `directory` -> canonical `ERR-NOT-FOUND`, checked before
    `out_dir` is ever touched -- an unmatched/bad `--journal` must not
    leave a stray `--out-dir` behind."""
    if not directory.is_dir():
        raise not_found_error(
            f"journal directory does not exist: {directory}", path=str(directory)
        )
    run_ids = discover_run_ids(directory, match=match)

    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[tuple[str, Path]] = []
    unreadable_run_ids: list[str] = []
    for run_id in run_ids:
        try:
            html_text = render_run_report(directory, run_id)
        except CoreError:
            unreadable_run_ids.append(run_id)
            continue
        out_path = out_dir / f"{run_id}.report.html"
        out_path.write_text(html_text, encoding="utf-8")
        outputs.append((run_id, out_path))

    # The scoped index replays every matched id in discovery order; this
    # includes the failures recorded above, which become critical rows.
    index_html = render_index(directory, run_ids=run_ids, flat_hrefs=True)
    index_path = out_dir / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    return outputs, index_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _resolve_report_target(run_arg: str, journal_arg: Optional[str]) -> tuple[Path, str]:
    """`--journal DIR` explicitly given: `run_arg` is a bare run id under
    that directory. Otherwise fall back to the same flexible target
    resolution `status`/`history` use (`_resolve_journal`): a
    `<run_id>.jsonl` path, a directory containing exactly one journal, or a
    bare run id under the default `./.orc`."""
    if journal_arg is not None:
        return Path(journal_arg), run_arg
    return _resolve_journal(run_arg)


def cmd_report(args: argparse.Namespace) -> int:
    if args.all:
        if args.run:
            raise validation_error(
                "orc report --all does not take a positional run argument", run=args.run
            )
        if args.index:
            raise validation_error("orc report --all cannot be combined with --index")
        if args.out:
            raise validation_error("orc report --all uses --out-dir, not --out")
        directory = resolve_journal_dir(args.journal)
        out_dir = Path(args.out_dir) if args.out_dir else directory
        match = args.match if args.match is not None else "*"
        outputs, index_path = render_all(directory, match=match, out_dir=out_dir)
        for _run_id, out_path in outputs:
            print(f"report: {hyperlink_path(out_path.resolve())}")
        print(f"report: {hyperlink_path(index_path.resolve())}")
        return 0

    if args.match is not None:
        raise validation_error("orc report --match requires --all")
    if args.out_dir is not None:
        raise validation_error("orc report --out-dir requires --all")

    if args.index:
        if args.run:
            raise validation_error(
                "orc report --index does not take a positional run argument", run=args.run
            )
        directory = resolve_journal_dir(args.journal)
        html_text = render_index(directory)
        out_path = Path(args.out) if args.out else directory / "index.html"
        out_path.write_text(html_text, encoding="utf-8")
        print(f"report: {hyperlink_path(out_path.resolve())}")
        return 0

    if not args.run:
        raise validation_error("orc report requires a run id/path positional argument, or --index/--all")

    directory, run_id = _resolve_report_target(args.run, args.journal)
    html_text = render_run_report(directory, run_id)
    # issue #55 H1: default single-run output lands inside the run's own
    # new-layout directory (`<journal-dir>/<run_id>/report.html`); a
    # legacy-layout run keeps its pre-#55 flat default.
    out_path = Path(args.out) if args.out else layout.report_html_path(directory, run_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text, encoding="utf-8")
    print(f"report: {hyperlink_path(out_path.resolve())}")
    return 0


# ---------------------------------------------------------------------------
# Page shell + CSS (dataviz skill palette: light/dark chart chrome & ink
# tokens, status palette fixed across themes; inline only, no external
# requests, `prefers-color-scheme` for dark mode).
# ---------------------------------------------------------------------------

_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<main class="report">
{body}
</main>
<footer class="report-footer">Static snapshot rendered by <code>orc report</code> from the journal on disk -- not a live view; re-run to refresh.</footer>
</body>
</html>
"""

_CSS = """
:root {
  color-scheme: light dark;
  --page: #f9f9f7;
  --surface: #fcfcfb;
  --surface-2: #ffffff;
  --ink-primary: #0b0b0b;
  --ink-secondary: #52514e;
  --ink-muted: #898781;
  --border: rgba(11,11,11,0.10);
  --gridline: #e1e0d9;
  --good: #0ca30c;
  --warning: #fab219;
  --serious: #ec835a;
  --critical: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root {
    --page: #0d0d0d;
    --surface: #1a1a19;
    --surface-2: #202020;
    --ink-primary: #ffffff;
    --ink-secondary: #c3c2b7;
    --ink-muted: #898781;
    --border: rgba(255,255,255,0.10);
    --gridline: #2c2c2a;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 2rem 1.25rem 3rem;
  background: var(--page);
  color: var(--ink-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.5;
}
.report { max-width: 960px; margin: 0 auto; }
h1 { font-size: 1.4rem; margin: 0 0 0.75rem; }
h2 { font-size: 1.1rem; margin-top: 2.25rem; border-bottom: 1px solid var(--gridline); padding-bottom: 0.4rem; }
h3 { font-size: 0.9rem; color: var(--ink-secondary); margin-top: 1.5rem; text-transform: uppercase; letter-spacing: 0.04em; }
.run-header { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem 1.5rem; }
.intent-text { white-space: pre-wrap; word-break: break-word; font-size: 1.05rem; }
.intent-text.muted { color: var(--ink-muted); font-style: italic; }
.meta-line { color: var(--ink-secondary); font-size: 0.9rem; margin: 0.3rem 0; }
.muted { color: var(--ink-muted); }
.scroll { overflow-x: auto; }
table.data-table, table.index-table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
table.data-table th, table.data-table td,
table.index-table th, table.index-table td {
  text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid var(--gridline); vertical-align: top;
}
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.82em; }
pre.record-data, pre.record-extensions {
  background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  padding: 0.5rem 0.75rem; margin: 0.35rem 0 0; white-space: pre-wrap; word-break: break-word;
}
.chip {
  display: inline-flex; align-items: center; gap: 0.35em; padding: 0.15em 0.65em;
  border-radius: 999px; border: 1px solid var(--border); background: var(--surface-2);
  color: var(--ink-primary); font-size: 0.82em; font-weight: 600;
}
.chip-icon { display: inline-block; }
.chip-good .chip-icon { color: var(--good); }
.chip-warning .chip-icon { color: var(--warning); }
.chip-critical .chip-icon { color: var(--critical); }
.chip-serious .chip-icon { color: var(--serious); }
.chip-neutral .chip-icon { color: var(--ink-muted); }
.callout {
  display: flex; gap: 0.5em; align-items: baseline; border-radius: 8px;
  padding: 0.6em 0.9em; margin: 0.75rem 0; border: 1px solid var(--border); background: var(--surface);
}
.callout-warning .callout-icon { color: var(--warning); }
.callout-critical .callout-icon { color: var(--critical); }
.timeline { list-style: none; margin: 0.5rem 0 0; padding: 0; }
.timeline > li.record {
  padding: 0.5rem 0 0.5rem 1rem; margin: 0 0 0.15rem; border-left: 3px solid var(--gridline);
}
.timeline > li.record-fact { border-left-color: var(--ink-muted); }
.timeline > li.record-decision { border-left-color: var(--warning); }
.timeline > li.record-effect { border-left-color: var(--ink-secondary); }
.record-head { font-weight: 600; font-size: 0.88rem; }
.record-seq { color: var(--ink-muted); font-variant-numeric: tabular-nums; }
.record-time { color: var(--ink-muted); font-size: 0.82em; font-variant-numeric: tabular-nums; }
.basis { margin: 0.3rem 0 0; font-size: 0.85rem; }
.basis-label { color: var(--ink-muted); text-transform: uppercase; font-size: 0.7em; letter-spacing: 0.06em; }
.basis ul { margin: 0.15rem 0 0; padding-left: 1.1rem; }
.citation { color: var(--ink-secondary); }
a.citation { color: var(--ink-primary); text-decoration: underline; text-decoration-color: var(--ink-muted); }
.report-footer { max-width: 960px; margin: 2rem auto 0; color: var(--ink-muted); font-size: 0.8rem; text-align: center; }
ul.dep-tree { list-style: none; margin: 0.35rem 0 0; padding-left: 1.4rem; }
ul.dep-tree.dep-tree-root { padding-left: 0; }
li.dep-node { margin: 0.3rem 0; border-left: 2px solid var(--gridline); padding-left: 0.75rem; }
ul.dep-tree.dep-tree-root > li.dep-node { border-left: none; padding-left: 0; }
.dep-node-head { display: flex; align-items: center; gap: 0.5em; }
.dep-attempts { color: var(--ink-muted); font-size: 0.82em; }
.dep-unlocked-by { color: var(--ink-secondary); font-size: 0.82em; margin: 0.15rem 0 0; }
"""


__all__ = ["cmd_report", "discover_run_ids", "render_all", "render_index", "render_run_report"]
