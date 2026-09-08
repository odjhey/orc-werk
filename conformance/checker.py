#!/usr/bin/env python3
"""Portable conformance kit checker (`CONFORMANCE-PORTABLE-KIT`).

Runs every case named in `manifest.json` through a driver command (default:
the reference driver, `reference/run_case.py`, invoked as a subprocess --
never imported, so any other language's binary is a drop-in substitute via
`--driver-cmd`) and compares the driver's observed stdout against each
case's `expected` block using the subset-equality rule this file documents
and `docs/conformance/portable-kit.md` states normatively:

  For every key present in `expected`, the same key MUST be present in
  `observed` with an equal value (dicts compared key-by-key recursively
  under the same rule; lists compared element-by-element, same length,
  same rule per element). A key `expected` does not mention is never
  checked and never causes a mismatch. Missing or changed keys `expected`
  DOES mention are always a mismatch -- this is what stops a wrong or
  no-op driver from passing by returning unrelated extra fields.

Usage:
  python3 checker.py                     # run every case, exit 0 iff all pass
  python3 checker.py CASE-001-happy-path # run one case by id
  python3 checker.py --driver-cmd "go run ./cmd/kit-driver"
  python3 checker.py --probe             # falsification self-test (see below)

`--probe` proves this checker is not a rubber stamp: it takes real driver
output for a handful of real cases and checks that DELIBERATELY WRONG
`expected` blocks -- wrong acceptance, wrong candidate binding, wrong
pending/terminal state, wrong replay-budget outcome -- are correctly
reported as mismatches. A probe that is *not* rejected is a bug in this
checker and fails the run.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

KIT_DIR = Path(__file__).resolve().parent
DEFAULT_DRIVER_CMD = [sys.executable, str(KIT_DIR / "reference" / "run_case.py")]


def subset_equal(expected: Any, observed: Any, path: str = "$") -> list[str]:
    """Return a list of human-readable mismatch descriptions; empty means
    `expected` is satisfied by `observed` under the subset-equality rule.

    Type-strict on the JSON boolean/number distinction: Python's `bool` is
    a subclass of `int`, so a bare `==` would let an expected `true` match
    an observed `1` (or `false` match `0`). That is exactly the kind of
    imprecise pass this kit must not produce, so `bool` is compared only
    against `bool` here, never coerced against `int`.
    """
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            return [f"{path}: expected object, observed {type(observed).__name__}"]
        problems: list[str] = []
        for key, exp_val in expected.items():
            child_path = f"{path}.{key}"
            if key not in observed:
                problems.append(f"{child_path}: missing in observed output")
                continue
            problems.extend(subset_equal(exp_val, observed[key], child_path))
        return problems
    if isinstance(expected, list):
        if not isinstance(observed, list):
            return [f"{path}: expected array, observed {type(observed).__name__}"]
        if len(expected) != len(observed):
            return [
                f"{path}: expected {len(expected)} item(s), observed {len(observed)}"
            ]
        problems = []
        for index, (exp_item, obs_item) in enumerate(zip(expected, observed)):
            problems.extend(subset_equal(exp_item, obs_item, f"{path}[{index}]"))
        return problems
    if isinstance(expected, bool) != isinstance(observed, bool):
        return [
            f"{path}: type mismatch, expected {type(expected).__name__} {expected!r}, "
            f"observed {type(observed).__name__} {observed!r}"
        ]
    if expected != observed:
        return [f"{path}: expected {expected!r}, observed {observed!r}"]
    return []


def run_driver(driver_cmd: list[str], case_input: dict[str, Any]) -> dict[str, Any]:
    proc = subprocess.run(
        driver_cmd,
        input=json.dumps(case_input),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"driver exited {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"driver stdout is not valid JSON: {proc.stdout!r}") from exc


def load_manifest() -> dict[str, Any]:
    return json.loads((KIT_DIR / "manifest.json").read_text())


def load_case(case_id: str) -> dict[str, Any]:
    return json.loads((KIT_DIR / "cases" / f"{case_id}.json").read_text())


def check_case(driver_cmd: list[str], case: dict[str, Any]) -> list[str]:
    observed = run_driver(driver_cmd, case["input"])
    return subset_equal(case["expected"], observed, path="$.expected")


def run_all(driver_cmd: list[str], case_ids: list[str] | None) -> bool:
    manifest = load_manifest()
    ids = case_ids or [entry["case_id"] for entry in manifest["cases"]]
    all_ok = True
    for case_id in ids:
        case = load_case(case_id)
        try:
            problems = check_case(driver_cmd, case)
        except RuntimeError as exc:
            problems = [str(exc)]
        if problems:
            all_ok = False
            print(f"FAIL {case_id}")
            for problem in problems:
                print(f"      {problem}")
        else:
            print(f"PASS {case_id}")
    print(f"\n{'all cases passed' if all_ok else 'FAILURES PRESENT'} ({len(ids)} case(s))")
    return all_ok


# --- Falsification probes (--probe) ------------------------------------
#
# Each probe: (case_id, mutation-description, mutate(expected) -> mutated
# expected). The probe passes when `subset_equal(mutated, real_observed)`
# is NON-empty (a mismatch was correctly detected). If it comes back empty,
# this checker has a false-accept bug.


def _probe_mutations() -> list[tuple[str, str, Any]]:
    return [
        (
            "CASE-001-happy-path-acceptance",
            "wrong acceptance: claims BLOCKED for a run that actually accepts",
            lambda expected: _set_path(expected, ["projection", "A", "state"], "BLOCKED"),
        ),
        (
            "CASE-001-happy-path-acceptance",
            "wrong candidate binding: claims a different fingerprint bound",
            lambda expected: _set_path(
                expected, ["projection", "A", "current_candidate_id"], "not-c1"
            ),
        ),
        (
            "CASE-005-execution-pending",
            "wrong pending behavior: claims ACCEPTED while execution is still pending",
            lambda expected: _set_path(expected, ["projection", "A", "state"], "ACCEPTED"),
        ),
        (
            "CASE-007-replay-non-default-budget",
            "wrong replay-budget outcome: claims READY instead of the budget-exhausted BLOCKED",
            lambda expected: _set_path(expected, ["projection", "A", "state"], "READY"),
        ),
        (
            "CASE-022-inconclusive-budget-exhausted",
            "wrong blocked_reason: claims retry-budget-exhausted instead of assurance-inconclusive",
            lambda expected: _set_path(
                expected, ["projection", "A", "blocked_reason"], "retry-budget-exhausted"
            ),
        ),
        (
            "CASE-018-candidate-fingerprint-mismatch",
            "wrong error id: claims ERR-VALIDATION for a fingerprint-mismatch conflict",
            lambda expected: _set_path(expected, ["error", "error"], "ERR-VALIDATION"),
        ),
        (
            "CASE-019-malformed-assurance-verdict",
            "wrong outcome: claims ok for a malformed verdict that must be a canonical error",
            lambda expected: _set_path(expected, ["outcome"], "ok"),
        ),
        (
            "CASE-001-happy-path-acceptance",
            "type-confused attempt_number: claims the string \"1\" where the contract requires the integer 1",
            lambda expected: _set_path(expected, ["projection", "A", "attempt_number"], "1"),
        ),
        (
            "CASE-019-malformed-assurance-verdict",
            "wrong failing_work_id derivation: claims null when the raw envelope's data.work_id was actually the discoverable string \"A\"",
            lambda expected: _set_path(expected, ["failing_work_id"], None),
        ),
        (
            "CASE-013-attempt-abandonment-unsettled-assurance-recovery",
            "manufactured fourth verdict: claims verdict \"abandoned\" instead of null+abandoned:true",
            lambda expected: _set_path(
                expected, ["projection", "B", "assurances", 0, "verdict"], "abandoned"
            ),
        ),
        (
            "CASE-015-cancellation-from-executing",
            "stale pending pointer: claims pending_execution_id survives cancellation",
            lambda expected: _set_path(expected, ["projection", "B", "pending_execution_id"], "e1"),
        ),
        (
            "CASE-020-inconclusive-rerequest-decision",
            "wrong idempotency_scope: omits the assurance_number component for the second assurance",
            lambda expected: _set_path(
                expected,
                ["decisions", "A", "effects", 0, "idempotency_scope"],
                ["run-1", "A", 1, "FX-START-ASSURANCE", "fp-1", None],
            ),
        ),
        (
            "CASE-020-inconclusive-rerequest-decision",
            "candidate fingerprint collision: omits the candidate_fingerprint component, "
            "so a differently-fingerprinted candidate at the same assurance_number would "
            "wrongly collide on the same idempotency scope",
            lambda expected: _set_path(
                expected,
                ["decisions", "A", "effects", 0, "idempotency_scope"],
                ["run-1", "A", 1, "FX-START-ASSURANCE", None, 2],
            ),
        ),
        (
            "CASE-024-malformed-history-shape",
            "fabricated location: claims failing_work_id \"0\" for a failure raised before any envelope could be identified",
            lambda expected: _set_path(expected, ["failing_work_id"], "0"),
        ),
    ]


def _set_path(value: Any, path: list[str], new_value: Any) -> Any:
    mutated = copy.deepcopy(value)
    node = mutated
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = new_value
    return mutated


def run_probes(driver_cmd: list[str]) -> bool:
    all_ok = True
    for case_id, description, mutate in _probe_mutations():
        case = load_case(case_id)
        observed = run_driver(driver_cmd, case["input"])
        mutated_expected = mutate(copy.deepcopy(case["expected"]))
        problems = subset_equal(mutated_expected, observed, path="$.expected")
        if problems:
            print(f"PROBE OK   {case_id}: {description} -- correctly rejected")
        else:
            all_ok = False
            print(
                f"PROBE FAIL {case_id}: {description} -- checker ACCEPTED a false claim"
            )
    print(f"\n{'all probes correctly rejected' if all_ok else 'PROBE FAILURES: false-accept bug'}")
    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_ids", nargs="*", help="specific case id(s); default: all")
    parser.add_argument(
        "--driver-cmd",
        default=None,
        help="shell-split command to run as the driver; default: the reference driver",
    )
    parser.add_argument(
        "--probe", action="store_true", help="run falsification probes instead of the case suite"
    )
    args = parser.parse_args()

    driver_cmd = args.driver_cmd.split() if args.driver_cmd else DEFAULT_DRIVER_CMD

    if args.probe:
        ok = run_probes(driver_cmd)
    else:
        ok = run_all(driver_cmd, args.case_ids or None)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
