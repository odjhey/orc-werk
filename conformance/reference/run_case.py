#!/usr/bin/env python3
"""Reference driver for the portable conformance kit.

`CONFORMANCE-PORTABLE-KIT` (`docs/conformance/portable-kit.md`) is the
normative source; this file is the reference-implementation adapter it
describes, not the contract itself.

Wire contract (the entire language-neutral boundary):

  stdin  -- exactly one JSON object: `{"delivery_run_id": "...", "history":
            [envelope, ...]}`, where each `envelope` is a canonical
            `PORT-JOURNAL-ENVELOPE` record -- the exact on-disk shape a
            real `.orc/*/journal.jsonl` line has:
            `{schema_version, seq, delivery_run_id, kind, id, data,
            extensions}`, `kind` one of `"fact"`/`"decision"`/`"effect"`,
            ordered by `seq`. This is not a Python-internal shape and not
            a driver-specific convenience format -- it is the same
            envelope every real adapter (`adapters/jsonl/journal.py`,
            `adapters/memory/journal.py`) reads back.

  stdout -- exactly one JSON object: the observed-result envelope
            (`kit_version`, `outcome`, and either `projection`+`decisions`
            for `"ok"` or `error`+`failing_*` for `"error"`).

This driver performs the SAME operation `PORT-JOURNAL-005 load_projection`
performs on a real journal (`CONF-JOURNAL-003`'s replay-determinism
guarantee): it derives both run-scoped budgets from the history's own
`FX-CREATE-WORK` effect record (`orc_werk.core.reducer
.journaled_max_attempts` / `.journaled_max_assurance_attempts` --
including their documented legacy-fallback rule), then folds every `fact`
envelope, in `seq` order, under those derived budgets
(`orc_werk.core.reducer.apply_fact`) -- never a caller-supplied policy
override, exactly as `SCN-008`'s single-authority ruling (issue #240)
requires. `decide()` runs after the fold, per Work, to report the
currently-applicable next Decision/Effect(s) (or none).

Any other implementation that accepts the same stdin shape and emits the
same stdout shape may be substituted for this file via
`checker.py --driver-cmd`. This file exists to be read for its shape, not
its Python: no case, expectation, or comparison rule lives here.

This process is intentionally dependency-free beyond the stdlib and the
`orc_werk.core` package it drives -- no third-party package, no filesystem
side effect beyond reading stdin/writing stdout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Resolve the sibling `src/` tree by path so this driver runs from a bare
# checkout with no install step and no reliance on the caller's PYTHONPATH
# (though `PYTHONPATH=src python3 conformance/reference/run_case.py` also
# works unchanged, matching `scripts/check.sh`'s convention).
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from orc_werk.core.errors import CoreError, canonical_error  # noqa: E402
from orc_werk.core.errors import ERR_VALIDATION  # noqa: E402
from orc_werk.core.facts import FACT_INTENT_SUBMITTED  # noqa: E402
from orc_werk.core.policy import decide  # noqa: E402
from orc_werk.core.reducer import (  # noqa: E402
    apply_fact,
    journaled_max_assurance_attempts,
    journaled_max_attempts,
)
from orc_werk.core.serialization import KIND_FACT, fact_from_envelope  # noqa: E402

KIT_VERSION = 1


def run(case_input: dict[str, Any]) -> dict[str, Any]:
    delivery_run_id = case_input["delivery_run_id"]
    history = case_input.get("history", [])

    # Single-authority budget derivation (issue #240 R1, `SCN-008`,
    # `SCN-021`'s legacy-fallback amendment): read straight off the raw
    # history, never a field the caller supplies alongside it.
    max_attempts = journaled_max_attempts(history)
    max_assurance_attempts = journaled_max_assurance_attempts(history)

    intent_id = None
    works: dict[str, Any] = {}
    fact_index = -1

    for record in history:
        if record.get("kind") != KIND_FACT:
            continue
        fact_index += 1
        try:
            fact = fact_from_envelope(record)
        except (CoreError, ValueError) as exc:
            return _error_result(exc, fact_index=fact_index, fact_id=record.get("id"))

        if fact.id == FACT_INTENT_SUBMITTED:
            intent_id = fact.field("intent_id")
            continue

        work_id = fact.data.get("work_id")
        try:
            works[work_id] = apply_fact(
                works.get(work_id),
                fact,
                max_attempts=max_attempts,
                max_assurance_attempts=max_assurance_attempts,
            )
        except (CoreError, ValueError) as exc:
            return _error_result(
                exc, fact_index=fact_index, fact_id=fact.id, work_id=work_id
            )

    decisions: dict[str, Any] = {}
    for work_id, projection in works.items():
        outcome = decide(
            projection,
            max_attempts=max_attempts,
            max_assurance_attempts=max_assurance_attempts,
        )
        decisions[work_id] = (
            {
                "decision": outcome.decision.to_dict(),
                "effects": [effect.to_dict() for effect in outcome.effects],
            }
            if outcome is not None
            else None
        )

    return {
        "kit_version": KIT_VERSION,
        "outcome": "ok",
        "delivery_run_id": delivery_run_id,
        "intent_id": intent_id,
        "derived_max_attempts": max_attempts,
        "derived_max_assurance_attempts": max_assurance_attempts,
        "projection": {work_id: proj.to_dict() for work_id, proj in works.items()},
        "decisions": decisions,
    }


def _error_result(
    exc: Exception, *, fact_index: int, fact_id: Any, work_id: Any = None
) -> dict[str, Any]:
    """Every failure this driver can hit while folding history is a
    canonical error (`CONTRACT-ERRORS`): a plain `ValueError` (raised by
    `Fact.__post_init__`/`fact_from_envelope` for a malformed record --
    unknown id, missing required field, non-portable data, or an invalid
    enum value such as a malformed assurance verdict) is normalized to
    `ERR-VALIDATION` rather than surfaced as an uncaught traceback; a
    `CoreError` already carries its own canonical error id/message."""
    error = exc.to_canonical() if isinstance(exc, CoreError) else canonical_error(
        ERR_VALIDATION, str(exc)
    )
    return {
        "kit_version": KIT_VERSION,
        "outcome": "error",
        "failing_fact_index": fact_index,
        "failing_fact_id": fact_id,
        "failing_work_id": work_id,
        "error": error,
    }


def main() -> int:
    case_input = json.load(sys.stdin)
    result = run(case_input)
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
