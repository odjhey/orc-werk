"""CLI dispatch-config loading/translation (`TASK-M0-005`).

The `orc dispatch --config <path>` config file is a portable JSON document
declaring the scripted-adapter scripts and (optionally) a multi-work plan
for one run. This module is CLI-owned composition, not a canonical
protocol shape (`ARCH-REPOSITORY-STRUCTURE`: only `orc_werk.cli` composes
adapters); the schema below is this reference CLI's own invention, not a
normative contract.

## Config schema

This same plain-JSON object schema is used by explicit ``--config`` files
and the optional repo-default profile.  The profile is discovered only at
``<resolved-journal-dir>/profile.json``: with the default journal directory
that is ``<repo>/.orc/profile.json``; with ``--journal`` or
``ORC_JOURNAL_DIR`` it is the selected directory's ``profile.json``.  No
cwd/ancestor search is performed.  Effective precedence is explicit
``--config`` (deep-merged) over a run's persisted ``config.json`` over the
profile over ``{}``; nested JSON objects compose, while other values replace.
The ``--max-attempts`` flag keeps its existing precedence over the resulting
config's ``max_attempts``. At each layer boundary, an explicit adapter change
inside ``execution``, ``candidate``, ``assurance``, or ``mirror`` drops keys
inherited from the previous adapter that are exclusive to it; keys supplied by
the overlay and inherited adapter-agnostic keys remain.

Issue #240: ``max_attempts`` is special-cased beyond ordinary layering once a
run exists. The journaled ``FX-CREATE-WORK.data.max_attempts`` -- not this
module's merged config -- is the single authority for an existing run's
retry decisions (``orc_werk.core.reducer.journaled_max_attempts``,
``SCN-008``'s budget-authority clause); this module's ``build_run_config``
is consulted for that only at run creation. An explicit ``--max-attempts``
flag or ``--config`` file's ``max_attempts`` supplied for an EXISTING run
that disagrees with the journaled value is refused with ``ERR-VALIDATION``
(match-or-refuse) rather than silently applied or silently diverging; a
flag-supplied value at creation is persisted into the run's own
``config.json`` so a later bare ``--run-id`` resume's merged config already
agrees with the journal from birth.

```json
{
  "run_id": "optional-explicit-delivery-run-id",
  "max_attempts": 3,
  "resume_capability": null,
  "execution_capabilities": [],
  "plan": null,
  "attempts": {
    "work-1": [
      {"outcome": "completed", "candidate": {"label": "A"}, "assurance": {"verdict": "rejected"}},
      {"outcome": "completed", "candidate": {"label": "B"}, "assurance": {"verdict": "accepted"}}
    ]
  }
}
```

- `attempts` is keyed by `work_id` (defaulting to the single-work plan's
  `orc_werk.app.DEFAULT_WORK_ID`, `"work-1"`, when `plan` is omitted). Each
  entry is one scripted attempt, in order (attempt 1 first): `outcome` is
  `"completed"` or `"failed"` (`ExecutionPort`/`ScriptedExecution`);
  `candidate`, when present and `outcome == "completed"`, is the portable
  `subject_identity` content `ScriptedCandidate.identify` returns (its
  canonical-JSON sha256 IS the candidate fingerprint --
  `orc_werk.adapters.scripted.candidate.fingerprint_of`, exported
  precisely so callers like this one never have to guess it); `artifact_refs`
  (issue #224), when present, is a portable list of externally resolvable
  references transported verbatim into `FACT-EXEC-SETTLED.artifact_refs`
  (`PROTOCOL-FACTS`) -- `orc record --outcome --evidence-ref` writes here;
  `assurance`, when present, supplies that candidate's scripted verdict
  (`ScriptedAssurance`); `extensions` (#105/#106), when present, is passed
  through verbatim into the scripted execution outcome's own `extensions`
  field (e.g. an `execution-session/v1` payload) -- the same passthrough
  envelope field every journaled fact already carries
  (`CONTRACT-EXTENSIONS`).

### Scripted assurance entry

An attempt entry's `assurance` object accepts exactly these keys:

- `verdict` (REQUIRED): `"accepted"`, `"rejected"`, or `"inconclusive"`.
- `states` (optional): the per-assurance-inspection lifecycle-state script,
  in order; it defaults to `["settled"]`.
- `evidence_refs` (optional): a portable list of externally resolvable
  reference strings.
- `extensions` (optional): a versioned-extension map transported opaquely
  under `CONTRACT-EXTENSIONS`. Per `PLAYBOOK-AGENT-CLI` section 4, a
  verifier records substantive findings here as
  `{"review-findings/v1": {...}}`; `{"assurance-context/v1": {...}}` is
  also accepted for verifier-attested audit-base provenance.
- `derived_identity` (optional): a non-empty portable-JSON object containing
  identity fields only; an empty object, a non-object, or an object containing
  `extensions` is `ERR-VALIDATION`. At verdict-binding time every asserted key
  must exist and compare by uninterpreted JSON equality with the bound
  candidate's durable `subject_identity`. A mismatch is `ERR-CONFLICT` before
  any Fact is journaled. The key is CLI-only and is stripped before the
  scripted assurance adapter receives the entry.

- `plan` is an optional `PORT-WORK-001` multi-work plan (needed to exercise
  a fan-in run like `SCN-005` from the CLI); defaults to
  `orc_werk.app.default_single_work_plan()`.
- `max_attempts` is the positive retry budget (default `3`);
  `resume_capability` is the optional capability policy uses for resume;
  `execution_capabilities` is the list advertised by the execution port.

## Port selection (`execution`/`candidate`/`assurance`)

Three optional top-level objects select the adapters for the delivery seats.
Their complete adapter vocabularies are: `execution.adapter` is `"scripted"`
(the only value -- 0.5.0/`ADR-0005` removed the `acp` `ExecutionPort`
adapter, so `execution` carries no other key either); `candidate.adapter`
is `"scripted"` (default) or `"git"`; and `assurance.adapter` is
`"scripted"` (default) or `"command"` (0.5.0/`ADR-0005` removed the
no-mistakes `AssurancePort` adapter).

```json
{
  "candidate": {"adapter": "git", "repo_path": "/abs/worktree"},
  "assurance": {"adapter": "command", "script": "scripts/assure-candidate.sh",
                 "cwd": "/abs/worktree", "timeout_s": 300}
}
```

- `execution.adapter`: `"scripted"` only. There is no real `ExecutionPort`
  adapter to select in 0.5.0+; a deployment that still needs a real
  executor runs it externally and pushes the outcome in via
  `orc record <run> --work <id> --outcome completed|failed` (`ADR-0005`,
  `PLAYBOOK-AGENT-CLI`) -- the ship-seat sibling of the verdict path's
  `orc record <run> --work <id> --verdict accepted|rejected` (issue #192).
  Candidate identity is never settable through `--outcome`: a `git`
  candidate gets identified by the next `orc dispatch` pass, and a
  `scripted` candidate's `attempts[work_id][n].candidate` stays
  hand-authored in the config.
- `candidate.adapter`: `"scripted"` (default) or `"git"`. `"git"` selects
  `orc_werk.adapters.git.candidate.GitDiffCandidate(repo_path=...)`.
  `repo_path` is REQUIRED when `adapter == "git"`.
- `assurance.adapter`: `"scripted"` (default) or `"command"`. `"command"`
  selects `orc_werk.adapters.command.assurance.CommandAssurance` with
  REQUIRED `script` and `cwd`; relative scripts resolve against `cwd`,
  the resolved path must remain inside `cwd`, and it must exist and be
  executable. `timeout_s` is a positive number (default 300). No args,
  environment, or inline-script key exists. A real assurance adapter derives
  its own verdict, so attempt entries MUST NOT also provide `assurance`.
  The real assurance adapter REQUIRES `candidate.adapter == "git"`.
- **Attempts-merge semantics when candidate is real** (the PR body's
  "attempts-merge semantics" decision, restated here as it governs load-time
  validation): when `candidate.adapter == "git"`, an `attempts[work_id]`
  entry may carry ONLY `assurance` -- never `outcome`/`candidate`/`states`/
  `artifact_refs` for that work, because the real `CandidatePort` supplies
  those and a config-declared value would be a silently-ignored footgun.
  Execution stays `"scripted"` in every case, so `outcome`/`states`/
  `artifact_refs` remain allowed (they still drive `ScriptedExecution`),
  just never `candidate`.

Because `ScriptedCandidate` scripts are keyed by `execution_id`, and
`ScriptedExecution` derives `execution_id` deterministically from the
`FX-START-EXECUTION` idempotency key (`CONF-EXEC-001`, documented in that
adapter's own module docstring as
``execution_id = f"exec-{sha256(idempotency_key)[:16]}"``), this module
predicts each attempt's `execution_id` up front via the same public
`orc_werk.core.idempotency.idempotency_key` derivation so a human-authored
config never has to spell out a hash by hand.

## Per-work briefs and Beads mirror (optional, `TASK-M2-006`)

The optional `briefs` mapping supplies, when the mirror is configured,
per-work descriptions for the write-only projection of run/work state
into a shared `bd` database (canonical `ADAPTER-BEADS-MAPPING` has the
full design):

```json
{
  "mirror": {"adapter": "beads", "workspace": "/abs/bd-initialized/dir", "bd_bin": "bd"},
  "briefs": {"work-1": "per-work brief text, becomes the bd issue description"}
}
```

- `mirror` is entirely optional; ABSENT means no mirror is built at all --
  zero behavior change for every existing config (`build_mirror` returns
  `None`, and `cmd_dispatch` skips every mirror call). `mirror.adapter`:
  only `"beads"` is defined today. `mirror.workspace` is REQUIRED when
  `mirror` is present -- the directory an operator has already run `bd
  init` in (this CLI never runs `bd init` itself). `mirror.bd_bin`
  optionally overrides the `bd` binary name/path (default `"bd"`, resolved
  via `PATH`). A `workspace` that has no `.beads` directory of its own
  degrades the whole projection before any `bd` subprocess is spawned
  (`BeadsMirror`'s walk-up containment guard -- `bd -C` would otherwise
  silently write into the nearest ANCESTOR `.beads` database; see the
  mapping doc's "Workspace guard" section).
- `briefs` is a CLI-owned, non-canonical sibling to `plan` (`PORT-WORK-001`
  itself carries no brief/description field -- `CONTRACT-DURABILITY`'s
  multi-work-brief row stays outside core) keyed by `work_id`. Each entry
  feeds that work's Beads mirror issue description. When `briefs[work]` is
  set, that entry -- not the run intent text -- is the description used
  for that work. A work with no entry falls back to the run's own intent
  text -- never an empty description when the run-level intent text is
  available (see the mapping doc's brief-fallback note).
- A degraded mirror (one or more `bd` invocations failed) is NEVER a
  dispatch failure: `cmd_dispatch` prints a `mirror: degraded (...)` note
  to stderr and returns the SAME exit code the run would have had without
  a mirror configured at all (mirror failures MUST NEVER break the
  delivery loop, per the task card).

## Observer hooks (optional, `SCN-018`, issue #193)

The optional top-level `observers` key declares config-driven, fire-and-
forget commands the CLI spawns after specific canonical Facts are journaled
by the current dispatch pass -- the notification half of issue #193 (the
behavior-modification half is an explicitly separate, unfiled card).
`orc_werk.cli.observers` is the firing implementation and the fuller design
note; this is the config schema `orc config-schema` prints:

```json
{
  "observers": {
    "on_settle": {"command": ["./scripts/notify-settle.sh"]},
    "on_verdict": {"command": ["./scripts/notify-verdict.sh"], "timeout_seconds": 10},
    "on_blocked": {"command": ["./scripts/notify-blocked.sh"]}
  }
}
```

- `observers` is entirely optional; ABSENT means zero behavior change for
  every existing config (`orc_werk.cli.observers.fire_observers` is a no-op
  for a `None`/empty mapping). Its only allowed keys are `on_settle`,
  `on_verdict`, `on_blocked`, each independently optional -- an operator
  configures any subset. `on_settle` fires once per dispatch pass for each
  `FACT-EXEC-SETTLED` newly appended that pass; `on_verdict` the same for
  `FACT-ASSURE-SETTLED` (a verdict INHERITED via `STATE-DELIVERY` item 8
  journals no new such Fact, so it is never a trigger); `on_blocked` the
  same for `FACT-WORK-BLOCKED`.
- Each trigger's object accepts exactly two keys: `command` (REQUIRED) --
  a non-empty argv-array of strings, never a shell string, matching command
  assurance's `script`-only shape (`SCN-015`) -- and `timeout_seconds`
  (optional, a non-negative number, default `30`): the bounded maximum
  lifetime of that trigger's spawned observer process, enforced by a
  supervisor that travels with the spawned process group, never by a later
  dispatch pass (`orc_werk.cli.observers` module docstring).
- `command[0]` (relative paths resolve against the CLI process's own actual
  working directory at dispatch invocation time -- see
  `orc_werk.cli.observers`' "Ambiguity: the dispatch config's cwd" section
  for why that reading, absent any `cwd` key of its own here) must resolve,
  by path containment and not textual prefix matching, INSIDE that
  directory: an escaping `command[0]` is `ERR-VALIDATION` at config-load
  time, before any journal write -- the identical containment rejection
  command assurance's own script uses (`SCN-015`). A command whose script
  is merely missing or non-executable at fire time is NOT a load-time
  rejection -- it is a single stderr warning per dispatch pass, per
  triggering fact, and the run is otherwise entirely unaffected (`SCN-018`
  step 11): observers are a supplementary side channel, never load-bearing
  for delivery the way a real assurance adapter's script is.
- The triggering fact's own journal envelope (exactly as journaled: `kind`/
  `id`/`data`/`seq`/`extensions`/...) is written as one JSON document to the
  spawned observer's standard input, then standard input is closed -- never
  argv, never an environment variable. The observer's own exit status,
  stdout, and stderr are always opaque: never journaled, never inspected,
  and never able to change dispatch's own exit code or stdout (the same
  write-only posture `INV-014` already establishes for the Beads mirror).
- Delivery is explicitly **at-most-once**, CLI-local, and unjournaled: a
  hook fires only for facts newly appended by the CURRENT dispatch pass,
  never for replayed history and never again on any later pass or
  reconstruction of the same journal (`SCN-018` steps 13-15). No kernel
  semantics exist for this at all -- `src/orc_werk/core` never knows
  observers exist.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from orc_werk.adapters.beads.mirror import BeadsMirror
from orc_werk.adapters.command.assurance import CommandAssurance
from orc_werk.adapters.git.candidate import GitDiffCandidate
from orc_werk.cli.observers import DEFAULT_TIMEOUT_SECONDS, OBSERVER_TRIGGERS, resolve_command_path
from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate, fingerprint_of
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app.orchestrator import RunConfig
from orc_werk.core.effects import FX_IDENTIFY_CANDIDATE, FX_START_EXECUTION
from orc_werk.core.errors import CoreError, ERR_PROVIDER_UNAVAILABLE, canonical_error, conflict_error
from orc_werk.core.errors import validation_error as _core_validation_error
from orc_werk.core.facts import ASSURANCE_VERDICTS, EXEC_OUTCOMES, FACT_CANDIDATE_OBSERVED
from orc_werk.core.idempotency import idempotency_key
from orc_werk.core.portable import is_portable
from orc_werk.core.serialization import KIND_FACT
from orc_werk.ports.assurance import AssurancePort
from orc_werk.ports.candidate import CandidatePort
from orc_werk.ports.capabilities import validate_capabilities
from orc_werk.ports.execution import ExecutionPort
from orc_werk.ports.journal import JournalPort

# #17 (re-scoped, docs/delivery/M1-delivery-ledger.md): the CLI-owned,
# non-normative config schema this module's own docstring documents.
# Load-time strict validation rejects unknown top-level keys and
# structurally malformed `attempts` shapes -- it never rejects an *absent*
# `attempts` key or a planned Work with no entry (the valid
# fully-incremental/SCN-007-pending case).
_TOP_LEVEL_KEYS = frozenset(
    {
        "run_id",
        "max_attempts",
        "resume_capability",
        "execution_capabilities",
        "plan",
        "attempts",
        "execution",
        "candidate",
        "assurance",
        "mirror",
        "briefs",
        "observers",
    }
)
_ATTEMPT_ENTRY_KEYS = frozenset({"outcome", "candidate", "assurance", "states", "artifact_refs", "extensions"})
_ASSURANCE_ENTRY_KEYS = frozenset({"verdict", "states", "evidence_refs", "extensions", "derived_identity"})
# `observers` (`SCN-018`, issue #193): each trigger entry accepts EXACTLY
# `command`/`timeout_seconds` -- no `args`-appended-to-command, no inline
# script text, no environment key, matching command assurance's
# `script`/`cwd`-only shape's own restraint (module docstring, "Observer
# hooks" section).
_OBSERVER_ENTRY_KEYS = frozenset({"command", "timeout_seconds"})

# `execution`/`candidate`/`assurance` real-port selection (module
# docstring, "Real-port selection" section). `execution` has no adapter
# beyond the "scripted" default (0.5.0/ADR-0005 removed the `acp`
# `ExecutionPort` adapter), so `adapter` is its only config key; `adapter`
# is this CLI's own selector, not an adapter constructor parameter.
_EXECUTION_CONFIG_KEYS = frozenset({"adapter"})
_EXECUTION_ADAPTERS = frozenset({"scripted"})
_CANDIDATE_CONFIG_KEYS = frozenset({"adapter", "repo_path"})
_CANDIDATE_ADAPTERS = frozenset({"scripted", "git"})
_ASSURANCE_CONFIG_KEYS = frozenset({"adapter", "script", "cwd", "timeout_s"})
_ASSURANCE_ADAPTERS = frozenset({"scripted", "command"})
# `mirror` (`TASK-M2-006`, module docstring "Beads mirror" section): unlike
# execution/candidate/assurance, there is no "scripted" default -- absent
# `mirror` means no mirror at all, not a null-object adapter. `workspace`
# is keyed exactly to `BeadsMirror`'s one required constructor parameter;
# `bd_bin` maps to its optional one. No `timeout_s` key exposed at this
# layer either, matching the no-mistakes precedent's "don't expose every
# constructor parameter" restraint (`CLAUDE.md` #3).
_MIRROR_CONFIG_KEYS = frozenset({"adapter", "workspace", "bd_bin", "project"})
_MIRROR_ADAPTERS = frozenset({"beads"})

# Single source for adapter-conditional validation and layer composition.
# When an overlay changes a section's adapter, only inherited keys exclusive
# to the lower layer's selected adapter are removed (#174).
_ADAPTER_EXCLUSIVE_KEYS: Mapping[str, Mapping[str, frozenset[str]]] = {
    "execution": {},
    "candidate": {"git": frozenset({"repo_path"})},
    "assurance": {
        "command": frozenset({"script", "cwd", "timeout_s"}),
    },
    "mirror": {"beads": _MIRROR_CONFIG_KEYS - {"adapter"}},
}
_ADAPTER_DEFAULTS = {
    "execution": "scripted",
    "candidate": "scripted",
    "assurance": "scripted",
    "mirror": "beads",
}

# issue #94: every validation error this module raises is, by construction,
# about the dispatch config document -- `orc config-schema` (this module's
# own docstring, printed verbatim) is the one guide every one of them
# shares. Shadowing the imported `orc_werk.core.errors.validation_error`
# name with this module-local wrapper means every existing `raise
# validation_error(...)` call site below picks up that default `next`
# automatically -- an explicit `next_steps=` at a call site still wins,
# but none currently need to be more specific than "go read the schema".
# This is the single-touch alternative to hand-editing this module's ~40
# call sites with an identical `next_steps=["orc config-schema"]` each.
_CONFIG_SCHEMA_NEXT = ("orc config-schema",)

# ADR-0005: the `acp` `ExecutionPort` adapter and the no-mistakes
# `AssurancePort` adapter were removed in 0.5.0 (Breaking). A config author
# who names either by its old string gets the ordinary "not one of [...]"
# adapter-vocabulary error PLUS this extra guidance line, so the rejection
# points at the removal decision instead of just looking like a typo.
_REMOVED_ADAPTERS = frozenset({"acp", "no-mistakes"})
_REMOVED_ADAPTER_NEXT = (
    "removed in 0.5.0 (ADR-0005) -- pin orc v0.4.1 or migrate to external-executor "
    "recording (PLAYBOOK-AGENT-CLI)"
)


def validation_error(message: str, *, next_steps: Optional[Sequence[str]] = None, **details: Any) -> CoreError:
    return _core_validation_error(message, next_steps=next_steps or _CONFIG_SCHEMA_NEXT, **details)


def _adapter_choice_error(path: str, adapters: frozenset[str], value: Any) -> CoreError:
    """`<section>.adapter is not one of [...]` -- with an extra `next` hint
    when the rejected value is an adapter this repo used to support and
    removed (ADR-0005)."""
    next_steps = list(_CONFIG_SCHEMA_NEXT)
    if value in _REMOVED_ADAPTERS:
        next_steps.append(_REMOVED_ADAPTER_NEXT)
    return validation_error(
        f"config value at {path} is not one of {sorted(adapters)}: {value!r}",
        path=path,
        next_steps=next_steps,
    )


def _require_portable(value: Any, *, path: str) -> None:
    """Recursively confirm a parsed config value is portable/JSON-compatible
    (`orc_werk.core.portable.is_portable`), raising canonical `ERR-VALIDATION`
    naming the exact offending path.

    BUG-1 dogfood finding: Python's `json.loads` accepts the bare
    `NaN`/`Infinity`/`-Infinity` tokens even though they have no JSON
    literal (`core/portable.py` module docstring), so a hand-authored
    config like `{"score": NaN}` parses without error and only fails much
    later -- deep inside adapter construction, as an uncaught `TypeError`/
    `ValueError` from `core.portable` -- producing a raw Python traceback
    instead of this CLI's documented "never a Python traceback" canonical
    error contract (`main.py` module docstring). Checking portability of
    the whole config at load time, before any of it reaches a canonical
    shape, catches this at the boundary that owns the guarantee.
    """
    if is_portable(value):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _require_portable(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _require_portable(item, path=f"{path}[{index}]")
    raise validation_error(
        f"config value at {path} is not portable/JSON-compatible: {value!r}",
        path=path,
    )


def _validate_top_level_keys(data: Mapping[str, Any]) -> None:
    unknown = sorted(set(data) - _TOP_LEVEL_KEYS)
    if unknown:
        raise validation_error(
            f"config contains unknown top-level key(s): {', '.join(unknown)}",
            unknown_keys=unknown,
            known_keys=sorted(_TOP_LEVEL_KEYS),
        )


def _validate_assurance_entry(assurance: Any, *, path: str) -> None:
    if not isinstance(assurance, Mapping):
        raise validation_error(
            f"config value at {path} must be a JSON object, got {type(assurance).__name__}", path=path
        )
    unknown = sorted(set(assurance) - _ASSURANCE_ENTRY_KEYS)
    if unknown:
        raise validation_error(
            f"config value at {path} has unknown key(s): {', '.join(unknown)}",
            path=path,
            unknown_keys=unknown,
        )
    if "verdict" in assurance and assurance["verdict"] not in ASSURANCE_VERDICTS:
        raise validation_error(
            f"config value at {path}.verdict is not a valid assurance verdict: {assurance['verdict']!r}",
            path=f"{path}.verdict",
            verdict=assurance["verdict"],
        )
    if "derived_identity" in assurance:
        derived = assurance["derived_identity"]
        derived_path = f"{path}.derived_identity"
        if not isinstance(derived, Mapping):
            raise validation_error(
                f"config value at {derived_path} must be a JSON object, got {type(derived).__name__}",
                path=derived_path,
            )
        if not derived:
            raise validation_error(
                f"config value at {derived_path} must be a non-empty identity object",
                path=derived_path,
            )
        if "extensions" in derived:
            raise validation_error(
                f"config value at {derived_path} must contain identity fields only; extensions is forbidden",
                path=derived_path,
            )


def _attempt_allowed_keys(
    *, execution_adapter: str, candidate_adapter: str, assurance_adapter: str = "scripted"
) -> frozenset[str]:
    """Real-port-aware attempt-entry allowlist (module docstring,
    "Attempts-merge semantics"). `assurance` is allowed only when assurance
    stays scripted (the operator/verification agent records verdicts
    through this channel); a real `AssurancePort` (`TASK-M2-001`) derives
    its own verdict automatically, so a config-declared one would be
    silently ignored -- the same rationale `candidate` already follows for
    a real `CandidatePort`. `outcome`/`states`/`artifact_refs` are allowed
    only when execution stays scripted (a real `ExecutionPort` supplies
    its own outcome). `candidate` is allowed only when the candidate stays
    scripted (a real `CandidatePort` supplies its own subject; a
    config-declared one would be silently ignored)."""
    allowed: set[str] = set()
    if assurance_adapter == "scripted":
        allowed.add("assurance")
    if execution_adapter == "scripted":
        allowed |= {"outcome", "states", "artifact_refs", "extensions"}
    if candidate_adapter == "scripted":
        allowed.add("candidate")
    return frozenset(allowed)


def _validate_attempts(
    attempts: Any,
    *,
    execution_adapter: str = "scripted",
    candidate_adapter: str = "scripted",
    assurance_adapter: str = "scripted",
) -> None:
    """#17 (re-scoped): reject structurally malformed `attempts` shapes at
    config load time -- a non-mapping `attempts` value, a non-list
    per-work attempts value, a non-mapping attempt entry, an unknown key
    inside an entry, or an invalid `outcome`/`assurance.verdict` value. An
    *absent* `attempts` key, or a planned Work with no entry at all, is the
    valid fully-incremental case (`SCN-007`'s pending default) and MUST NOT
    be rejected -- see the M1-delivery-ledger #17 re-scope annotation.

    `execution_adapter`/`candidate_adapter`/`assurance_adapter`
    (`TASK-M1-005`/`TASK-M2-001` CLI wiring): narrow the allowed per-entry
    key set when any port is real -- see `_attempt_allowed_keys` and the
    module docstring's "Attempts-merge semantics" section."""
    if attempts is None:
        return
    if not isinstance(attempts, Mapping):
        raise validation_error(
            f"config 'attempts' must be a JSON object keyed by work_id, got {type(attempts).__name__}",
            path="<config>.attempts",
        )
    allowed_keys = _attempt_allowed_keys(
        execution_adapter=execution_adapter,
        candidate_adapter=candidate_adapter,
        assurance_adapter=assurance_adapter,
    )
    for work_id, work_attempts in attempts.items():
        path = f"<config>.attempts.{work_id}"
        if not isinstance(work_attempts, list):
            raise validation_error(
                f"config value at {path} must be a JSON array of attempt entries, "
                f"got {type(work_attempts).__name__}",
                path=path,
            )
        for index, entry in enumerate(work_attempts):
            entry_path = f"{path}[{index}]"
            if not isinstance(entry, Mapping):
                raise validation_error(
                    f"config value at {entry_path} must be a JSON object, got {type(entry).__name__}",
                    path=entry_path,
                )
            unknown = sorted(set(entry) - allowed_keys)
            if unknown:
                raise validation_error(
                    f"config value at {entry_path} has unknown key(s): {', '.join(unknown)} "
                    f"(execution.adapter={execution_adapter!r}, candidate.adapter={candidate_adapter!r}, "
                    f"assurance.adapter={assurance_adapter!r} allows only {sorted(allowed_keys)})",
                    path=entry_path,
                    unknown_keys=unknown,
                )
            if "outcome" in entry and entry["outcome"] not in EXEC_OUTCOMES:
                raise validation_error(
                    f"config value at {entry_path}.outcome is not a valid execution outcome: "
                    f"{entry['outcome']!r}",
                    path=f"{entry_path}.outcome",
                    outcome=entry["outcome"],
                )
            if entry.get("assurance") is not None:
                _validate_assurance_entry(entry["assurance"], path=f"{entry_path}.assurance")


def _validate_execution_config(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise validation_error(
            f"config value at <config>.execution must be a JSON object, got {type(value).__name__}",
            path="<config>.execution",
        )
    unknown = sorted(set(value) - _EXECUTION_CONFIG_KEYS)
    if unknown:
        raise validation_error(
            f"config value at <config>.execution has unknown key(s): {', '.join(unknown)}",
            path="<config>.execution",
            unknown_keys=unknown,
            known_keys=sorted(_EXECUTION_CONFIG_KEYS),
        )
    adapter = value.get("adapter", "scripted")
    if adapter not in _EXECUTION_ADAPTERS:
        raise _adapter_choice_error("<config>.execution.adapter", _EXECUTION_ADAPTERS, adapter)


def _validate_candidate_config(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise validation_error(
            f"config value at <config>.candidate must be a JSON object, got {type(value).__name__}",
            path="<config>.candidate",
        )
    unknown = sorted(set(value) - _CANDIDATE_CONFIG_KEYS)
    if unknown:
        raise validation_error(
            f"config value at <config>.candidate has unknown key(s): {', '.join(unknown)}",
            path="<config>.candidate",
            unknown_keys=unknown,
            known_keys=sorted(_CANDIDATE_CONFIG_KEYS),
        )
    adapter = value.get("adapter", "scripted")
    if adapter not in _CANDIDATE_ADAPTERS:
        raise validation_error(
            f"config value at <config>.candidate.adapter is not one of {sorted(_CANDIDATE_ADAPTERS)}: {adapter!r}",
            path="<config>.candidate.adapter",
        )
    if adapter == "scripted":
        present_only = sorted(_ADAPTER_EXCLUSIVE_KEYS["candidate"]["git"] & set(value))
        if present_only:
            raise validation_error(
                "config value at <config>.candidate.repo_path requires candidate.adapter == 'git'",
                path="<config>.candidate.repo_path",
            )
        return
    repo_path = value.get("repo_path")
    if not isinstance(repo_path, str) or not repo_path:
        raise validation_error(
            "config value at <config>.candidate.repo_path is required (a non-empty string) when "
            "candidate.adapter == 'git'",
            path="<config>.candidate.repo_path",
        )


def _validate_assurance_config(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise validation_error(
            f"config value at <config>.assurance must be a JSON object, got {type(value).__name__}",
            path="<config>.assurance",
        )
    unknown = sorted(set(value) - _ASSURANCE_CONFIG_KEYS)
    if unknown:
        raise validation_error(
            f"config value at <config>.assurance has unknown key(s): {', '.join(unknown)}",
            path="<config>.assurance",
            unknown_keys=unknown,
            known_keys=sorted(_ASSURANCE_CONFIG_KEYS),
        )
    adapter = value.get("adapter", "scripted")
    if adapter not in _ASSURANCE_ADAPTERS:
        raise _adapter_choice_error("<config>.assurance.adapter", _ASSURANCE_ADAPTERS, adapter)
    if adapter == "scripted":
        real_only = set().union(*_ADAPTER_EXCLUSIVE_KEYS["assurance"].values())
        present_only = sorted(real_only & set(value))
        if present_only:
            raise validation_error(
                f"config value(s) at <config>.assurance {present_only} require a real assurance adapter",
                path="<config>.assurance",
            )
        return
    script = value.get("script")
    cwd = value.get("cwd")
    if not isinstance(script, str) or not script:
        raise validation_error(
            "config value at <config>.assurance.script is required (a non-empty string) when assurance.adapter == 'command'",
            path="<config>.assurance.script",
        )
    if not isinstance(cwd, str) or not cwd:
        raise validation_error(
            "config value at <config>.assurance.cwd is required (a non-empty string) when assurance.adapter == 'command'",
            path="<config>.assurance.cwd",
        )
    timeout_s = value.get("timeout_s", 300)
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
        raise validation_error(
            "config value at <config>.assurance.timeout_s must be a positive number",
            path="<config>.assurance.timeout_s",
        )
    cwd_path = Path(cwd).resolve()
    configured = Path(script)
    resolved = (cwd_path / configured).resolve() if not configured.is_absolute() else configured.resolve()
    try:
        resolved.relative_to(cwd_path)
    except ValueError as exc:
        raise validation_error(
            "config command assurance script must resolve inside cwd",
            path="<config>.assurance.script",
            resolved_script=str(resolved),
            cwd=str(cwd_path),
        ) from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise CoreError(
            canonical_error(
                ERR_PROVIDER_UNAVAILABLE,
                "command assurance script is missing or not executable",
                script=str(resolved),
                cwd=str(cwd_path),
            )
        )


def _validate_mirror_config(value: Any) -> None:
    """`mirror` (`TASK-M2-006`): unlike execution/candidate/assurance,
    ABSENT (`None`) is the only "no mirror" spelling -- there is no
    `"scripted"`/null-adapter fallback to reject a stray `repo_path`-style
    key against, so this function's shape is a little simpler than its
    three siblings above."""
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise validation_error(
            f"config value at <config>.mirror must be a JSON object, got {type(value).__name__}",
            path="<config>.mirror",
        )
    unknown = sorted(set(value) - _MIRROR_CONFIG_KEYS)
    if unknown:
        raise validation_error(
            f"config value at <config>.mirror has unknown key(s): {', '.join(unknown)}",
            path="<config>.mirror",
            unknown_keys=unknown,
            known_keys=sorted(_MIRROR_CONFIG_KEYS),
        )
    adapter = value.get("adapter", "beads")
    if adapter not in _MIRROR_ADAPTERS:
        raise validation_error(
            f"config value at <config>.mirror.adapter is not one of {sorted(_MIRROR_ADAPTERS)}: {adapter!r}",
            path="<config>.mirror.adapter",
        )
    workspace = value.get("workspace")
    if not isinstance(workspace, str) or not workspace:
        raise validation_error(
            "config value at <config>.mirror.workspace is required (a non-empty string) when "
            "'mirror' is present -- the directory an operator has already run 'bd init' in",
            path="<config>.mirror.workspace",
        )
    if "bd_bin" in value and (not isinstance(value["bd_bin"], str) or not value["bd_bin"]):
        raise validation_error(
            "config value at <config>.mirror.bd_bin must be a non-empty string when present",
            path="<config>.mirror.bd_bin",
        )
    if "project" in value and (not isinstance(value["project"], str) or not value["project"]):
        raise validation_error(
            "config value at <config>.mirror.project must be a non-empty string when present",
            path="<config>.mirror.project",
        )


def _validate_briefs(value: Any) -> None:
    """`briefs` (`TASK-M2-006`): a CLI-owned, non-canonical `work_id ->
    brief text` mapping, entirely optional and independent of `mirror` --
    a config MAY supply briefs even when no mirror is configured (this
    validator has no adapter-conditional gate of its own), matching how
    `attempts` is validated independently of which ports are real."""
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise validation_error(
            f"config 'briefs' must be a JSON object keyed by work_id, got {type(value).__name__}",
            path="<config>.briefs",
        )
    for work_id, brief in value.items():
        if not isinstance(brief, str):
            raise validation_error(
                f"config value at <config>.briefs.{work_id} must be a string, got {type(brief).__name__}",
                path=f"<config>.briefs.{work_id}",
            )


def _validate_observer_entry(entry: Any, *, path: str, cwd: Path) -> None:
    if not isinstance(entry, Mapping):
        raise validation_error(
            f"config value at {path} must be a JSON object, got {type(entry).__name__}", path=path
        )
    unknown = sorted(set(entry) - _OBSERVER_ENTRY_KEYS)
    if unknown:
        raise validation_error(
            f"config value at {path} has unknown key(s): {', '.join(unknown)}",
            path=path,
            unknown_keys=unknown,
            known_keys=sorted(_OBSERVER_ENTRY_KEYS),
        )
    command = entry.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) for item in command)
        or not command[0]
    ):
        raise validation_error(
            f"config value at {path}.command must be a non-empty array of strings with a "
            "non-empty first element (never a bare shell string)",
            path=f"{path}.command",
        )
    if "timeout_seconds" in entry:
        timeout = entry["timeout_seconds"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0:
            raise validation_error(
                f"config value at {path}.timeout_seconds must be a non-negative number, got {timeout!r} "
                f"(default {DEFAULT_TIMEOUT_SECONDS})",
                path=f"{path}.timeout_seconds",
                timeout_seconds=timeout,
            )
    # SCN-018 "Containment and seat checks": rejected before spawn, at
    # config-load time, before any journal write -- the identical
    # containment rule command assurance uses for its own script
    # (`_validate_assurance_config` above); a MISSING/non-executable script
    # is deliberately NOT checked here (module docstring, "Observer hooks"
    # section) -- that is a fire-time-only stderr warning
    # (`orc_werk.cli.observers._spawn_one`), never a load-time rejection.
    try:
        resolve_command_path(command, cwd=cwd)
    except ValueError as exc:
        raise validation_error(
            f"config observer command at {path}.command must resolve inside cwd",
            path=f"{path}.command",
            cwd=str(cwd),
        ) from exc


def _validate_observers_config(value: Any) -> None:
    """`observers` (`SCN-018`, issue #193): entirely optional, no built-in
    default -- ABSENT means no observer configured at all, zero behavior
    change (module docstring, "Observer hooks" section)."""
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise validation_error(
            f"config value at <config>.observers must be a JSON object, got {type(value).__name__}",
            path="<config>.observers",
        )
    unknown = sorted(set(value) - OBSERVER_TRIGGERS)
    if unknown:
        raise validation_error(
            f"config value at <config>.observers has unknown key(s): {', '.join(unknown)}",
            path="<config>.observers",
            unknown_keys=unknown,
            known_keys=sorted(OBSERVER_TRIGGERS),
        )
    cwd = Path.cwd().resolve()
    for trigger, entry in value.items():
        _validate_observer_entry(entry, path=f"<config>.observers.{trigger}", cwd=cwd)


def _validate_assurance_candidate_combo(assurance_cfg: Any, candidate_cfg: Any) -> None:
    """The one real assurance adapter (`command`) REQUIRES
    `candidate.adapter == 'git'`.

    A command verifier observes real repository state; a config-predicted
    scripted candidate cannot honestly bind its verdict.
    """
    assurance_adapter = (
        (assurance_cfg or {}).get("adapter", "scripted") if isinstance(assurance_cfg, Mapping) else "scripted"
    )
    if assurance_adapter != "command":
        return
    candidate_adapter = (candidate_cfg or {}).get("adapter", "scripted") if isinstance(candidate_cfg, Mapping) else "scripted"
    if candidate_adapter != "git":
        raise validation_error(
            f"config assurance.adapter == {assurance_adapter!r} requires candidate.adapter == 'git' "
            "(a real assurance verdict cannot be bound to a config-scripted candidate)",
            path="<config>.candidate.adapter",
            assurance_adapter=assurance_adapter,
            candidate_adapter=candidate_adapter,
        )


def _read_config_mapping(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise validation_error(f"config file is not valid JSON: {path}", path=str(path)) from exc
    if not isinstance(data, Mapping):
        raise validation_error(f"config file must contain a JSON object: {path}", path=str(path))
    _require_portable(data, path="<config>")
    return data


def validate_config(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate one effective dispatch config using the schema's existing gates."""
    _validate_top_level_keys(data)
    _validate_execution_config(data.get("execution"))
    _validate_candidate_config(data.get("candidate"))
    _validate_assurance_config(data.get("assurance"))
    _validate_mirror_config(data.get("mirror"))
    _validate_briefs(data.get("briefs"))
    _validate_observers_config(data.get("observers"))
    _validate_assurance_candidate_combo(data.get("assurance"), data.get("candidate"))
    execution_adapter = (data.get("execution") or {}).get("adapter", "scripted")
    candidate_adapter = (data.get("candidate") or {}).get("adapter", "scripted")
    assurance_adapter = (data.get("assurance") or {}).get("adapter", "scripted")
    _validate_attempts(
        data.get("attempts"),
        execution_adapter=execution_adapter,
        candidate_adapter=candidate_adapter,
        assurance_adapter=assurance_adapter,
    )
    return data


def load_config(path: str) -> Mapping[str, Any]:
    return validate_config(_read_config_mapping(Path(path)))


def _entry_slot(updated: dict[str, Any], *, work_id: str, attempt_number: int) -> dict[str, Any]:
    """Shared by `record_assurance_entry`/`record_execution_outcome_entry`:
    locate (creating if this is the next unwritten slot) the mutable
    `attempts[work_id][attempt_number - 1]` entry a `record` recording
    merges into."""
    attempts = updated.setdefault("attempts", {})
    entries = attempts.setdefault(work_id, [])
    index = attempt_number - 1
    if len(entries) < index:
        raise validation_error(
            f"config has no entry for attempt {attempt_number} of work {work_id!r}",
            path=f"<config>.attempts.{work_id}[{index}]",
        )
    if len(entries) == index:
        entries.append({})
    return entries[index]


def _atomic_replace_config(path: Path, updated: Mapping[str, Any]) -> Mapping[str, Any]:
    """Shared by `record_assurance_entry`/`record_execution_outcome_entry`:
    write `updated` to `path` via a same-directory temp file + `os.replace`
    (atomic on POSIX), never a partially-written config."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(updated, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return updated


def record_assurance_entry(
    path: Path, *, work_id: str, attempt_number: int, assurance: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Merge one assurance entry into a persisted config and replace atomically."""
    current = load_config(str(path))
    updated = json.loads(json.dumps(current))
    entry = _entry_slot(updated, work_id=work_id, attempt_number=attempt_number)
    if "assurance" in entry:
        raise conflict_error(
            f"attempt {attempt_number} of work {work_id!r} already has a recorded assurance entry",
            work_id=work_id,
            attempt_number=attempt_number,
        )
    entry["assurance"] = dict(assurance)
    validate_config(updated)  # reuse all assurance/extension/adapter checks
    return _atomic_replace_config(path, updated)


def record_execution_outcome_entry(
    path: Path,
    *,
    work_id: str,
    attempt_number: int,
    outcome: str,
    artifact_refs: Optional[Sequence[Any]] = None,
    extensions: Optional[Mapping[str, Any]] = None,
) -> Mapping[str, Any]:
    """`orc record --outcome`'s sibling of `record_assurance_entry`: merge one
    ship-seat execution outcome into a persisted config and replace
    atomically. `artifact_refs` (when non-empty; issue #224) is the ship
    seat's `--evidence-ref` values, written to the attempt entry's
    canonical `artifact_refs` key -- transported losslessly into
    `FACT-EXEC-SETTLED.artifact_refs` (`PROTOCOL-FACTS`), mirroring the
    verdict path's `evidence_refs`->`FACT-ASSURE-SETTLED` precedent.
    `extensions` (when non-empty) is the attempt entry's registered push
    channel (issues #105/#106: config-entry `extensions` transport
    losslessly into `FACT-EXEC-SETTLED.extensions` per `CONF-EXT-003`):
    `executor-identity/v1` with `role: "ship"` for seat provenance (the
    same passthrough `record_assurance_entry` uses for `role: "verify"`).
    Never writes `candidate`: a real (`git`) candidate is identified by the
    next dispatch pass, and a scripted candidate's payload stays
    hand-authored."""
    current = load_config(str(path))
    updated = json.loads(json.dumps(current))
    entry = _entry_slot(updated, work_id=work_id, attempt_number=attempt_number)
    if "outcome" in entry:
        raise conflict_error(
            f"attempt {attempt_number} of work {work_id!r} already has a recorded execution outcome",
            work_id=work_id,
            attempt_number=attempt_number,
        )
    entry["outcome"] = outcome
    if artifact_refs:
        entry["artifact_refs"] = list(artifact_refs)
    if extensions:
        entry["extensions"] = dict(extensions)
    validate_config(updated)  # reuse all outcome/extension/adapter checks
    return _atomic_replace_config(path, updated)


def load_config_overlay(path: str) -> Mapping[str, Any]:
    """Load a JSON-object overlay; cross-field validation occurs after merging."""
    return _read_config_mapping(Path(path))


def load_repo_profile(journal_dir: Path) -> Optional[Mapping[str, Any]]:
    """Load ``<resolved-journal-dir>/profile.json`` when present.

    Thus the default journal ``<repo>/.orc`` discovers exactly
    ``<repo>/.orc/profile.json``.  A custom journal directory discovers its
    own sibling profile and never searches cwd or ancestor directories.
    """
    profile_path = journal_dir.resolve() / "profile.json"
    if not profile_path.exists():
        return None
    # A repo profile is a partial overlay, not an independently runnable
    # dispatch config.  Keep portable-object and top-level typo checks here,
    # but defer adapter-conditional completeness to validate_config after the
    # profile is composed with persisted and per-run layers.
    profile = _read_config_mapping(profile_path)
    _validate_top_level_keys(profile)
    return profile


def _deep_merge_json(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Generic recursive JSON-object merge used after layer-aware cleanup."""
    merged: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        prior = merged.get(key)
        if isinstance(prior, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge_json(prior, value)
        else:
            merged[key] = value
    return merged


def deep_merge_config(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> Mapping[str, Any]:
    """Compose two config layers, dropping old-adapter-exclusive inheritance."""
    prepared: dict[str, Any] = dict(base)
    for section, exclusive_by_adapter in _ADAPTER_EXCLUSIVE_KEYS.items():
        lower = base.get(section)
        higher = overlay.get(section)
        if not isinstance(lower, Mapping) or not isinstance(higher, Mapping) or "adapter" not in higher:
            continue
        lower_adapter = lower.get("adapter", _ADAPTER_DEFAULTS[section])
        if higher["adapter"] == lower_adapter:
            continue
        cleaned = dict(lower)
        for key in exclusive_by_adapter.get(lower_adapter, frozenset()):
            cleaned.pop(key, None)
        prepared[section] = cleaned
    return _deep_merge_json(prepared, overlay)


def _predicted_execution_id(*, delivery_run_id: str, work_id: str, attempt_number: int) -> str:
    key = idempotency_key(
        FX_START_EXECUTION,
        delivery_run_id=delivery_run_id,
        work_id=work_id,
        attempt_number=attempt_number,
    )
    return f"exec-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"


def _exec_entry_from_attempt(attempt: Mapping[str, Any]) -> dict[str, Any]:
    """`ScriptedExecution` script-entry translation shared by
    `build_scripted_adapters` (fully scripted) and `build_dispatch_ports`'
    scripted-execution/real-candidate combination (`execution.adapter ==
    'scripted'`, `candidate.adapter == 'git'`) -- the same per-attempt
    `outcome`/`states`/`artifact_refs`/`extensions` fields regardless of which
    `CandidatePort` observes the resulting candidate."""
    outcome = attempt.get("outcome", "completed")
    exec_entry: dict[str, Any] = {"outcome": outcome}
    if "states" in attempt:
        exec_entry["states"] = attempt["states"]
    if "artifact_refs" in attempt:
        exec_entry["artifact_refs"] = attempt["artifact_refs"]
    if "extensions" in attempt:
        exec_entry["extensions"] = attempt["extensions"]
    return exec_entry


def _json_equal(left: Any, right: Any) -> bool:
    """Representation-preserving equality for uninterpreted portable JSON."""
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def _bound_assurance_entry(
    assurance_entry: Mapping[str, Any], *, subject_identity: Mapping[str, Any]
) -> dict[str, Any]:
    """Corroborate and remove the CLI-only derived identity at binding time."""
    bound = dict(assurance_entry)
    derived = bound.pop("derived_identity", None)
    if derived is None:
        return bound
    matches = all(
        key in subject_identity and _json_equal(value, subject_identity[key])
        for key, value in derived.items()
    )
    if not matches:
        asserted_json = json.dumps(derived, sort_keys=True, separators=(",", ":"))
        bound_json = json.dumps(subject_identity, sort_keys=True, separators=(",", ":"))
        raise conflict_error(
            "scripted assurance derived_identity does not match the bound candidate subject_identity",
            next_steps=[
                f"asserted derived_identity: {asserted_json}",
                f"bound subject_identity: {bound_json}",
                "correct the assurance entry and re-dispatch, or inspect DEC-ABANDON-ATTEMPT",
            ],
            derived_identity=dict(derived),
            subject_identity=dict(subject_identity),
        )
    return bound


def build_scripted_adapters(
    config: Mapping[str, Any], *, delivery_run_id: str
) -> tuple[ScriptedExecution, ScriptedCandidate, ScriptedAssurance]:
    """Translate the `attempts` section of a dispatch config into the three
    scripted adapters' own native script formats.

    `TASK-M1-002`/`SCN-007`: pending/incremental mode is the M1a **default**
    dispatch mode, so this CLI-wired builder always constructs the
    `ScriptedExecution`/`ScriptedAssurance` adapters with `pending=True`
    (`docs/delivery/M1-delivery-ledger.md`'s "Pending/incremental mode is
    the M1a default"). An absent `attempts` key entirely means a fully
    incremental run: no attempt is scripted for any work, so every work's
    first dispatch starts and rests unsettled until the operator records
    real outcomes and re-dispatches. `tests/scenarios/support.py`'s
    `build_run` (used by `SCN-001`-`SCN-006`) constructs the scripted
    adapters directly with the M0 strict default (`pending=False`), so
    those golden scenarios and the conformance suite are unaffected by
    this default flip.
    """
    attempts_by_work: Mapping[str, Any] = config.get("attempts") or {}
    execution_capabilities = validate_capabilities(config.get("execution_capabilities", ()))

    execution_script: dict[str, list[dict[str, Any]]] = {}
    candidate_subjects: dict[str, dict[str, Any]] = {}
    assurance_script: dict[str, dict[str, Any]] = {}

    for work_id, attempts in attempts_by_work.items():
        execution_script[work_id] = []
        for attempt_index, attempt in enumerate(attempts):
            outcome = attempt.get("outcome", "completed")
            execution_script[work_id].append(_exec_entry_from_attempt(attempt))

            candidate_content = attempt.get("candidate")
            if outcome == "completed" and candidate_content is not None:
                attempt_number = attempt_index + 1
                execution_id = _predicted_execution_id(
                    delivery_run_id=delivery_run_id, work_id=work_id, attempt_number=attempt_number
                )
                candidate_subjects[execution_id] = {
                    "work_id": work_id,
                    "subject_identity": candidate_content,
                }
                assurance_entry = attempt.get("assurance")
                if assurance_entry is not None:
                    fingerprint = fingerprint_of(candidate_content)
                    assurance_script[fingerprint] = _bound_assurance_entry(
                        assurance_entry, subject_identity=candidate_content
                    )

    # pending=True: the CLI-wired M1a default (SCN-007) -- a work with no
    # recorded outcome for its next attempt starts and rests unsettled
    # rather than failing at dispatch. See this function's docstring.
    execution = ScriptedExecution(script=execution_script, capabilities=execution_capabilities, pending=True)
    candidate = ScriptedCandidate(subjects=candidate_subjects, current_by_work={})
    assurance = ScriptedAssurance(script=assurance_script, pending=True)
    return execution, candidate, assurance


def _build_command_assurance(assurance_cfg: Mapping[str, Any]) -> AssurancePort:
    return CommandAssurance(
        script=assurance_cfg["script"],
        cwd=assurance_cfg["cwd"],
        timeout_s=assurance_cfg.get("timeout_s", 300),
    )


def _observed_candidate_fingerprints(history: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Real-candidate counterpart of `build_scripted_adapters`'
    config-driven `fingerprint_of(candidate_content)` keying: a
    `GitDiffCandidate` fingerprint depends on real git state, unknowable at
    config-authoring time, so this reads the already-durable
    `FACT-CANDIDATE-OBSERVED` records off the run's own journal history
    (chronological `JournalPort.history()` order) instead, grouped by
    `work_id` -- one fingerprint per attempt that produced an assurable
    subject, in the order those attempts settled."""
    by_work: dict[str, list[str]] = {}
    for record in history:
        if record.get("kind") != KIND_FACT or record.get("id") != FACT_CANDIDATE_OBSERVED:
            continue
        data = record.get("data", {})
        work_id = data.get("work_id")
        fingerprint = data.get("fingerprint")
        if work_id and fingerprint:
            by_work.setdefault(work_id, []).append(fingerprint)
    return by_work


def _observed_candidate_bindings(
    history: Iterable[Mapping[str, Any]],
) -> dict[str, list[tuple[str, Mapping[str, Any]]]]:
    """Read fingerprint and identity together from durable identify effects.

    Issue #244 (SCN-014 regression): a `FX-IDENTIFY-CANDIDATE` record's
    `dispatch_result.candidate` is explicitly `null` for a non-binding null
    observation (`PORT-CAND-001`'s legitimate no-subject result) -- present
    as a key with a `None` value, not an absent key, so a bare
    `.get("candidate", {})` does NOT fall back to its default and instead
    returns `None`. Guard with `isinstance(candidate, Mapping)` before
    reading `fingerprint`/`subject_identity` off it, matching every other
    `dispatch_result.get("candidate")` reader in this codebase (`cli.show`,
    `cli.affordances`, `cli.main`, `cli.refs`, `cli.report`) -- this was the
    one call site that skipped the guard."""
    by_work: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for record in history:
        if record.get("kind") != "effect" or record.get("id") != FX_IDENTIFY_CANDIDATE:
            continue
        data = record.get("data", {})
        candidate = data.get("dispatch_result", {}).get("candidate")
        if not isinstance(candidate, Mapping):
            continue
        work_id = data.get("work_id")
        fingerprint = candidate.get("fingerprint")
        subject_identity = candidate.get("subject_identity")
        if work_id and fingerprint and isinstance(subject_identity, Mapping):
            by_work.setdefault(work_id, []).append((fingerprint, subject_identity))
    return by_work


def build_real_assurance_script(
    attempts_by_work: Mapping[str, Any], *, history: Iterable[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Build a `ScriptedAssurance` script keyed by REAL, journal-observed
    candidate fingerprints instead of config-predicted ones (module
    docstring, "Attempts-merge semantics"). Each `attempts[work_id]` entry
    (real-candidate mode: `assurance` only) is matched, in order, against
    that work's `FACT-CANDIDATE-OBSERVED` fingerprints in the order they
    were journaled -- attempt N's config-recorded verdict binds to attempt
    N's real candidate. An attempt position with no verdict recorded yet is
    skipped (nothing to bind); an attempt position with a verdict recorded
    before its candidate has been observed yet is also skipped -- there is
    nothing to bind it to *yet*, and `ScriptedAssurance(pending=True)`
    reports the ordinary SCN-007 pending wait until a later dispatch (once
    the candidate is observed) supplies the matching script entry."""
    history_records = list(history)
    observed = _observed_candidate_bindings(history_records)
    observed_fingerprints = _observed_candidate_fingerprints(history_records)
    script: dict[str, dict[str, Any]] = {}
    for work_id, attempts in attempts_by_work.items():
        bindings = observed.get(work_id, [])
        fingerprints = observed_fingerprints.get(work_id, [])
        for attempt_index, attempt in enumerate(attempts):
            assurance_entry = attempt.get("assurance")
            if assurance_entry is None or attempt_index >= len(fingerprints):
                continue
            if "derived_identity" not in assurance_entry:
                script[fingerprints[attempt_index]] = dict(assurance_entry)
                continue
            if attempt_index >= len(bindings):
                continue
            fingerprint, subject_identity = bindings[attempt_index]
            script[fingerprint] = _bound_assurance_entry(
                assurance_entry, subject_identity=subject_identity
            )
    return script


def build_dispatch_ports(
    config: Mapping[str, Any],
    *,
    delivery_run_id: str,
    intent_text: str,
    journal: Optional[JournalPort] = None,
) -> tuple[ExecutionPort, CandidatePort, AssurancePort]:
    """Select and construct the three ports `orc dispatch` wires into the
    `Orchestrator`, per the `execution`/`candidate`/`assurance` config
    blocks (module docstring, "Real-port selection"). The all-scripted
    default (every adapter `"scripted"`, or every key absent) delegates
    unchanged to `build_scripted_adapters` -- zero behavior change for
    every existing config. Execution has no real adapter (0.5.0/ADR-0005
    removed the `acp` `ExecutionPort` adapter), so past that fast path
    execution is always the same scripted construction below; the only
    real seats left are `candidate.adapter == "git"` and
    `assurance.adapter == "command"`, and `_validate_assurance_candidate_combo`
    requires `candidate.adapter == "git"` whenever assurance is `"command"`
    -- so the candidate wiring below never needs a scripted-candidate
    branch once past the fast path.

    Assurance stays the operator-recorded `ScriptedAssurance` path
    (`assurance` absent/`"scripted"`, the `TASK-M1-005` M1a+ default),
    keyed by real, journal-observed candidate fingerprints
    (`build_real_assurance_script`) when candidate is real, unless
    `assurance.adapter == "command"` selects the real `CommandAssurance`
    seat instead (no `attempts[work_id].assurance` entries are consulted
    on that path; a real `AssurancePort` derives its own verdict,
    `_attempt_allowed_keys` rejects a config author's attempt to also
    script one).

    `journal`, when given, supplies the already-durable history
    `build_real_assurance_script` reads to bind operator-recorded verdicts
    to real, journal-observed candidate fingerprints (only consulted on
    the scripted-assurance path). `None` (no journal yet -- not a case
    `orc dispatch` itself ever hits, since it always has one, but kept
    optional so other callers can construct ports without a journal when
    there is nothing to look up yet) yields an empty assurance script,
    matching a brand-new run before any candidate has ever been observed.
    """
    execution_cfg: Mapping[str, Any] = config.get("execution") or {}
    candidate_cfg: Mapping[str, Any] = config.get("candidate") or {}
    assurance_cfg: Mapping[str, Any] = config.get("assurance") or {}
    execution_adapter = execution_cfg.get("adapter", "scripted")
    candidate_adapter = candidate_cfg.get("adapter", "scripted")
    assurance_adapter = assurance_cfg.get("adapter", "scripted")

    if execution_adapter == "scripted" and candidate_adapter == "scripted" and assurance_adapter == "scripted":
        return build_scripted_adapters(config, delivery_run_id=delivery_run_id)

    attempts_by_work: Mapping[str, Any] = config.get("attempts") or {}
    execution_capabilities = validate_capabilities(config.get("execution_capabilities", ()))

    execution_script = {
        work_id: [_exec_entry_from_attempt(attempt) for attempt in attempts]
        for work_id, attempts in attempts_by_work.items()
    }
    execution: ExecutionPort = ScriptedExecution(
        script=execution_script, capabilities=execution_capabilities, pending=True
    )

    # candidate_adapter == "git" here unconditionally -- see docstring.
    candidate: CandidatePort = GitDiffCandidate(repo_path=candidate_cfg["repo_path"])

    assurance: AssurancePort
    if assurance_adapter == "command":
        assurance = _build_command_assurance(assurance_cfg)
    else:
        journal_history: Iterable[Mapping[str, Any]] = (
            journal.history(delivery_run_id=delivery_run_id) if journal is not None else ()
        )
        assurance_script = build_real_assurance_script(attempts_by_work, history=journal_history)
        assurance = ScriptedAssurance(script=assurance_script, pending=True)

    return execution, candidate, assurance


def build_mirror(config: Mapping[str, Any]) -> Optional[BeadsMirror]:
    """`mirror` (`TASK-M2-006`): `None` when the `mirror` key is absent (or
    `null`) -- the zero-behavior-change default every existing config
    already satisfies. `BeadsMirror` is constructed, never a `WorkGraphPort`
    -- this is not part of `build_dispatch_ports`'s `(execution, candidate,
    assurance)` triple; it is an independent, optional, write-only observer
    `cmd_dispatch` consults separately, after the ordinary dispatch loop has
    already run and journaled everything it is going to journal."""
    mirror_cfg = config.get("mirror")
    if not mirror_cfg:
        return None
    kwargs: dict[str, Any] = {"workspace": mirror_cfg["workspace"]}
    if "bd_bin" in mirror_cfg:
        kwargs["bd_bin"] = mirror_cfg["bd_bin"]
    if "project" in mirror_cfg:
        kwargs["project"] = mirror_cfg["project"]
    return BeadsMirror(**kwargs)


def _validate_max_attempts(value: Any, *, source: str) -> int:
    """`INV-019` requires any configured attempt budget be finite (and, by
    the same "budget" intent, positive -- a run that can never attempt
    anything is not a bounded budget, it is a broken one). BUG-2 dogfood
    finding: 0 is falsy in Python, so a naive `x or default` precedence
    chain silently discards an explicit `max_attempts: 0` (or
    `--max-attempts 0`) and replaces it with the default instead of
    rejecting it -- fail closed with a canonical error instead."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise validation_error(
            f"max_attempts ({source}) must be a positive integer, got {value!r}",
            source=source,
            max_attempts=value,
        )
    return value


def build_run_config(config: Mapping[str, Any], *, max_attempts_override: int | None) -> RunConfig:
    # BUG-2: explicit `is not None` precedence (flag > config > default) --
    # NOT `or`-chaining, which would treat an explicit 0 as absent.
    if max_attempts_override is not None:
        max_attempts = _validate_max_attempts(max_attempts_override, source="--max-attempts flag")
    elif config.get("max_attempts") is not None:
        max_attempts = _validate_max_attempts(config["max_attempts"], source="config max_attempts")
    else:
        max_attempts = RunConfig().max_attempts
    resume_capability = config.get("resume_capability")
    return RunConfig(max_attempts=max_attempts, resume_capability=resume_capability)


__all__ = [
    "build_dispatch_ports",
    "build_mirror",
    "build_real_assurance_script",
    "build_run_config",
    "build_scripted_adapters",
    "deep_merge_config",
    "load_config",
    "load_config_overlay",
    "load_repo_profile",
    "record_assurance_entry",
    "record_execution_outcome_entry",
    "validate_config",
]
