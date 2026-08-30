---
id: ADAPTER-ACP-CONFORMANCE
type: conformance-report
status: current
authority: informative
description: ACP/acpx adapter (AcpExecution) conformance status.
---

# ACP/acpx conformance

| Requirement | Status | Evidence |
|---|---|---|
| `CONF-EXEC-001` | pass | `tests/conformance/test_acp_execution_conformance.py::AcpExecutionConformanceTest::test_conf_exec_001_start_returns_stable_execution_identity` |
| `CONF-EXEC-002` | pass | `tests/conformance/test_acp_execution_conformance.py::AcpExecutionConformanceTest::test_conf_exec_002_repeated_start_same_key_no_duplicate_execution` |
| `CONF-EXEC-003` | pass | `tests/conformance/test_acp_execution_conformance.py::AcpExecutionConformanceTest::test_conf_exec_003_inspect_distinguishes_running_from_settled` |
| `CONF-EXEC-004` | pass | `tests/conformance/test_acp_execution_conformance.py::AcpExecutionConformanceTest::test_conf_exec_004_unsupported_resume_strength_fails_explicitly` |
| `CONF-CAND-001` | pass (`GitDiffCandidate`) | `tests/conformance/test_git_candidate_conformance.py::GitDiffCandidateConformanceTest::test_conf_cand_001_same_subject_same_fingerprint` |
| `CONF-CAND-002` | pass (`GitDiffCandidate`) | `tests/conformance/test_git_candidate_conformance.py::GitDiffCandidateConformanceTest::test_conf_cand_002_changed_subject_different_fingerprint` (+ `..._new_commit_changes_fingerprint`) |
| `CONF-CAND-003` | pass (`GitDiffCandidate`) | `tests/conformance/test_git_candidate_conformance.py::GitDiffCandidateConformanceTest::test_conf_cand_003_current_declines_when_not_a_git_repo` (+ 3 more decline/return variants) |

All run against a fake `acpx` executable on `PATH` (`tests/conformance/support_acpx_stub.py`) — no real `acpx`/Node/`pi-acp` install required for the automated suite. Two mixin tests inherited from `tests/conformance/test_execution_conformance.py::ExecutionPortConformance` are skipped with a documented reason (scripted-test-double-only behavior no real adapter can offer): `test_inspect_transports_scripted_artifact_refs_and_extensions_losslessly`, `test_capability_honesty_resume_exact_when_advertised`. See `docs/adapters/acp/mapping.md`'s "Lossy mappings"/"Capability honesty" sections.

Additional unit coverage beyond the shared mixin (task card acceptance item): `tests/conformance/test_acp_execution_unit.py` — the three unobservability-determination branches (daemon-dead-no-result → `failed`; terminal-quiescent result → `settled`; alive-no-result → `running`, never a timeout), issue #181 terminal-quiescence cases (retry activity suppresses settlement; a terminal result settles; passive reconnect bookkeeping does not block it), and cancel post-verification (both the in-flight-turn and nothing-to-cancel cases).

Live-smoke evidence (manual, not part of the automated suite; transcript recorded in the shipping PR body): one real `acpx pi` run through `AcpExecution` — `start()` → polling `inspect()` (`running`, `running`, `settled`/`completed`) → `execution-session/v1` extensions emitted — session closed afterward.
