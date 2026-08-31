"""Unit tests for the read-only merge-frontier PR classifier."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.watch_pr import EXIT_CODES, classify, classify_verdict


def snapshot(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "reviewDecision": "APPROVED",
        "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
        "unresolvedReviewThreads": 0,
        "headRefOid": "abc",
    }
    value.update(changes)
    return value


class ClassifyTest(unittest.TestCase):
    def test_terminal_states_have_first_priority(self) -> None:
        self.assertEqual(classify(snapshot(state="MERGED", mergeable="CONFLICTING")).state, "MERGED")
        self.assertEqual(classify(snapshot(state="CLOSED", mergeable="CONFLICTING")).state, "CLOSED")

    def test_conflicts_precede_failing_ci(self) -> None:
        result = classify(snapshot(
            mergeable="CONFLICTING",
            statusCheckRollup=[{"status": "COMPLETED", "conclusion": "FAILURE"}],
        ))
        self.assertEqual(result.state, "CONFLICTS")

    def test_unresolved_threads_precede_pending_ci(self) -> None:
        result = classify(snapshot(
            unresolvedReviewThreads=2,
            statusCheckRollup=[{"status": "IN_PROGRESS", "conclusion": None}],
        ))
        self.assertEqual(result.state, "UNRESOLVED-THREADS")

    def test_cancelled_duplicate_in_platform_rollup_is_failure(self) -> None:
        # A name-deduplicating implementation could retain only the green entry.
        result = classify(snapshot(statusCheckRollup=[
            {"name": "ci-required", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"name": "ci-required", "status": "COMPLETED", "conclusion": "CANCELLED"},
        ]))
        self.assertEqual(result.state, "CI-FAILING")

    def test_draft_precedes_green_mergeability(self) -> None:
        self.assertEqual(classify(snapshot(isDraft=True)).state, "MERGE-GATE")

    def test_changes_requested_is_merge_gate(self) -> None:
        self.assertEqual(classify(snapshot(reviewDecision="CHANGES_REQUESTED")).state, "MERGE-GATE")

    def test_pending_checks_wait(self) -> None:
        result = classify(snapshot(statusCheckRollup=[{"status": "QUEUED", "conclusion": None}]))
        self.assertEqual(result.state, "CI-PENDING")

    def test_uncomputed_merge_state_is_pending(self) -> None:
        for merge_status in ("UNKNOWN", "", None):
            with self.subTest(merge_status=merge_status):
                result = classify(snapshot(mergeStateStatus=merge_status))
                self.assertEqual(result.state, "CI-PENDING")
                self.assertEqual(result.reason, "merge state not yet computed by the platform")
                self.assertEqual(EXIT_CODES[result.state], 7)

    def test_behind_branch_needs_update(self) -> None:
        result = classify(snapshot(mergeStateStatus="BEHIND"))
        self.assertEqual(result.state, "NEEDS-UPDATE-BRANCH")
        self.assertIn("gh pr update-branch", result.reason)
        self.assertEqual(EXIT_CODES[result.state], 11)

    def test_clean_snapshot_is_ready(self) -> None:
        self.assertEqual(classify(snapshot()).state, "READY")

    def test_unknown_threads_are_skipped_with_note(self) -> None:
        value = snapshot(reviewThreadsUnknown=True)
        value.pop("unresolvedReviewThreads")
        result = classify(value)
        self.assertEqual(result.state, "READY")
        self.assertIn("unavailable", result.reason)


class VerdictStalenessTest(unittest.TestCase):
    @staticmethod
    def git(repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        )
        return result.stdout.strip()

    def test_patch_id_distinguishes_rebase_from_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            self.git(repo, "init", "-b", "master")
            self.git(repo, "config", "user.name", "Watch Test")
            self.git(repo, "config", "user.email", "watch@example.invalid")
            (repo / "base.txt").write_text("base\n", encoding="utf-8")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "base")

            self.git(repo, "checkout", "-b", "verified")
            (repo / "change.txt").write_text("same patch\n", encoding="utf-8")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "verified")
            verified = self.git(repo, "rev-parse", "HEAD")

            self.git(repo, "checkout", "master")
            self.git(repo, "checkout", "-b", "rebased")
            (repo / "change.txt").write_text("same patch\n", encoding="utf-8")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "different commit metadata")
            rebased = self.git(repo, "rev-parse", "HEAD")
            self.assertEqual(classify_verdict(verified, rebased, cwd=repo).state, "REBASED")

            self.git(repo, "checkout", "master")
            self.git(repo, "checkout", "-b", "drift")
            (repo / "change.txt").write_text("different patch\n", encoding="utf-8")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "drift")
            drift = self.git(repo, "rev-parse", "HEAD")
            self.assertEqual(
                classify_verdict(verified, drift, cwd=repo).state,
                "STALE-VERDICT",
            )


if __name__ == "__main__":
    unittest.main()
