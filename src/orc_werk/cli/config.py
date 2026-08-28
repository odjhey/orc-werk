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

Because `ScriptedCandidate` scripts are keyed by `execution_id`, and
`ScriptedExecution` derives `execution_id` deterministically from the
`FX-START-EXECUTION` idempotency key (`CONF-EXEC-001`, documented in that
adapter's own module docstring as
``execution_id = f"exec-{sha256(idempotency_key)[:16]}"``), this module
predicts each attempt's `execution_id` up front via the same public
`orc_werk.core.idempotency.idempotency_key` derivation so a human-authored
config never has to spell out a hash by hand.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate, fingerprint_of
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app.orchestrator import RunConfig
from orc_werk.core.effects import FX_START_EXECUTION
from orc_werk.core.errors import validation_error
from orc_werk.core.facts import ASSURANCE_VERDICTS, EXEC_OUTCOMES
from orc_werk.core.idempotency import idempotency_key
from orc_werk.core.portable import is_portable
from orc_werk.ports.capabilities import validate_capabilities

# #17 (re-scoped, docs/delivery/M1-delivery-ledger.md): the CLI-owned,
# non-normative config schema this module's own docstring documents.
# Load-time strict validation rejects unknown top-level keys and
# structurally malformed `attempts` shapes -- it never rejects an *absent*
# `attempts` key or a planned Work with no entry (the valid
# fully-incremental/SCN-007-pending case).
_TOP_LEVEL_KEYS = frozenset(
    {"run_id", "max_attempts", "resume_capability", "execution_capabilities", "plan", "attempts"}
)
_ATTEMPT_ENTRY_KEYS = frozenset({"outcome", "candidate", "assurance", "states", "artifact_refs", "extensions"})
_ASSURANCE_ENTRY_KEYS = frozenset({"verdict", "states", "evidence_refs", "extensions"})


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


def _validate_attempts(attempts: Any) -> None:
    """#17 (re-scoped): reject structurally malformed `attempts` shapes at
    config load time -- a non-mapping `attempts` value, a non-list
    per-work attempts value, a non-mapping attempt entry, an unknown key
    inside an entry, or an invalid `outcome`/`assurance.verdict` value. An
    *absent* `attempts` key, or a planned Work with no entry at all, is the
    valid fully-incremental case (`SCN-007`'s pending default) and MUST NOT
    be rejected -- see the M1-delivery-ledger #17 re-scope annotation."""
    if attempts is None:
        return
    if not isinstance(attempts, Mapping):
        raise validation_error(
            f"config 'attempts' must be a JSON object keyed by work_id, got {type(attempts).__name__}",
            path="<config>.attempts",
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
            unknown = sorted(set(entry) - _ATTEMPT_ENTRY_KEYS)
            if unknown:
                raise validation_error(
                    f"config value at {entry_path} has unknown key(s): {', '.join(unknown)}",
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
    _validate_attempts(data.get("attempts"))
    return data


def _predicted_execution_id(*, delivery_run_id: str, work_id: str, attempt_number: int) -> str:
    key = idempotency_key(
        FX_START_EXECUTION,
        delivery_run_id=delivery_run_id,
        work_id=work_id,
        attempt_number=attempt_number,
    )
    return f"exec-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]}"


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
            exec_entry: dict[str, Any] = {"outcome": outcome}
            if "states" in attempt:
                exec_entry["states"] = attempt["states"]
            if "artifact_refs" in attempt:
                exec_entry["artifact_refs"] = attempt["artifact_refs"]
            execution_script[work_id].append(exec_entry)

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


__all__ = ["build_run_config", "build_scripted_adapters", "load_config"]
