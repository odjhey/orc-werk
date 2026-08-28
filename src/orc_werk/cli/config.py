"""CLI dispatch-config loading/translation (`TASK-M0-005`).

The `orc dispatch --config <path>` config file is a portable JSON document
declaring the scripted-adapter scripts and (optionally) a multi-work plan
for one run. This module is CLI-owned composition, not a canonical
protocol shape (`ARCH-REPOSITORY-STRUCTURE`: only `orc_werk.cli` composes
adapters); the schema below is this reference CLI's own invention, not a
normative contract.

## Config schema

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
  precisely so callers like this one never have to guess it); `assurance`,
  when present, supplies that candidate's scripted verdict
  (`ScriptedAssurance`).
- `plan` is an optional `PORT-WORK-001` multi-work plan (needed to exercise
  a fan-in run like `SCN-005` from the CLI); defaults to
  `orc_werk.app.default_single_work_plan()`.

## Real-port selection (`execution`/`candidate`, `TASK-M1-005` CLI wiring)

Two further optional top-level objects select real (non-scripted) ports in
place of `ScriptedExecution`/`ScriptedCandidate`, per `M1-delivery-ledger`'s
M1b acceptance ("`orc dispatch \"<real task>\"` produces a real candidate
authored by a Pi run driven over ACP"):

```json
{
  "execution": {"adapter": "acp", "cwd": "/abs/worktree", "agent": "pi",
                 "thought_level": "low", "model": null, "approve_all": false},
  "candidate": {"adapter": "git", "repo_path": "/abs/worktree"}
}
```

- `execution.adapter`: `"scripted"` (default) or `"acp"`. `"acp"` selects
  `orc_werk.adapters.acp.execution.AcpExecution`, keyed exactly to that
  constructor's real parameters (`agent`, `cwd`, `thought_level`,
  `approve_all`; `capabilities` is instead reused from this config's
  existing top-level `execution_capabilities` key rather than a duplicate
  field). `cwd` is REQUIRED when `adapter == "acp"` -- there is no safe
  default working directory for a real agent to run in. `model`, when
  given, is not an `AcpExecution` constructor parameter -- it is this
  module's own default for the per-call `execution_request['model']` field
  (see "Real-port wiring" below). No `session_prefix` key: `AcpExecution`
  has no such constructor parameter (session names are always derived
  deterministically from the `INV-020` idempotency key), so one is not
  invented here per `CLAUDE.md` #3.
- `candidate.adapter`: `"scripted"` (default) or `"git"`. `"git"` selects
  `orc_werk.adapters.git.candidate.GitDiffCandidate(repo_path=...)`.
  `repo_path` is REQUIRED when `adapter == "git"`.
- **Constraint**: `execution.adapter == "acp"` REQUIRES `candidate.adapter
  == "git"` -- rejected otherwise. A real agent execution's outcome cannot
  be matched against a config-scripted candidate (`ScriptedCandidate`'s
  `subjects` map is keyed by a *predicted* `execution_id` that only
  `ScriptedExecution`'s deterministic idempotency-hash derivation can
  produce; `AcpExecution`'s `execution_id` shape is unrelated and
  unpredictable at config-authoring time).
- **Attempts-merge semantics when either port is real** (the PR body's
  "attempts-merge semantics" decision, restated here as it governs load-time
  validation): when `candidate.adapter == "git"`, an `attempts[work_id]`
  entry may carry ONLY `assurance` -- never `outcome`/`candidate`/`states`/
  `artifact_refs` for that work, because the real `CandidatePort` supplies
  those and a config-declared value would be a silently-ignored footgun.
  When `execution.adapter` is additionally `"acp"`, this is the *only*
  allowed key. When `execution.adapter` stays `"scripted"` (candidate real,
  execution still scripted -- a valid, lesser combination useful for
  testing the git-candidate wiring without a live agent), `outcome`/
  `states`/`artifact_refs` remain allowed (they still drive
  `ScriptedExecution`), just never `candidate`.

Because `ScriptedCandidate` scripts are keyed by `execution_id`, and
`ScriptedExecution` derives `execution_id` deterministically from the
`FX-START-EXECUTION` idempotency key (`CONF-EXEC-001`, documented in that
adapter's own module docstring as
``execution_id = f"exec-{sha256(idempotency_key)[:16]}"``), this module
predicts each attempt's `execution_id` up front via the same public
`orc_werk.core.idempotency.idempotency_key` derivation so a human-authored
config never has to spell out a hash by hand.

## Beads mirror (optional, write-only, `TASK-M2-006`)

A further optional top-level object wires an optional, write-only
projection of run/work state and briefs into a shared `bd` database
(`docs/adapters/beads/mapping.md` has the full design):

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
  init` in (this CLI never runs `bd init` itself, mirroring the
  `no-mistakes` adapter's own "never `axi init`s a repo" precedent).
  `mirror.bd_bin` optionally overrides the `bd` binary name/path (default
  `"bd"`, resolved via `PATH`).
- `briefs` is a CLI-owned, non-canonical sibling to `plan` (`PORT-WORK-001`
  itself carries no brief/description field -- `CONTRACT-DURABILITY`'s
  multi-work-brief row stays adapter-owned, not core) keyed by `work_id`.
  A work with no entry falls back to the run's own intent text -- never an
  empty description when the run-level intent text is available (see the
  mapping doc's brief-fallback note).
- A degraded mirror (one or more `bd` invocations failed) is NEVER a
  dispatch failure: `cmd_dispatch` prints a `mirror: degraded (...)` note
  to stderr and returns the SAME exit code the run would have had without
  a mirror configured at all (mirror failures MUST NEVER break the
  delivery loop, per the task card).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from orc_werk.adapters.acp.execution import AcpExecution
from orc_werk.adapters.beads.mirror import BeadsMirror
from orc_werk.adapters.git.candidate import GitDiffCandidate
from orc_werk.adapters.no_mistakes.assurance import NoMistakesAssurance
from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate, fingerprint_of
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app.orchestrator import RunConfig
from orc_werk.core.effects import FX_START_EXECUTION
from orc_werk.core.errors import validation_error
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
    }
)
_ATTEMPT_ENTRY_KEYS = frozenset({"outcome", "candidate", "assurance", "states", "artifact_refs", "extensions"})
_ASSURANCE_ENTRY_KEYS = frozenset({"verdict", "states", "evidence_refs", "extensions"})

# `execution`/`candidate`/`assurance` real-port selection (module
# docstring, "Real-port selection" section). Keyed exactly to what each
# real adapter constructor genuinely accepts -- `model` is the one
# exception for `execution`, threaded through to the per-call
# `execution_request` instead (see `_build_acp_execution`), and `adapter`
# is this CLI's own selector, not an adapter constructor parameter.
_EXECUTION_CONFIG_KEYS = frozenset({"adapter", "agent", "cwd", "thought_level", "model", "approve_all"})
_EXECUTION_ADAPTER_ONLY_KEYS = _EXECUTION_CONFIG_KEYS - {"adapter"}
_EXECUTION_ADAPTERS = frozenset({"scripted", "acp"})
_CANDIDATE_CONFIG_KEYS = frozenset({"adapter", "repo_path"})
_CANDIDATE_ADAPTERS = frozenset({"scripted", "git"})
_ASSURANCE_CONFIG_KEYS = frozenset({"adapter", "repo_path"})
_ASSURANCE_ADAPTERS = frozenset({"scripted", "no-mistakes"})
# `mirror` (`TASK-M2-006`, module docstring "Beads mirror" section): unlike
# execution/candidate/assurance, there is no "scripted" default -- absent
# `mirror` means no mirror at all, not a null-object adapter. `workspace`
# is keyed exactly to `BeadsMirror`'s one required constructor parameter;
# `bd_bin` maps to its optional one. No `timeout_s` key exposed at this
# layer either, matching the no-mistakes precedent's "don't expose every
# constructor parameter" restraint (`CLAUDE.md` #3).
_MIRROR_CONFIG_KEYS = frozenset({"adapter", "workspace", "bd_bin"})
_MIRROR_ADAPTERS = frozenset({"beads"})


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
        raise validation_error(
            f"config value at <config>.execution.adapter is not one of {sorted(_EXECUTION_ADAPTERS)}: {adapter!r}",
            path="<config>.execution.adapter",
        )
    if adapter == "scripted":
        present_only = sorted(_EXECUTION_ADAPTER_ONLY_KEYS & set(value))
        if present_only:
            raise validation_error(
                f"config value(s) at <config>.execution {present_only} require execution.adapter == 'acp'",
                path="<config>.execution",
                unknown_keys=present_only,
            )
        return
    cwd = value.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        raise validation_error(
            "config value at <config>.execution.cwd is required (a non-empty string) when "
            "execution.adapter == 'acp' -- AcpExecution has no safe default working directory",
            path="<config>.execution.cwd",
        )
    agent = value.get("agent")
    if agent is not None and (not isinstance(agent, str) or not agent):
        raise validation_error(
            "config value at <config>.execution.agent must be a non-empty string when present",
            path="<config>.execution.agent",
        )
    thought_level = value.get("thought_level")
    if thought_level is not None and not isinstance(thought_level, str):
        raise validation_error(
            "config value at <config>.execution.thought_level must be a string when present",
            path="<config>.execution.thought_level",
        )
    model = value.get("model")
    if model is not None and not isinstance(model, str):
        raise validation_error(
            "config value at <config>.execution.model must be a string when present",
            path="<config>.execution.model",
        )
    approve_all = value.get("approve_all")
    if approve_all is not None and not isinstance(approve_all, bool):
        raise validation_error(
            "config value at <config>.execution.approve_all must be a boolean when present",
            path="<config>.execution.approve_all",
        )


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
        if "repo_path" in value:
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
        raise validation_error(
            f"config value at <config>.assurance.adapter is not one of {sorted(_ASSURANCE_ADAPTERS)}: {adapter!r}",
            path="<config>.assurance.adapter",
        )
    if adapter == "scripted":
        if "repo_path" in value:
            raise validation_error(
                "config value at <config>.assurance.repo_path requires assurance.adapter == 'no-mistakes'",
                path="<config>.assurance.repo_path",
            )
        return
    repo_path = value.get("repo_path")
    if not isinstance(repo_path, str) or not repo_path:
        raise validation_error(
            "config value at <config>.assurance.repo_path is required (a non-empty string) when "
            "assurance.adapter == 'no-mistakes' -- NoMistakesAssurance has no safe default repository",
            path="<config>.assurance.repo_path",
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


def _validate_briefs(value: Any) -> None:
    """`briefs` (`TASK-M2-006`): a CLI-owned, non-canonical `work_id ->
    brief text` mapping, entirely optional and independent of `mirror` --
    a config MAY supply briefs even when no mirror is configured (they are
    simply unused in that case), matching how `attempts` is validated
    independently of which ports are real."""
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


def _validate_execution_candidate_combo(execution_cfg: Any, candidate_cfg: Any) -> None:
    """`execution.adapter == 'acp'` REQUIRES `candidate.adapter == 'git'`
    (module docstring, "Real-port selection"): a real agent execution's
    outcome cannot be matched against a config-scripted candidate, whose
    `subjects` map is keyed by a predicted `execution_id` only
    `ScriptedExecution`'s deterministic derivation can produce."""
    execution_adapter = (execution_cfg or {}).get("adapter", "scripted") if isinstance(execution_cfg, Mapping) else "scripted"
    if execution_adapter != "acp":
        return
    candidate_adapter = (candidate_cfg or {}).get("adapter", "scripted") if isinstance(candidate_cfg, Mapping) else "scripted"
    if candidate_adapter != "git":
        raise validation_error(
            "config execution.adapter == 'acp' requires candidate.adapter == 'git' "
            "(a real agent execution cannot be matched against a config-scripted candidate)",
            path="<config>.candidate.adapter",
            execution_adapter=execution_adapter,
            candidate_adapter=candidate_adapter,
        )


def _validate_assurance_candidate_combo(assurance_cfg: Any, candidate_cfg: Any) -> None:
    """`assurance.adapter == 'no-mistakes'` REQUIRES `candidate.adapter ==
    'git'` (`TASK-M2-001`, mirroring `_validate_execution_candidate_combo`'s
    acp-requires-git precedent exactly): `no-mistakes` reviews real git
    state at a configured `repo_path`; a config-scripted candidate's
    `subject_identity` (and therefore fingerprint) would not correspond to
    anything `no-mistakes` actually reviewed, so a settled verdict could
    never be honestly bound to it (`INV-007`)."""
    assurance_adapter = (
        (assurance_cfg or {}).get("adapter", "scripted") if isinstance(assurance_cfg, Mapping) else "scripted"
    )
    if assurance_adapter != "no-mistakes":
        return
    candidate_adapter = (candidate_cfg or {}).get("adapter", "scripted") if isinstance(candidate_cfg, Mapping) else "scripted"
    if candidate_adapter != "git":
        raise validation_error(
            "config assurance.adapter == 'no-mistakes' requires candidate.adapter == 'git' "
            "(a real assurance verdict cannot be bound to a config-scripted candidate)",
            path="<config>.candidate.adapter",
            assurance_adapter=assurance_adapter,
            candidate_adapter=candidate_adapter,
        )


def load_config(path: str) -> Mapping[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise validation_error(f"config file is not valid JSON: {path}", path=path) from exc
    if not isinstance(data, Mapping):
        raise validation_error(f"config file must contain a JSON object: {path}", path=path)
    _require_portable(data, path="<config>")
    _validate_top_level_keys(data)
    _validate_execution_config(data.get("execution"))
    _validate_candidate_config(data.get("candidate"))
    _validate_assurance_config(data.get("assurance"))
    _validate_mirror_config(data.get("mirror"))
    _validate_briefs(data.get("briefs"))
    _validate_execution_candidate_combo(data.get("execution"), data.get("candidate"))
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
    `outcome`/`states`/`artifact_refs` fields regardless of which
    `CandidatePort` observes the resulting candidate."""
    outcome = attempt.get("outcome", "completed")
    exec_entry: dict[str, Any] = {"outcome": outcome}
    if "states" in attempt:
        exec_entry["states"] = attempt["states"]
    if "artifact_refs" in attempt:
        exec_entry["artifact_refs"] = attempt["artifact_refs"]
    return exec_entry


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
                    assurance_script[fingerprint] = dict(assurance_entry)

    # pending=True: the CLI-wired M1a default (SCN-007) -- a work with no
    # recorded outcome for its next attempt starts and rests unsettled
    # rather than failing at dispatch. See this function's docstring.
    execution = ScriptedExecution(script=execution_script, capabilities=execution_capabilities, pending=True)
    candidate = ScriptedCandidate(subjects=candidate_subjects, current_by_work={})
    assurance = ScriptedAssurance(script=assurance_script, pending=True)
    return execution, candidate, assurance


class _IntentPromptExecution(ExecutionPort):
    """CLI-local decorator around a real `ExecutionPort` (`AcpExecution`)
    that fills in a usable prompt for `orc_werk.app.Orchestrator`'s
    `start()`/`send()` calls.

    Why this exists: `Orchestrator` always calls
    `execution.start(work_id=..., execution_request={}, idempotency_key=...)`
    -- confirmed by reading both of its call sites (`_start_or_resume_execution`
    and the `FX_START_EXECUTION` replay branch in `_replay_effect_record`);
    `execution_request` is declared opaque to core per `PORT-EXEC-001`, and
    neither `app` nor `core` threads any per-work request payload through
    it. `AcpExecution.start()` requires `execution_request['prompt']` to be
    a non-empty string. Since `app`/`core`/`adapters` are out of scope for
    this task (CLI + docs + tests only), this class composes around the
    real adapter instead of changing it or `Orchestrator`: it fills in
    `{"prompt": <the run's intent text>}` (and an optional configured
    default `model`) whenever the caller passes an empty/absent `prompt`,
    then delegates unchanged. Every other operation passes straight
    through -- this is composition, not a reimplementation."""

    def __init__(self, inner: ExecutionPort, *, intent_text: str, model: Optional[str] = None) -> None:
        self._inner = inner
        self._intent_text = intent_text
        self._model = model

    def capabilities(self) -> frozenset[str]:
        return self._inner.capabilities()

    def _filled_request(self, request: Mapping[str, Any]) -> dict[str, Any]:
        filled = dict(request)
        if not filled.get("prompt"):
            filled["prompt"] = self._intent_text
        if self._model is not None and "model" not in filled:
            filled["model"] = self._model
        return filled

    def start(self, *, work_id: str, execution_request: Mapping[str, Any], idempotency_key: str) -> Any:
        return self._inner.start(
            work_id=work_id,
            execution_request=self._filled_request(execution_request),
            idempotency_key=idempotency_key,
        )

    def inspect(self, *, execution_id: str) -> Any:
        return self._inner.inspect(execution_id=execution_id)

    def send(self, *, execution_id: str, message: Mapping[str, Any]) -> None:
        self._inner.send(execution_id=execution_id, message=self._filled_request(message))

    def cancel(self, *, execution_id: str) -> None:
        self._inner.cancel(execution_id=execution_id)

    def resume(self, *, execution_id: str, resume_request: Mapping[str, Any]) -> Any:
        return self._inner.resume(execution_id=execution_id, resume_request=resume_request)


class _IntentRequirementsAssurance(AssurancePort):
    """CLI-local decorator around a real `AssurancePort` (`NoMistakesAssurance`)
    that fills in a usable `requirements['intent']` for `orc_werk.app.
    Orchestrator`'s `request()` call -- the exact same rationale as
    `_IntentPromptExecution` above, one port over: `Orchestrator.
    _dispatch_policy_effect`'s `FX_START_ASSURANCE` branch always calls
    `self.assurance.request(candidate=candidate, requirements={}, ...)`
    (confirmed by reading `orchestrator.py`) -- `requirements` is declared
    opaque to core per `PORT-ASSURE-001`, and neither `app` nor `core`
    threads a per-work request payload through it. `NoMistakesAssurance.
    request()` requires `requirements['intent']` to be a non-empty string.
    Since `app`/`core`/`adapters` are out of scope for `TASK-M2-001` (CLI +
    docs + tests only, mirroring `TASK-M1-005`'s own scope note), this
    class composes around the real adapter instead of changing it or
    `Orchestrator`: it fills in `{"intent": <the run's intent text>}`
    whenever the caller passes an empty/absent `intent`, then delegates
    unchanged."""

    def __init__(self, inner: AssurancePort, *, intent_text: str) -> None:
        self._inner = inner
        self._intent_text = intent_text

    def capabilities(self) -> frozenset[str]:
        return self._inner.capabilities()

    def request(self, *, candidate: Any, requirements: Mapping[str, Any], idempotency_key: str) -> Any:
        filled = dict(requirements)
        if not filled.get("intent"):
            filled["intent"] = self._intent_text
        return self._inner.request(candidate=candidate, requirements=filled, idempotency_key=idempotency_key)

    def inspect(self, *, assurance_id: str) -> Any:
        return self._inner.inspect(assurance_id=assurance_id)


def _build_no_mistakes_assurance(assurance_cfg: Mapping[str, Any], *, intent_text: str) -> AssurancePort:
    """`NoMistakesAssurance`, constructed from exactly the `assurance`
    config keys that constructor genuinely accepts, wrapped in
    `_IntentRequirementsAssurance` so it receives a usable `--intent` text
    despite the orchestrator's always-empty `requirements`."""
    inner = NoMistakesAssurance(repo_path=assurance_cfg["repo_path"])
    return _IntentRequirementsAssurance(inner, intent_text=intent_text)


def _build_acp_execution(
    execution_cfg: Mapping[str, Any], *, intent_text: str, capabilities: Iterable[str]
) -> ExecutionPort:
    """`AcpExecution`, constructed from exactly the `execution` config keys
    that constructor genuinely accepts (module docstring, "Real-port
    selection"), wrapped in `_IntentPromptExecution` so it receives a
    usable prompt despite the orchestrator's always-empty
    `execution_request`."""
    kwargs: dict[str, Any] = {"cwd": execution_cfg["cwd"]}
    if "agent" in execution_cfg:
        kwargs["agent"] = execution_cfg["agent"]
    if "thought_level" in execution_cfg:
        kwargs["thought_level"] = execution_cfg["thought_level"]
    if "approve_all" in execution_cfg:
        kwargs["approve_all"] = execution_cfg["approve_all"]
    caps = tuple(capabilities)
    if caps:
        kwargs["capabilities"] = caps
    inner = AcpExecution(**kwargs)
    return _IntentPromptExecution(inner, intent_text=intent_text, model=execution_cfg.get("model"))


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
    observed = _observed_candidate_fingerprints(history)
    script: dict[str, dict[str, Any]] = {}
    for work_id, attempts in attempts_by_work.items():
        fingerprints = observed.get(work_id, [])
        for attempt_index, attempt in enumerate(attempts):
            assurance_entry = attempt.get("assurance")
            if assurance_entry is None or attempt_index >= len(fingerprints):
                continue
            script[fingerprints[attempt_index]] = dict(assurance_entry)
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
    every existing config. Past that fast path, `candidate.adapter ==
    "git"` always (the only other config `load_config`'s cross-field
    validation -- `_validate_execution_candidate_combo`,
    `_validate_assurance_candidate_combo` -- allows once `execution` or
    `assurance` is real), so the candidate wiring below never needs a
    scripted-candidate branch.

    `assurance.adapter == "no-mistakes"` (`TASK-M2-001`) selects
    `NoMistakesAssurance` -- an automatic, real verdict seat, replacing the
    operator-recorded-verdict `ScriptedAssurance` path entirely for that
    run (no `attempts[work_id].assurance` entries are consulted; a real
    `AssurancePort` derives its own verdict, `_attempt_allowed_keys`
    rejects a config author's attempt to also script one). Otherwise
    (`assurance` absent/`"scripted"`, the `TASK-M1-005` M1a+ default)
    assurance stays the existing operator-recorded `ScriptedAssurance`
    path, keyed by real, journal-observed candidate fingerprints
    (`build_real_assurance_script`) when candidate is real.

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

    execution: ExecutionPort
    if execution_adapter == "acp":
        execution = _build_acp_execution(
            execution_cfg, intent_text=intent_text, capabilities=execution_capabilities
        )
    else:
        execution_script = {
            work_id: [_exec_entry_from_attempt(attempt) for attempt in attempts]
            for work_id, attempts in attempts_by_work.items()
        }
        execution = ScriptedExecution(script=execution_script, capabilities=execution_capabilities, pending=True)

    # candidate_adapter == "git" here unconditionally -- see docstring.
    candidate: CandidatePort = GitDiffCandidate(repo_path=candidate_cfg["repo_path"])

    assurance: AssurancePort
    if assurance_adapter == "no-mistakes":
        assurance = _build_no_mistakes_assurance(assurance_cfg, intent_text=intent_text)
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
    "load_config",
]
