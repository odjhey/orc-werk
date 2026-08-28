"""`orc refs` (GitHub issue #100 part 1): a pure, read-only projection over
one run's already-journaled state, listing every resolvable reference the
run carries with a runnable resolve command for each -- no new recording,
no new storage, nothing this command journals or persists itself.

This is the CLI-side instance of the reference-first narrative doctrine
(issue #65's operator "RULING AMENDED" comment): narrative/report *content*
stays provider-owned; the ledger journals a durable, resolvable
*reference* to it. `CONTRACT-DURABILITY`'s disposition sentence states the
same rule generically -- "narrative/report content is provider-owned and
the ledger journals resolvable references; sidecar extensions are the
fallback where no provider-native store exists, with `execution-session/v1`
and `EXT-CREW-REPORT-V1` as instances" -- and names `execution-session/v1`
(`EXT-EXECUTION-SESSION-V1-SCHEMA`, `docs/extensions/execution-session/`)
as the reference instance this command's first source walks. This module
adds no new normative semantics of its own; it composes exactly the same
public `JournalPort` reads (`history`, and this run's persisted dispatch
config) `orc status`/`orc report` already use.

Four independently optional sources, walked in this order, each rendered
only when present -- absence is never fabricated (`CLAUDE.md` #3):

1. `execution-session/v1` payloads carried on `FACT-EXEC-SETTLED`'s
   `extensions` (one settlement per execution): a `session` row for
   `native_session_id` (resolve: the provider's own inspection tool form,
   derived conservatively from the opaque `provider` string -- e.g.
   `acpx-pi` yields `acpx pi sessions history <ref>`, per
   `docs/adapters/acp/mapping.md`'s `provider` field convention; an
   unrecognized provider string renders the ref with resolve `-`, never a
   guessed command); a `resume` row for `resume.ref` (no adapter-neutral
   resolve command is defined for this schema field, so resolve is always
   `-`); a `transcript` row for `transcript_ref` (resolve: `cat
   <transcript_ref>` -- `EXT-EXECUTION-SESSION-V1-SCHEMA`'s ref-only rule
   guarantees this is an opaque reference the schema documents as
   typically an absolute path, so `cat` works from any cwd).
2. `FACT-ASSURE-SETTLED`'s `evidence_refs` (`docs/protocol/facts.md`,
   `PROTOCOL-FACTS`): one `evidence` row per entry, value rendered
   verbatim. When an entry is a structured (mapping) reference carrying an
   explicit command-ish field -- literally named `command`, or any key
   ending in `_command` (`docs/adapters/no-mistakes/mapping.md`'s
   `evidence_refs` shape documents both `command` and, for a
   step-scoped entry, the more specific `logs_command`, which wins when
   both are present) -- that field's value becomes the row's resolve
   command. A plain string entry, or a structured entry with no such
   field, renders with resolve `-`. This is a structural (naming-
   convention) match, never an allowlist of specific known provider
   shapes: an unregistered future provider's evidence entry, or an
   unrecognized field inside a known one, passes through unchanged
   (`CONF-EXT-002`-style tolerance, applied to this CLI-owned projection).
3. Candidate identity, read the same way `orc report` already does
   (`orc_werk.cli.report._candidate_subject_identities`'s sibling
   read -- this module's own `_candidate_subject_identities` walks the
   same journaled `FX-IDENTIFY-CANDIDATE` effect records
   `FACT-CANDIDATE-OBSERVED` itself does not carry the subject identity
   for): a `candidate` row for `head_sha`/`repo_path` when at least
   `head_sha` is present (resolve: `git -C <repo_path> show <head_sha>
   --stat`, only constructible when both fields are present -- `head_sha`
   alone renders with resolve `-`), and a `candidate-pr` row for `pr` when
   present (resolve: `gh pr view <pr>`, unconditionally -- PR #104's
   verifier recommendation, folded into issue #94: this now matches
   `orc_werk.cli.affordances`'s own unconditional `gh pr view <pr>`
   precedent for the `ACCEPTED` state's `next:` block, rather than gating
   on a same-`subject_identity` repo/URL-shaped sibling field that a real
   candidate need not carry). `subject_identity` is adapter-owned and
   opaque (`PORT-CANDIDATE`); these three field names are the ones this
   command was asked to surface, not a claim that every candidate carries
   them.
4. The Beads mirror block, read from the run's own persisted dispatch
   config (`<journal-dir>/<run_id>/config.json`, issue #55 H2's
   `_persist_effective_config`) when both the file and its `mirror` key
   exist: one `mirror` row naming the run label + workspace (resolve:
   `bd --json -C <workspace> list --label run:<run_id>`, matching
   `docs/adapters/beads/mapping.md`'s `--label run:<run_id>` convention).
   The kernel itself never journals mirror configuration (`mirror` is a
   CLI-owned config block, `CONTRACT-DURABILITY`'s "delegated work
   specification" disposition), so this is the one source read from the
   config sidecar rather than the journal.

Every "resolve" value is a DISPLAY string only -- this command never
shells out to anything (issue #65's ruling reserves an actual `--resolve`
execution flag for a later, separate task, with its own
may-break-on-provider-API-change caveat).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.jsonl import layout
from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.cli.journal_reading import _require_journal_file, _resolve_journal

FACT_EXEC_SETTLED = "FACT-EXEC-SETTLED"
FACT_ASSURE_SETTLED = "FACT-ASSURE-SETTLED"
FX_IDENTIFY_CANDIDATE = "FX-IDENTIFY-CANDIDATE"
EXECUTION_SESSION_V1 = "execution-session/v1"


@dataclass(frozen=True)
class RefRow:
    kind: str
    provider: str
    value: str
    resolve: str


def _display(value: Any) -> str:
    """Render a reference value verbatim: a plain string prints unchanged;
    anything else (a structured evidence_refs entry, a numeric `pr`, ...)
    prints as compact portable JSON -- never `str()`'d Python repr, per
    `CLAUDE.md` #9's "no language-specific shapes" posture applied to
    display text too."""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Source 1: execution-session/v1 (FACT-EXEC-SETTLED.extensions)
# ---------------------------------------------------------------------------

_ACPX_PROVIDER_PREFIX = "acpx-"


def _session_resolve(provider: Any, ref: str) -> str:
    """Conservative, `docs/adapters/acp/mapping.md`-derived tool form: a
    provider string exactly matching `acpx-<agent>` (the only convention
    any adapter in this codebase currently emits, `AcpExecution.
    _session_provenance`) yields `acpx <agent> sessions history <ref>`.
    Any other provider string -- including one merely resembling this
    convention -- renders with resolve `-` rather than a guessed command;
    inventing a tool form for an unrecognized provider would be exactly
    the kind of provider-specific guessing `CLAUDE.md` #6/#9 forbid a
    generic surface from doing."""
    if not isinstance(provider, str) or not provider.startswith(_ACPX_PROVIDER_PREFIX):
        return "-"
    agent = provider[len(_ACPX_PROVIDER_PREFIX) :]
    if not agent:
        return "-"
    return f"acpx {agent} sessions history {ref}"


def _execution_session_rows(history: Sequence[Mapping[str, Any]]) -> list[RefRow]:
    rows: list[RefRow] = []
    for record in history:
        if record.get("kind") != "fact" or record.get("id") != FACT_EXEC_SETTLED:
            continue
        extensions = record.get("extensions") or {}
        payload = extensions.get(EXECUTION_SESSION_V1)
        if not isinstance(payload, Mapping):
            continue
        provider = payload.get("provider")
        provider_display = provider if isinstance(provider, str) else "-"

        native_session_id = payload.get("native_session_id")
        if native_session_id is not None:
            ref_value = _display(native_session_id)
            rows.append(
                RefRow(
                    kind="session",
                    provider=provider_display,
                    value=ref_value,
                    resolve=_session_resolve(provider, ref_value),
                )
            )

        resume = payload.get("resume")
        if isinstance(resume, Mapping) and resume.get("ref") is not None:
            rows.append(
                RefRow(
                    kind="resume",
                    provider=provider_display,
                    value=_display(resume["ref"]),
                    resolve="-",
                )
            )

        transcript_ref = payload.get("transcript_ref")
        if transcript_ref is not None:
            transcript_display = _display(transcript_ref)
            rows.append(
                RefRow(
                    kind="transcript",
                    provider=provider_display,
                    value=transcript_display,
                    resolve=f"cat {transcript_display}",
                )
            )
    return rows


# ---------------------------------------------------------------------------
# Source 2: FACT-ASSURE-SETTLED.evidence_refs
# ---------------------------------------------------------------------------


def _command_field(entry: Mapping[str, Any]) -> Optional[str]:
    """Structural (naming-convention) detection of a command-ish field --
    never an allowlist of specific known provider field names. A key
    ending in `_command` (other than the bare `command` key itself) wins
    over the generic `command` field when both are present -- the
    no-mistakes adapter's step-scoped `evidence_refs` entry
    (`docs/adapters/no-mistakes/mapping.md`) carries both `command` (a
    status check) and `logs_command` (the fuller, more specific view once
    already settled), and the more specific one is the more useful resolve
    action once a verdict has already settled. Deterministic across
    multiple `_command`-suffixed fields via sorted key order."""
    generic: Optional[str] = None
    specific: Optional[str] = None
    for key in sorted(entry):
        value = entry.get(key)
        if not isinstance(value, str) or not value:
            continue
        if key == "command":
            generic = value
        elif key.endswith("_command") and specific is None:
            specific = value
    return specific if specific is not None else generic


def _evidence_ref_rows(history: Sequence[Mapping[str, Any]]) -> list[RefRow]:
    rows: list[RefRow] = []
    for record in history:
        if record.get("kind") != "fact" or record.get("id") != FACT_ASSURE_SETTLED:
            continue
        data = record.get("data", {})
        evidence_refs = data.get("evidence_refs")
        if not evidence_refs:
            continue
        for entry in evidence_refs:
            resolve = "-"
            if isinstance(entry, Mapping):
                command = _command_field(entry)
                if command is not None:
                    resolve = command
            rows.append(RefRow(kind="evidence", provider="-", value=_display(entry), resolve=resolve))
    return rows


# ---------------------------------------------------------------------------
# Source 3: candidate subject_identity (FX-IDENTIFY-CANDIDATE effect data)
# ---------------------------------------------------------------------------


def _candidate_rows(history: Sequence[Mapping[str, Any]]) -> list[RefRow]:
    rows: list[RefRow] = []
    for record in history:
        if record.get("kind") != "effect" or record.get("id") != FX_IDENTIFY_CANDIDATE:
            continue
        candidate = record.get("data", {}).get("dispatch_result", {}).get("candidate")
        if not isinstance(candidate, Mapping):
            continue
        subject_identity = candidate.get("subject_identity")
        if not isinstance(subject_identity, Mapping):
            continue

        head_sha = subject_identity.get("head_sha")
        if head_sha is not None:
            repo_path = subject_identity.get("repo_path")
            if repo_path is not None:
                value = _display({"head_sha": head_sha, "repo_path": repo_path})
                resolve = f"git -C {repo_path} show {head_sha} --stat"
            else:
                value = _display({"head_sha": head_sha})
                resolve = "-"
            rows.append(RefRow(kind="candidate", provider="-", value=value, resolve=resolve))

        pr = subject_identity.get("pr")
        if pr is not None:
            # issue #94 folded item / PR #104 verifier recommendation:
            # unconditional, matching orc_werk.cli.affordances._candidate_pr's
            # own unconditional `gh pr view <pr>` precedent for the
            # ACCEPTED-state next: block -- no repo-context gate.
            rows.append(RefRow(kind="candidate-pr", provider="-", value=_display(pr), resolve=f"gh pr view {pr}"))
    return rows


# ---------------------------------------------------------------------------
# Source 4: Beads mirror (persisted dispatch config)
# ---------------------------------------------------------------------------


def _load_persisted_config(directory: Path, run_id: str) -> Optional[Mapping[str, Any]]:
    """Best-effort read of the run's own persisted effective dispatch
    config (issue #55 H2, `orc_werk.cli.main._persist_effective_config`).
    Absent (never dispatched with a config, or a legacy run predating
    config persistence) or unreadable/malformed is not an error for this
    read-only projection -- it simply means source 4 contributes nothing,
    the same "silently absent, never fabricated" rule every other source
    here follows."""
    path = layout.config_path(directory, run_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, Mapping) else None


def _mirror_row(directory: Path, run_id: str) -> Optional[RefRow]:
    config = _load_persisted_config(directory, run_id)
    if config is None:
        return None
    mirror = config.get("mirror")
    if not isinstance(mirror, Mapping):
        return None
    workspace = mirror.get("workspace")
    if not isinstance(workspace, str) or not workspace:
        return None
    adapter = mirror.get("adapter", "beads") if isinstance(mirror.get("adapter", "beads"), str) else "beads"
    label = f"run:{run_id}"
    return RefRow(
        kind="mirror",
        provider=adapter,
        value=f"label={label} workspace={workspace}",
        resolve=f"bd --json -C {workspace} list --label {label}",
    )


# ---------------------------------------------------------------------------
# Collection + CLI entry point
# ---------------------------------------------------------------------------


def collect_refs(directory: Path, run_id: str, history: Sequence[Mapping[str, Any]]) -> list[RefRow]:
    """Every resolvable reference row for one run, in source order
    (execution-session -> evidence_refs -> candidate identity -> mirror).
    Pure: reads `history` (already loaded by the caller) plus this run's
    persisted config file; never writes anything."""
    rows: list[RefRow] = []
    rows.extend(_execution_session_rows(history))
    rows.extend(_evidence_ref_rows(history))
    rows.extend(_candidate_rows(history))
    mirror_row = _mirror_row(directory, run_id)
    if mirror_row is not None:
        rows.append(mirror_row)
    return rows


def _row_line(row: RefRow) -> str:
    return f"{row.kind:12s} {row.provider:16s} {row.value}  (resolve: {row.resolve})"


def cmd_refs(args: argparse.Namespace) -> int:
    directory, run_id = _resolve_journal(args.target, args.journal)
    _require_journal_file(directory, run_id, target=args.target)
    journal = JSONLJournal(directory)
    # `history()` reads raw envelopes only -- never replays through
    # `core/reducer.py`, so it cannot raise `ERR-CONFLICT` (only
    # `load_projection` can); nothing to enrich here (main.py's
    # `cmd_status`, report.py's `render_run_report`).
    history = journal.history(delivery_run_id=run_id)

    rows = collect_refs(directory, run_id, history)

    print(f"run: {run_id}")
    if not rows:
        # Definitive empty state (issue #43's "content first" convention,
        # applied here): never a bare blank line -- an exact count plus a
        # one-line pointer at the ordinary per-work status view, which
        # remains correct/informative even when this run has no
        # resolvable references at all yet (e.g. still pending, or every
        # source genuinely absent).
        print(f"0 refs for {run_id}")
        print("next:")
        print(f"  - orc status {run_id}")
        return 0

    for row in rows:
        print(_row_line(row))
    return 0


__all__ = ["RefRow", "cmd_refs", "collect_refs"]
