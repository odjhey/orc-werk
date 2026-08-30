"""`CONF-CAND-*` conformance for `GitDiffCandidate` (`TASK-M1-005`),
against a real temporary `git` repository fixture -- no scripted subject
content, no mocked `git`.

`GitDiffCandidate`'s real signature (`identify(execution_id,
artifact_refs)`, `current(work_id)`) is driven by live git state rather
than a `{execution_id: subject}` script map, so this does not literally
subclass `tests.conformance.test_candidate_conformance.
CandidatePortConformance` (that mixin's `make_candidate(subjects=...)`
factory is scripted-adapter-shaped). It instead exercises the same
`CONF-CAND-001`/`002`/`003` properties -- same subject -> same
fingerprint, changed subject -> different fingerprint, `compare()`, and
`current()` declining when not safely determinable -- against real
repository content, per the task card's acceptance item.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orc_werk.adapters.git import GitDiffCandidate
from orc_werk.core.errors import CoreError
from orc_werk.ports.candidate import CANDIDATE_COMPARISON_DIFFERENT, CANDIDATE_COMPARISON_SAME


def _git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], cwd=path)
    _git(["config", "user.email", "conformance@example.invalid"], cwd=path)
    _git(["config", "user.name", "Conformance Fixture"], cwd=path)


class GitDiffCandidateConformanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        _init_repo(self.repo)
        (self.repo / "a.txt").write_text("x")
        _git(["add", "."], cwd=self.repo)
        _git(["commit", "-q", "-m", "init"], cwd=self.repo)
        self.adapter = GitDiffCandidate(repo_path=str(self.repo))

    # -- CONF-CAND-001: same exact subject yields the same fingerprint. --

    def test_conf_cand_001_same_subject_same_fingerprint(self) -> None:
        c1 = self.adapter.identify(execution_id="e1")
        c2 = self.adapter.identify(execution_id="e2")
        self.assertIsNotNone(c1)
        self.assertIsNotNone(c2)
        self.assertEqual(c1.fingerprint, c2.fingerprint)
        self.assertEqual(
            self.adapter.compare(candidate_a=c1, candidate_b=c2), CANDIDATE_COMPARISON_SAME
        )

    # -- CONF-CAND-002: changed subject (a real uncommitted edit) yields a
    # -- different fingerprint. --

    def test_conf_cand_002_changed_subject_different_fingerprint(self) -> None:
        before = self.adapter.identify(execution_id="e1")
        (self.repo / "a.txt").write_text("y")
        after = self.adapter.identify(execution_id="e2")
        self.assertNotEqual(before.fingerprint, after.fingerprint)
        self.assertEqual(
            self.adapter.compare(candidate_a=before, candidate_b=after),
            CANDIDATE_COMPARISON_DIFFERENT,
        )

    def test_conf_cand_002_new_commit_changes_fingerprint(self) -> None:
        before = self.adapter.identify(execution_id="e1")
        (self.repo / "b.txt").write_text("new file")
        _git(["add", "."], cwd=self.repo)
        _git(["commit", "-q", "-m", "second"], cwd=self.repo)
        after = self.adapter.identify(execution_id="e2")
        self.assertNotEqual(before.subject_identity["head_sha"], after.subject_identity["head_sha"])
        self.assertNotEqual(before.fingerprint, after.fingerprint)

    # -- CONF-CAND-003: current() must not silently return a stale/guessed
    # -- candidate; it must decline explicitly when not safely determinable,
    # -- and return a real candidate when it is. --

    def test_conf_cand_003_current_declines_when_not_a_git_repo(self) -> None:
        not_a_repo = Path(self._tmp.name) / "not-a-repo"
        not_a_repo.mkdir()
        adapter = GitDiffCandidate(repo_path=str(not_a_repo))
        self.assertIsNone(adapter.current(work_id="w1"))
        self.assertIsNone(adapter.identify(execution_id="e1"))

    def test_conf_cand_003_current_declines_on_unborn_head(self) -> None:
        empty_repo = Path(self._tmp.name) / "empty-repo"
        _init_repo(empty_repo)
        adapter = GitDiffCandidate(repo_path=str(empty_repo))
        self.assertIsNone(adapter.current(work_id="w1"))

    def test_conf_cand_003_current_declines_on_nonexistent_path(self) -> None:
        adapter = GitDiffCandidate(repo_path=str(Path(self._tmp.name) / "does-not-exist"))
        self.assertIsNone(adapter.current(work_id="w1"))

    def test_conf_cand_003_current_returns_candidate_when_safely_determinable(self) -> None:
        current = self.adapter.current(work_id="w1")
        self.assertIsNotNone(current)
        self.assertEqual(current.work_id, "w1")
        identified = self.adapter.identify(execution_id="e1")
        self.assertEqual(current.fingerprint, identified.fingerprint)

    # -- post-settlement identification confirms a quiescent ref. --

    def test_race_marker_does_not_change_bound_subject_fingerprint(self) -> None:
        first = self.adapter.identify(execution_id="before").subject_identity["head_sha"]
        (self.repo / "b.txt").write_text("tail-end write")
        _git(["add", "."], cwd=self.repo)
        _git(["commit", "-q", "-m", "agent final commit"], cwd=self.repo)
        later = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        reads = iter([first, later, later])

        class AdvancingHeadCandidate(GitDiffCandidate):
            def __init__(self, *, repo_path: str) -> None:
                super().__init__(repo_path=repo_path)
                self._settle_wait = lambda _seconds: None

            def _git(self, args: list[str], *, cwd: Path) -> str | None:
                if args[:2] == ["rev-parse", "--verify"]:
                    return next(reads)
                return super()._git(args, cwd=cwd)

        adapter = AdvancingHeadCandidate(repo_path=str(self.repo))

        with mock.patch("sys.stderr") as stderr:
            candidate = adapter.identify(execution_id="race")

        self.assertEqual(candidate.subject_identity["head_sha"], later)
        clean = self.adapter.current(work_id="clean-observation")
        self.assertNotIn("extensions", clean.subject_identity)
        self.assertEqual(candidate.fingerprint, clean.fingerprint)
        marker = candidate.subject_identity["extensions"]["git-candidate-identification/v1"]
        self.assertTrue(marker["worktree_advanced"])
        self.assertEqual(marker["initial_head"], first)
        self.assertEqual(marker["bound_head"], later)
        self.assertIn(f"({first}..{later}); bound {later}", "".join(call.args[0] for call in stderr.write.call_args_list))

    def test_identify_retries_while_index_lock_is_present(self) -> None:
        locks = iter([True, False])
        waits: list[float] = []
        adapter = GitDiffCandidate(
            repo_path=str(self.repo),
            lock_present=lambda _repo: next(locks),
            settle_wait=waits.append,
        )
        expected = self.adapter.current(work_id="w").subject_identity["head_sha"]

        candidate = adapter.identify(execution_id="locked")

        self.assertEqual(candidate.subject_identity["head_sha"], expected)
        self.assertEqual(len(waits), 2)
        self.assertNotIn("extensions", candidate.subject_identity)

    def test_stable_identification_retains_common_path_shape_and_identity(self) -> None:
        waits: list[float] = []
        adapter = GitDiffCandidate(repo_path=str(self.repo), settle_wait=waits.append)
        current = adapter.current(work_id="stable")
        identified = adapter.identify(execution_id="stable")

        self.assertEqual(identified.subject_identity, current.subject_identity)
        self.assertEqual(identified.fingerprint, current.fingerprint)
        self.assertEqual(len(waits), 1)
        self.assertNotIn("extensions", identified.subject_identity)

    def test_race_marker_is_absent_when_repeated_reads_are_stable(self) -> None:
        adapter = GitDiffCandidate(repo_path=str(self.repo), settle_wait=lambda _seconds: None)
        candidate = adapter.identify(execution_id="stable")
        self.assertNotIn("extensions", candidate.subject_identity)

    # -- subject_identity shape / rationale. --

    def test_subject_identity_shape(self) -> None:
        candidate = self.adapter.identify(execution_id="e1")
        self.assertEqual(
            set(candidate.subject_identity), {"head_sha", "diff_digest", "repo_path"}
        )
        self.assertTrue(candidate.subject_identity["diff_digest"].startswith("sha256:"))

    def test_include_repo_path_false_omits_it_from_subject_identity(self) -> None:
        adapter = GitDiffCandidate(repo_path=str(self.repo), include_repo_path=False)
        candidate = adapter.identify(execution_id="e1")
        self.assertNotIn("repo_path", candidate.subject_identity)

    # -- artifact_refs['ref'] selects a specific historical commit. --

    def test_identify_with_explicit_ref(self) -> None:
        first = self.adapter.identify(execution_id="e1")
        (self.repo / "a.txt").write_text("y")
        _git(["add", "."], cwd=self.repo)
        _git(["commit", "-q", "-m", "second"], cwd=self.repo)

        pinned = self.adapter.identify(
            execution_id="e2", artifact_refs={"ref": first.subject_identity["head_sha"]}
        )
        self.assertEqual(pinned.subject_identity["head_sha"], first.subject_identity["head_sha"])

    def test_identify_rejects_non_portable_artifact_refs(self) -> None:
        with self.assertRaises(CoreError) as ctx:
            self.adapter.identify(execution_id="e1", artifact_refs={"ref": object()})
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-VALIDATION")

    def test_identify_declines_for_unresolvable_ref(self) -> None:
        result = self.adapter.identify(execution_id="e1", artifact_refs={"ref": "not-a-real-ref"})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
