"""CI drift protection for the portable conformance kit
(`CONFORMANCE-PORTABLE-KIT`, `docs/conformance/portable-kit.md`; issue
#313 fix round 2, `agent://VerifyPortableKit` "REJECT CI DRIFT
PROTECTION" finding).

`conformance/checker.py` and `conformance/cases/*.json` live outside
`src/`, so nothing in the pre-existing `unittest discover -s tests`
gate (`scripts/check.sh`) ever imported or ran them. A wrong `expected`
value landing in a committed case file, or a false-accept regression in
the checker's own comparison, could ship silently. This module closes
that gap by importing `conformance/checker.py` directly (the same
module `python3 conformance/checker.py` runs) and exercising it against
the real reference driver as part of this same discovered suite."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KIT_DIR = _REPO_ROOT / "conformance"
if str(_KIT_DIR) not in sys.path:
    sys.path.insert(0, str(_KIT_DIR))

import checker  # noqa: E402  (conformance/checker.py -- not a src/ package)


class PortableKitCorpusTest(unittest.TestCase):
    """Every shipped case, run against the real reference core, as part
    of the gate -- not just a developer's manual `checker.py` invocation."""

    def test_every_case_passes_against_the_reference_driver(self) -> None:
        manifest = checker.load_manifest()
        self.assertEqual(23, len(manifest["cases"]))
        failures: dict[str, list[str]] = {}
        for entry in manifest["cases"]:
            case = checker.load_case(entry["case_id"])
            problems = checker.check_case(checker.DEFAULT_DRIVER_CMD, case)
            if problems:
                failures[entry["case_id"]] = problems
        self.assertEqual({}, failures)

    def test_falsification_probes_all_correctly_reject(self) -> None:
        probes = checker._probe_mutations()
        self.assertGreaterEqual(len(probes), 5)
        for case_id, description, mutate in probes:
            case = checker.load_case(case_id)
            observed = checker.run_driver(checker.DEFAULT_DRIVER_CMD, case["input"])
            mutated_expected = mutate(copy.deepcopy(case["expected"]))
            problems = checker.subset_equal(mutated_expected, observed, path="$.expected")
            self.assertTrue(
                problems,
                f"{case_id}: {description} -- checker ACCEPTED a false claim",
            )

    def test_wrong_expected_acceptance_is_rejected_not_silently_passed(self) -> None:
        """The exact drift the verifier's manual probe demonstrated: an
        `expected` claiming BLOCKED for a run that actually reaches
        ACCEPTED must be rejected. This is the mechanism that would make
        the same corruption, committed to a real case file, fail this
        gate instead of a manual-only `checker.py` run."""
        case = checker.load_case("CASE-001-happy-path-acceptance")
        wrong_expected = copy.deepcopy(case["expected"])
        wrong_expected["projection"]["A"]["state"] = "BLOCKED"
        observed = checker.run_driver(checker.DEFAULT_DRIVER_CMD, case["input"])
        problems = checker.subset_equal(wrong_expected, observed, path="$.expected")
        self.assertTrue(problems)
        self.assertIn("BLOCKED", problems[0])

    def test_every_fact_work_id_appears_in_the_records_own_plan(self) -> None:
        """PORT-WORK-001: a case's `history` must never fold a Fact for a
        Work absent from its own `FX-CREATE-WORK` plan -- the exact defect
        class the verifier found in the pre-fix CASE-013/015/016."""
        manifest = checker.load_manifest()
        for entry in manifest["cases"]:
            case = checker.load_case(entry["case_id"])
            history = case["input"]["history"]
            create_work = next(rec for rec in history if rec.get("id") == "FX-CREATE-WORK")
            planned = {w["work_id"] for w in create_work["data"]["plan"]["works"]}
            self.assertIn("dispatch_result", create_work["data"], entry["case_id"])
            for record in history:
                if record.get("kind") != "fact":
                    continue
                work_id = record["data"].get("work_id")
                if work_id is not None:
                    self.assertIn(
                        work_id,
                        planned,
                        f"{entry['case_id']}: fact {record['id']} targets work "
                        f"{work_id!r} absent from its own FX-CREATE-WORK plan {planned!r}",
                    )


if __name__ == "__main__":
    unittest.main()
