---
id: ADAPTER-NO-MISTAKES-CONFORMANCE
type: adapter-conformance
status: current
authority: informative
description: Conformance status for no-mistakes assurance adapter (TASK-M2-001).
---

# no-mistakes conformance

`NoMistakesAssurance` satisfies generic assurance conformance for every
capability it advertises, run against a fake `no-mistakes` executable on
`PATH` (`tests/conformance/support_no_mistakes_stub.py`) -- no real
`no-mistakes` install/daemon/agent dependency in CI, mirroring the acp
adapter's stub-subprocess precedent.

| Requirement | Status | Evidence |
|---|---|---|
| `CONF-ASSURE-001` (settled evidence names the candidate fingerprint) | Pass | `tests/conformance/test_no_mistakes_assurance_conformance.py::NoMistakesAssuranceConformanceTest::test_conf_assure_001_settled_evidence_names_candidate_fingerprint` (adapted from the shared mixin -- see that test's docstring for why: a real adapter cannot honor a caller-scripted passthrough `evidence_refs` string, so the incidental `assertIn("report-1", ...)` assertion is replaced with an assertion on this adapter's real, structured `evidence_refs` shape; the normative fingerprint/state assertions are unchanged). |
| `CONF-ASSURE-002` (rejected never normalizes to accepted) | Pass | Same file, `test_conf_assure_002_rejected_never_normalizes_to_accepted` (unmodified from the shared mixin). |
| `CONF-ASSURE-003` (evidence from a different fingerprint is rejected by the kernel) | Pass (via existing kernel-level test, not re-exercised per adapter) | `tests/conformance/test_assurance_conformance.py::Conf003ForeignFingerprintRejectedByKernelTest` -- per that file's own docstring, this is core's job (`orc_werk.core.reducer`, `INV-008`/`INV-010`), not an adapter-level test; this adapter's only obligation is `CONF-ASSURE-001`'s faithful fingerprint reporting. |
| `CONF-ASSURE-004` (inconclusive remains distinct from rejected/accepted) | Pass | Same file, `test_conf_assure_004_inconclusive_distinct_from_rejected_and_accepted` (unmodified from the shared mixin). |
| `CONF-EXT-001`-`CONF-EXT-006` (structured findings extension conformance) | Pass, exercised indirectly | `review-findings/v1` findings this adapter produces satisfy `EXT-REVIEW-FINDINGS-V1-SCHEMA` by construction (`_to_review_finding` in `assurance.py` always emits every required field); `test_parked_gate_with_findings_maps_to_rejected_with_review_findings_v1` (`test_no_mistakes_assurance_unit.py`) exercises a real produced payload end-to-end. `test_inspect_transports_scripted_extensions_losslessly` is skipped with a documented rationale (see `mapping.md` "Lossy mappings") -- a real adapter cannot honor a caller-scripted passthrough payload, the same documented gap `AcpExecution`'s own conformance test records for its `extensions`. |

Additional coverage beyond the CONF-ASSURE floor:

- `tests/conformance/test_no_mistakes_assurance_unit.py` -- the full,
  explicit verdict-mapping table (every row in `mapping.md`'s "Verdict
  mapping"), TOON parser tolerance (`ParseToonTest`), and a fresh-instance
  settlement-reproducibility test mirroring `AcpExecutionCrossProcess
  IdempotencyTest`'s crash-recovery style.
- `tests/scenarios/test_cli_no_mistakes_wiring.py` -- `load_config`'s
  strict validation of the `assurance` config block plus a full
  `dispatch -> pending -> pending (auto) -> accepted` cycle driven through
  the real `orc` CLI entrypoint (subprocess), against the stub and a real
  temporary git repository.

All of the above are stdlib-only (no real `no-mistakes`/daemon/agent
dependency) and run as part of `bash scripts/check.sh`.
