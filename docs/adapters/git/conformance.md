---
id: ADAPTER-GIT-CONFORMANCE
type: conformance-report
status: current
authority: informative
description: Git CandidatePort (GitDiffCandidate) conformance status.
---

# Git conformance

| Requirement | Status | Evidence |
|---|---|---|
| `CONF-CAND-001` | pass | `tests/conformance/test_git_candidate_conformance.py::GitDiffCandidateConformanceTest::test_conf_cand_001_same_subject_same_fingerprint` |
| `CONF-CAND-002` | pass | `tests/conformance/test_git_candidate_conformance.py::GitDiffCandidateConformanceTest::test_conf_cand_002_changed_subject_different_fingerprint`, `..._new_commit_changes_fingerprint` |
| `CONF-CAND-003` | pass | `tests/conformance/test_git_candidate_conformance.py::GitDiffCandidateConformanceTest::test_conf_cand_003_current_declines_when_not_a_git_repo`, `..._declines_on_unborn_head`, `..._declines_on_nonexistent_path`, `..._returns_candidate_when_safely_determinable` |

Run against a real temporary `git` repository fixture (`git init`, local-only, no network/remote) — no scripted subject content, no mocked `git`. Additional coverage beyond the three requirements: `subject_identity` shape, `include_repo_path=False`, explicit-ref identification (`artifact_refs['ref']`), non-portable `artifact_refs` rejection, and unresolvable-ref decline.
