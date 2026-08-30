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
   `bd --json -C <workspace> list --label run:<run_id> --status all`, matching
   `docs/adapters/beads/mapping.md`'s `--label run:<run_id>` convention).
   The kernel itself never journals mirror configuration (`mirror` is a
   CLI-owned config block, `CONTRACT-DURABILITY`'s "delegated work
   specification" disposition), so this is the one source read from the
   config sidecar rather than the journal.

Every "resolve" value is, in the base `orc refs <run>` listing, a DISPLAY
string. `TASK-M3C-002` (`orc refs <run> --resolve <selector>` /
`--resolve-all`) adds actual execution on top of the exact same values --
"one vocabulary, what you see is what runs": every row's `ResolveCommand`
below carries both the display string AND (when the command passed the
read-only allowlist at construction) the argv `--resolve` executes, with
the display mechanically DERIVED from that argv rather than kept as a
hand-maintained second copy, so the two can never drift apart. See
`ResolveCommand`'s own docstring for the safety model.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.adapters.jsonl import layout
from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.cli.journal_reading import _require_journal_file, _resolve_journal
from orc_werk.core.errors import validation_error

FACT_EXEC_SETTLED = "FACT-EXEC-SETTLED"
FACT_ASSURE_SETTLED = "FACT-ASSURE-SETTLED"
FX_IDENTIFY_CANDIDATE = "FX-IDENTIFY-CANDIDATE"
EXECUTION_SESSION_V1 = "execution-session/v1"

# `--resolve`/`--resolve-all` execution bounds (TASK-M3C-002).
RESOLVE_TIMEOUT_S = 30.0
# ~8 KiB: large enough for a normal `git show --stat`/`bd list`/session-
# history page to render whole in the common case, small enough that a
# pathological transcript/log can't flood a terminal or an agent's context
# window -- the same "definitive truncation, escape hatch always named"
# posture `pagination.py`'s size_hint documents for listing surfaces,
# applied here to resolved *content* instead of row counts.
RESOLVE_OUTPUT_CAP_BYTES = 8192


# ---------------------------------------------------------------------------
# Per-tool read-only FLAG policy (TASK-M3C-002 fix round; verifier
# F-ALLOWLIST-FLAG-DEPTH-GENERAL). The first round vetted only the
# SUBCOMMAND and left every post-subcommand token free-form -- an
# arbitrary-file-WRITE hole: `git show --output=<path>` is a documented git
# write primitive that passed because its subcommand is `show`. The fix:
# every vetted tool declares exactly which flags may follow its subcommand;
# anything else -- notably writers/exec (`--output`/`-o`/`-O`, `--ext-diff`,
# `--textconv`) -- is refused. Journal content is attacker-influencable
# input (any executor agent that ever filled a seat wrote some of it), so
# EVERY argv token is treated as hostile: an unrecognized flag is refused,
# and a value-taking flag's value is consumed unparsed (never re-read as a
# flag). The authoritative policy narrative lives in
# `docs/playbooks/cli-usage.md`'s known-issues ledger; keep the two in sync
# when adding a tool.
#
# git show: read/render-only options only. Deliberately EXCLUDES every
# writer/exec option -- `--output`/`-o` (write to file), `-O` (order file),
# `--ext-diff`/`--textconv` (run external diff/textconv drivers). The
# top-level `-C`-only prefix rule already blocks `git -c <cfg>` (the
# `GIT_EXTERNAL_DIFF` config-exec vector), so config injection is out of
# reach before the subcommand too.
_GIT_SHOW_BOOL_FLAGS = frozenset(
    {
        "--stat",
        "--numstat",
        "--shortstat",
        "--summary",
        "--name-only",
        "--name-status",
        "--oneline",
        "--raw",
        "--patch",
        "-p",
        "--no-patch",
        "-s",
        "--no-color",
        "--color",
        "--no-textconv",
        "--no-ext-diff",
        "--no-renames",
        "--find-renames",
    }
)
_GIT_SHOW_VALUE_FLAGS: frozenset[str] = frozenset()  # none needed; keep the surface minimal

_ACPX_SESSIONS_BOOL_FLAGS = frozenset({"--json"})
_ACPX_SESSIONS_VALUE_FLAGS: frozenset[str] = frozenset()

# Audited against bd 1.2.2. Keep this surface minimal: `--json`, the
# builder's `--label`/`--status` filters, and `--no-pager` for deterministic
# non-interactive reads. Deliberately EXCLUDED (and therefore refused):
# `-w`/`--watch` (runs indefinitely; hang/resource-exhaustion), `--format`
# (Go-template/dot/digraph output control, not a read filter), `--db`
# (attacker-controlled database-path read redirection), `--actor` (audit-trail
# mutation shape), and `--global`/`--dolt-auto-commit`/`--ignore-schema-skew`
# (global database, write/commit, or schema-skew controls; not read-only).
_BD_BOOL_FLAGS = frozenset({"--json", "--no-pager"})
_BD_VALUE_FLAGS = frozenset({"--label", "--status"})

# no-mistakes axi status/logs: `--run`/`--step` take values; `--full`/
# `--json` are read-only booleans. `--follow` is intentionally EXCLUDED
# (refused) rather than merely timeout-contained -- streaming a live log
# against a settled verdict has no resolution value and would only burn the
# 30s execution cap; refusing it is instant and stricter.
_NOMISTAKES_BOOL_FLAGS = frozenset({"--full", "--json"})
_NOMISTAKES_VALUE_FLAGS = frozenset({"--run", "--step"})


def _vet_flags(
    rest: Sequence[str],
    *,
    tool_label: str,
    bool_flags: frozenset[str] = frozenset(),
    value_flags: frozenset[str] = frozenset(),
    min_positionals: int = 0,
    max_positionals: Optional[int] = None,
) -> Optional[str]:
    """Classify every token AFTER a vetted subcommand against that tool's
    flag policy. A token starting with `-` (including a bare `-`) must be
    an allowed boolean flag or an allowed value-taking flag -- otherwise
    REFUSED. A value-taking flag's value is consumed WITHOUT re-parsing
    (`--label <value>` or `--label=<value>`), so a value that itself looks
    like a flag can never be mistaken for one. A literal `--` ends option
    parsing: everything after it is a positional (this is how a genuinely
    `-`-leading positional would be passed safely, where a tool supports
    it). Returns `None` when safe, else a human-readable refusal reason."""
    positionals = 0
    i = 0
    n = len(rest)
    after_ddash = False
    while i < n:
        tok = rest[i]
        if not after_ddash and tok == "--":
            after_ddash = True
            i += 1
            continue
        if not after_ddash and tok.startswith("-"):
            name = tok.split("=", 1)[0]
            if name in value_flags:
                # `--flag=value` carries its value inline (one token);
                # `--flag value` consumes the next token unparsed.
                i += 1 if "=" in tok else 2
                continue
            if name in bool_flags:
                i += 1
                continue
            return f"{tool_label}: option {tok!r} is not in the read-only flag allowlist"
        positionals += 1
        i += 1
    if positionals < min_positionals:
        return f"{tool_label}: too few positional arguments ({positionals} < {min_positionals})"
    if max_positionals is not None and positionals > max_positionals:
        return f"{tool_label}: too many positional arguments ({positionals} > {max_positionals})"
    return None


def _vet_read_only(argv: Sequence[str]) -> Optional[str]:
    """The read-only allowlist `--resolve`/`--resolve-all` vet EVERY
    resolve command against at construction time, before it is ever offered
    for execution (the judge-only bar `docs/adapters/no-mistakes/
    mapping.md`'s "Judge-only ruling" sets for the assurance adapter,
    applied here to this CLI's own command construction). Returns `None`
    when `argv` is vetted-safe to execute; otherwise a human-readable
    refusal reason.

    Two levels, BOTH required (the first-round escape passed the first and
    skipped the second): (1) a hard tool+subcommand allowlist -- `cat`;
    `git [-C <path>] show`; `acpx <agent> sessions <history|show>`; `bd
    [--json] [-C <path>] <list|show>`; `no-mistakes axi <status|logs>`,
    nothing else; and (2) a per-tool FLAG policy over every token after the
    subcommand (`_vet_flags`), so a write/exec-shaped option like `git show
    --output=<path>` is refused even though its subcommand is allowed.
    Notably `gh pr view <pr>` (the `candidate-pr` row's display) is NOT in
    the allowlist at all (see the PR body's Ambiguities section) -- that row
    displays but never executes.

    Interpolated tool-position tokens are guarded too: the `acpx` agent
    (`argv[1]`, derived from an adapter-owned `provider` string) is refused
    if it begins with `-`, closing an agent-name flag-injection path
    analogous to the git head_sha one the candidate builder guards.

    This is a shape-based, bare-tool-name check (matching this codebase's
    existing conservative-derivation precedent, `_session_resolve`'s own
    docstring) -- a tool invoked via an absolute or relative path (e.g.
    `/usr/bin/git`) does not match any bare name here and is refused, a
    known limitation recorded in `docs/playbooks/cli-usage.md`'s known-
    issues ledger rather than silently over-trusted.
    """
    if not argv:
        return "empty command"
    tool = argv[0]
    if tool == "cat":
        # cat has no write/exec option at all; its only risk is a
        # `-`-leading token being read as an unknown flag -- refused by the
        # empty flag policy below -- and reading a file is exactly the
        # read-only action requested. Exactly one positional path.
        return _vet_flags(argv[1:], tool_label="cat", min_positionals=1, max_positionals=1)
    if tool == "git":
        rest = list(argv[1:])
        if rest[:1] == ["-C"]:
            if len(rest) < 2:
                return "git -C: missing path"
            rest = rest[2:]
        if not rest or rest[0] != "show":
            return "git: only the read-only 'show' subcommand is vetted"
        return _vet_flags(
            rest[1:],
            tool_label="git show",
            bool_flags=_GIT_SHOW_BOOL_FLAGS,
            value_flags=_GIT_SHOW_VALUE_FLAGS,
        )
    if tool == "acpx":
        if len(argv) < 4 or argv[2] != "sessions" or argv[3] not in ("history", "show"):
            return "acpx: only 'sessions history'/'sessions show' is vetted"
        if argv[1].startswith("-"):
            return "acpx: agent token begins with '-' (refused as possible flag injection)"
        return _vet_flags(
            argv[4:],
            tool_label=f"acpx sessions {argv[3]}",
            bool_flags=_ACPX_SESSIONS_BOOL_FLAGS,
            value_flags=_ACPX_SESSIONS_VALUE_FLAGS,
            max_positionals=1,
        )
    if tool == "bd":
        rest = list(argv[1:])
        if rest[:1] == ["--json"]:
            rest = rest[1:]
        if rest[:1] == ["-C"]:
            if len(rest) < 2:
                return "bd -C: missing workspace path"
            rest = rest[2:]
        if not rest or rest[0] not in ("list", "show"):
            return "bd: only 'list'/'show' is vetted"
        sub = rest[0]
        return _vet_flags(
            rest[1:],
            tool_label=f"bd {sub}",
            bool_flags=_BD_BOOL_FLAGS,
            value_flags=_BD_VALUE_FLAGS,
            max_positionals=1 if sub == "show" else 0,
        )
    if tool == "no-mistakes":
        if len(argv) < 3 or argv[1] != "axi" or argv[2] not in ("status", "logs"):
            return "no-mistakes: only 'axi status'/'axi logs' is vetted"
        return _vet_flags(
            argv[3:],
            tool_label=f"no-mistakes axi {argv[2]}",
            bool_flags=_NOMISTAKES_BOOL_FLAGS,
            value_flags=_NOMISTAKES_VALUE_FLAGS,
        )
    return f"tool {tool!r} is not in the vetted read-only allowlist"


@dataclass(frozen=True)
class ResolveCommand:
    """One row's resolve command: `display` is always the exact string
    shown in the `orc refs` listing; `argv` is that SAME command as a
    vetted-safe argv list ready to execute via `subprocess.run(argv, ...)`
    (never `shell=True`, never string-interpolated) -- or `None` when this
    resolve command cannot be executed by `--resolve`/`--resolve-all` (no
    command at all, or refused by `_vet_read_only`).

    `display` is ALWAYS rendered mechanically FROM `argv` (`" ".join`) when
    a candidate argv exists -- for a builder-constructed command (session,
    transcript, candidate, mirror, candidate-pr) this is the only argv
    that ever existed; for a journal-carried evidence `command`/
    `*_command` field (`from_raw_text`) the field's raw text is first
    parsed into argv and the display is regenerated from THAT argv, not
    kept as the original string, so a builder can never emit a display
    string that diverges from what `--resolve` would actually run.  A
    command that fails to parse into argv at all keeps its original raw
    text as `display` (there is no argv to derive it from) with `argv`
    left `None` -- the same "print the manual command, never execute it"
    degrade as a refused command.

    This is the single source `_row_line` (the listing) and `--resolve`/
    `--resolve-all` (execution) both read -- there is no second,
    independently-maintained command vocabulary anywhere in this module.
    """

    display: str
    argv: Optional[tuple[str, ...]]
    refusal: Optional[str] = None

    @staticmethod
    def none() -> "ResolveCommand":
        return ResolveCommand(display="-", argv=None)

    @staticmethod
    def of(argv: Sequence[str]) -> "ResolveCommand":
        """Vet a builder-constructed argv against the read-only allowlist
        and derive `display` from it."""
        argv_t = tuple(argv)
        display = " ".join(argv_t)
        reason = _vet_read_only(argv_t)
        if reason is not None:
            return ResolveCommand(display=display, argv=None, refusal=reason)
        return ResolveCommand(display=display, argv=argv_t)

    @staticmethod
    def from_raw_text(text: str) -> "ResolveCommand":
        """A resolve command supplied as free text by journal-derived DATA
        (an `evidence_refs` entry's `command`/`*_command` field) --
        attacker-influencable input (a journal), never trusted as
        executable merely because it looks command-shaped. Parsed into
        argv with `shlex.split` and vetted exactly like a builder-
        constructed command via `of`; text that fails to parse (malformed
        shell quoting) degrades the same way an unvetted tool does --
        `argv=None`, the original text preserved verbatim as `display`,
        never executed."""
        try:
            argv = shlex.split(text)
        except ValueError as exc:
            return ResolveCommand(display=text, argv=None, refusal=f"could not parse command text ({exc})")
        if not argv:
            return ResolveCommand(display=text, argv=None, refusal="empty command")
        return ResolveCommand.of(argv)


def _guarded_command(argv: Sequence[str], *, interpolated: Sequence[str], field_label: str) -> ResolveCommand:
    """Build a builder-constructed `ResolveCommand`, but refuse it at
    BUILD time (defense in depth, TASK-M3C-002 fix round) if any
    journal-derived `interpolated` token begins with `-`. Those tokens
    (a candidate `head_sha`/`repo_path`, an `acpx` agent name/session ref)
    are attacker-influencable, and a `-`-leading value could be read by the
    tool as an option -- e.g. `head_sha='--output=/tmp/x'` is a git write
    primitive. `_vet_read_only` would also refuse such a token, but the
    builder must never MINT one; this is the independent second guard the
    fix-round ruling requires. The display still shows the (refused)
    command so the operator sees exactly what would have run."""
    for token in interpolated:
        if token.startswith("-"):
            return ResolveCommand(
                display=" ".join(argv),
                argv=None,
                refusal=f"{field_label} begins with '-' (refused as possible flag injection)",
            )
    return ResolveCommand.of(argv)


@dataclass(frozen=True)
class RefRow:
    kind: str
    provider: str
    value: str
    resolve: ResolveCommand
    verdict: Optional[str] = None


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


def _session_resolve(provider: Any, ref: str) -> ResolveCommand:
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
        return ResolveCommand.none()
    agent = provider[len(_ACPX_PROVIDER_PREFIX) :]
    if not agent:
        return ResolveCommand.none()
    return _guarded_command(
        ["acpx", agent, "sessions", "history", ref],
        interpolated=(agent, ref),
        field_label="acpx agent/session ref",
    )


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
                    resolve=ResolveCommand.none(),
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
                    resolve=ResolveCommand.of(["cat", transcript_display]),
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
            resolve = ResolveCommand.none()
            if isinstance(entry, Mapping):
                command = _command_field(entry)
                if command is not None:
                    resolve = ResolveCommand.from_raw_text(command)
            rows.append(
                RefRow(
                    kind="evidence",
                    provider="-",
                    value=_display(entry),
                    resolve=resolve,
                    verdict=data.get("verdict") if isinstance(data.get("verdict"), str) else None,
                )
            )
    return rows


# ---------------------------------------------------------------------------
# Source 3: candidate subject_identity (FX-IDENTIFY-CANDIDATE effect data)
# ---------------------------------------------------------------------------


def _candidate_git_show(head_sha: str, repo_path: str) -> ResolveCommand:
    """`git -C <repo_path> show <head_sha> --stat`, with both interpolated
    identity fields guarded against `-`-leading flag injection at build
    time (TASK-M3C-002 fix round). A `--` separator cannot be used to
    protect `<head_sha>` here: `git show --stat -- <sha>` makes git read
    the sha as a PATHSPEC, not a revision (empirically verified), producing
    empty output -- so the guard is build-time rejection plus the per-tool
    flag policy in `_vet_read_only`, not positional separation."""
    return _guarded_command(
        ["git", "-C", repo_path, "show", head_sha, "--stat"],
        interpolated=(head_sha, repo_path),
        field_label="candidate identity field (head_sha/repo_path)",
    )


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
            identity = {"head_sha": head_sha}
            if subject_identity.get("branch") is not None:
                identity["branch"] = subject_identity["branch"]
            if repo_path is not None:
                identity["repo_path"] = repo_path
                value = _display(identity)
                resolve = _candidate_git_show(str(head_sha), str(repo_path))
            else:
                value = _display(identity)
                resolve = ResolveCommand.none()
            rows.append(RefRow(kind="candidate", provider="-", value=value, resolve=resolve))

        pr = subject_identity.get("pr")
        if pr is not None:
            # issue #94 folded item / PR #104 verifier recommendation:
            # unconditional, matching orc_werk.cli.affordances._candidate_pr's
            # own unconditional `gh pr view <pr>` precedent for the
            # ACCEPTED-state next: block -- no repo-context gate. `gh` is
            # not in TASK-M3C-002's execution allowlist (see
            # `_vet_read_only`'s docstring), so this row's resolve command
            # keeps displaying unchanged but never executes under
            # `--resolve`/`--resolve-all` -- refused, not silently dropped.
            rows.append(
                RefRow(
                    kind="candidate-pr",
                    provider="-",
                    value=_display(pr),
                    resolve=ResolveCommand.of(["gh", "pr", "view", str(pr)]),
                )
            )
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
        resolve=ResolveCommand.of(
            ["bd", "--json", "-C", workspace, "list", "--label", label, "--status", "all"]
        ),
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
    verdict = f" verdict={row.verdict}" if row.verdict is not None else ""
    return f"{row.kind:12s} {row.provider:16s} {row.value}{verdict}  (resolve: {row.resolve.display})"


# ---------------------------------------------------------------------------
# --resolve / --resolve-all (TASK-M3C-002)
# ---------------------------------------------------------------------------


def _select_row(rows: Sequence[RefRow], selector: str) -> tuple[int, RefRow]:
    """A selector is either the 1-based index exactly as printed by the
    plain listing (`[N]`, copy-able verbatim -- `orc refs <run> --resolve
    2`), or `<kind>[:<substring>]`: every row of that `kind`, optionally
    narrowed to rows whose `value` contains `<substring>` (case-sensitive),
    selected only when exactly one match remains. Ambiguous/absent
    selectors raise `ERR-VALIDATION` with a `next` pointer (issue #94's
    affordance rule extended to this command's own error surface) rather
    than guessing which ref was meant."""
    if selector.isdigit():
        index = int(selector)
        if index < 1 or index > len(rows):
            next_steps = (
                [f"orc refs <run> lists every valid index (1..{len(rows)})"]
                if rows
                else ["orc refs <run> lists 0 refs for this run"]
            )
            raise validation_error(
                f"selector {selector!r} is out of range (1..{len(rows)})",
                selector=selector,
                row_count=len(rows),
                next_steps=next_steps,
            )
        return index, rows[index - 1]

    kind, _, match = selector.partition(":")
    candidates = [
        (index, row) for index, row in enumerate(rows, start=1) if row.kind == kind and (not match or match in row.value)
    ]
    if not candidates:
        raise validation_error(
            f"no ref matches selector {selector!r}",
            selector=selector,
            next_steps=["orc refs <run> lists every ref's index and kind"],
        )
    if len(candidates) > 1:
        matches = ", ".join(f"[{index}]" for index, _ in candidates)
        raise validation_error(
            f"selector {selector!r} matches {len(candidates)} refs ({matches})",
            selector=selector,
            next_steps=[
                f"use the index directly, e.g. orc refs <run> --resolve {candidates[0][0]}",
                "or narrow with '<kind>:<substring>' against the listed value",
            ],
        )
    return candidates[0]


def _execute_resolve(argv: Sequence[str], *, timeout: float = RESOLVE_TIMEOUT_S) -> tuple[bool, str]:
    """Execute a vetted-safe argv (never `shell=True`, never a string
    built from journal text) bounded by `timeout` seconds. Returns `(ok,
    text)`: `text` is captured stdout when `ok`, otherwise a human-
    readable description of what went wrong (missing binary, nonzero
    exit, timeout) -- callers append the manual command themselves so the
    same failure text is reusable for both the single-ref and
    `--resolve-all` paths."""
    tool = argv[0]
    if shutil.which(tool) is None and "/" not in tool:
        return False, f"binary not found on PATH: {tool!r}"
    try:
        proc = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout:g}s"
    except OSError as exc:
        return False, str(exc)
    if proc.returncode != 0:
        stderr_tail = proc.stderr.strip()
        detail = f": {stderr_tail}" if stderr_tail else ""
        return False, f"exited {proc.returncode}{detail}"
    return True, proc.stdout


def _render_resolution(index: int, row: RefRow) -> list[str]:
    """One ref's `--resolve` output block: a header naming the ref (index,
    kind, provider) and the EXACT command run (or that would have run),
    followed by content, a refusal note, or an error -- never a fabricated
    substitute for any of the three. Failure (refusal, missing binary,
    nonzero exit, timeout) is never a `orc refs` run failure -- the ref
    itself remains valid; only the resolution attempt did not produce
    content -- so this never raises."""
    lines = [f"--- [{index}] {row.kind} ({row.provider}): {row.resolve.display} ---"]
    if row.resolve.argv is None:
        if row.resolve.refusal is not None:
            lines.append(f"REFUSED: {row.resolve.refusal}")
            lines.append(f"manual command: {row.resolve.display}")
        else:
            lines.append("no resolve command available for this ref")
        return lines

    ok, text = _execute_resolve(row.resolve.argv)
    if not ok:
        lines.append(f"ERROR: {text}")
        lines.append(f"manual command: {row.resolve.display}")
        return lines

    # Content passthrough is raw by nature (issue #43/axi #6 non-TTY
    # escape-free hygiene applies to THIS command's own output, not to
    # verbatim adapter-native content it displays on request) -- stripped
    # or denied nothing silently; only the size cap below is applied, and
    # only with a definitive count plus the same manual command already
    # named in the header.
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > RESOLVE_OUTPUT_CAP_BYTES:
        truncated = encoded[:RESOLVE_OUTPUT_CAP_BYTES].decode("utf-8", errors="ignore")
        lines.append(truncated)
        lines.append(
            f"... truncated, showing first {RESOLVE_OUTPUT_CAP_BYTES} of {len(encoded)} bytes; "
            f"run manually for full output: {row.resolve.display}"
        )
    else:
        lines.append(text.rstrip("\n"))
    return lines


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

    selector = getattr(args, "resolve", None)
    resolve_all = getattr(args, "resolve_all", False)

    if selector is not None:
        # `_select_row` raises canonical ERR-VALIDATION (propagated by
        # `main()`'s top-level CoreError handler, exit 2) for an
        # out-of-range/ambiguous/absent selector -- a usage error, distinct
        # from a resolution FAILURE below, which never changes this
        # command's exit code (TASK-M3C-002's failure-honesty rule: the ref
        # remains valid even when resolving it fails).
        index, row = _select_row(rows, selector)
        for line in _render_resolution(index, row):
            print(line)
        return 0

    if resolve_all:
        any_resolved = False
        for index, row in enumerate(rows, start=1):
            if row.resolve.display == "-":
                continue
            any_resolved = True
            for line in _render_resolution(index, row):
                print(line)
        if not any_resolved:
            print("no refs in this run carry a resolve command")
        return 0

    for index, row in enumerate(rows, start=1):
        print(f"[{index}] {_row_line(row)}")
    return 0


__all__ = ["RefRow", "ResolveCommand", "cmd_refs", "collect_refs"]
