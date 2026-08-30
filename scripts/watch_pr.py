#!/usr/bin/env python3
"""Read-only GitHub PR merge-frontier watcher.

Exit codes: READY=0, MERGED=0, CLOSED=2, CONFLICTS=3,
UNRESOLVED-THREADS=4, CI-FAILING=5, MERGE-GATE=6, CI-PENDING=7,
FETCH-ERROR=8, STALE-VERDICT=9, INDETERMINATE=10. REBASED is an
informational verdict-staleness result and retains the PR classification's
exit code. No invocation mutates GitHub or the local repository.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

EXIT_CODES = {
    "READY": 0,
    "MERGED": 0,
    "CLOSED": 2,
    "CONFLICTS": 3,
    "UNRESOLVED-THREADS": 4,
    "CI-FAILING": 5,
    "MERGE-GATE": 6,
    "CI-PENDING": 7,
    "FETCH-ERROR": 8,
    "STALE-VERDICT": 9,
    "INDETERMINATE": 10,
}
FAILURE_CONCLUSIONS = {
    "ACTION_REQUIRED",
    "CANCELLED",
    "ERROR",
    "FAILURE",
    "STALE",
    "STARTUP_FAILURE",
    "TIMED_OUT",
}
PENDING_STATES = {"EXPECTED", "IN_PROGRESS", "PENDING", "QUEUED", "REQUESTED", "WAITING"}


@dataclass(frozen=True)
class Classification:
    state: str
    reason: str


def _rollup_state(check: dict[str, Any]) -> tuple[bool, bool]:
    """Return (failed, pending) from either CheckRun or StatusContext data."""
    conclusion = str(check.get("conclusion") or "").upper()
    state = str(check.get("state") or "").upper()
    status = str(check.get("status") or "").upper()
    failed = conclusion in FAILURE_CONCLUSIONS or state in FAILURE_CONCLUSIONS
    pending = status in PENDING_STATES or state in PENDING_STATES
    return failed, pending


def classify(snapshot: dict[str, Any]) -> Classification:
    """Classify one already-fetched PR snapshot; performs no I/O."""
    state = str(snapshot.get("state") or "").upper()
    if state == "MERGED":
        return Classification("MERGED", "already merged")
    if state == "CLOSED":
        return Classification("CLOSED", "closed without merge")

    if str(snapshot.get("mergeable") or "").upper() == "CONFLICTING":
        return Classification("CONFLICTS", "branch has merge conflicts")

    unresolved = snapshot.get("unresolvedReviewThreads")
    if isinstance(unresolved, int) and unresolved > 0:
        return Classification("UNRESOLVED-THREADS", f"{unresolved} unresolved review thread(s)")

    rollup = snapshot.get("statusCheckRollup") or []
    states = [_rollup_state(check) for check in rollup if isinstance(check, dict)]
    if any(failed for failed, _pending in states):
        return Classification("CI-FAILING", "status check rollup contains a failed check")

    if snapshot.get("isDraft"):
        return Classification("MERGE-GATE", "pull request is a draft")
    if str(snapshot.get("reviewDecision") or "").upper() == "CHANGES_REQUESTED":
        return Classification("MERGE-GATE", "changes were requested")

    if any(pending for _failed, pending in states):
        return Classification("CI-PENDING", "status checks are still running")

    merge_status = str(snapshot.get("mergeStateStatus") or "").upper()
    mergeable = str(snapshot.get("mergeable") or "").upper()
    if merge_status == "CLEAN" or mergeable == "MERGEABLE":
        note = "; review-thread count unavailable" if snapshot.get("reviewThreadsUnknown") else ""
        return Classification("READY", "platform reports the pull request mergeable" + note)

    note = "; review-thread count unavailable" if snapshot.get("reviewThreadsUnknown") else ""
    return Classification("MERGE-GATE", f"platform merge state is {merge_status or 'UNKNOWN'}{note}")


def _run(args: list[str], *, cwd: Path = ROOT, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=cwd, input=input_text, text=True, capture_output=True, check=False
    )


def _gh_json(args: list[str], *, retries: int = 3) -> Any:
    delay = 1.0
    last_error = "gh failed"
    for attempt in range(retries):
        try:
            result = _run(["gh", *args])
        except OSError as exc:
            last_error = str(exc)
        else:
            if result.returncode == 0:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError as exc:
                    last_error = f"invalid gh JSON: {exc}"
            else:
                last_error = result.stderr.strip() or f"gh exited {result.returncode}"
        if attempt + 1 < retries:
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(last_error)


def fetch_snapshot(pr: str, repo: str | None = None) -> dict[str, Any]:
    fields = "number,title,state,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup,headRefOid"
    repo_args = ["--repo", repo] if repo else []
    snapshot = _gh_json(["pr", "view", pr, *repo_args, "--json", fields])
    query = """query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){reviewThreads(first:100){nodes{isResolved}}}}}"""
    try:
        if repo:
            owner, name = repo.split("/", 1)
        else:
            identity = _gh_json(["repo", "view", "--json", "nameWithOwner"])
            owner, name = identity["nameWithOwner"].split("/", 1)
        threads = _gh_json([
            "api", "graphql", "-f", f"query={query}", "-F", f"owner={owner}",
            "-F", f"name={name}", "-F", f"number={snapshot['number']}",
        ], retries=1)
        nodes = threads["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
        snapshot["unresolvedReviewThreads"] = sum(not node["isResolved"] for node in nodes)
    except (KeyError, RuntimeError, TypeError, ValueError):
        snapshot["reviewThreadsUnknown"] = True
    return snapshot


def _patch_id(revision: str, *, cwd: Path, base: str) -> str | None:
    reachable = _run(["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=cwd)
    if reachable.returncode != 0:
        return None
    diff = _run(["git", "diff", f"{base}...{revision}"], cwd=cwd)
    if diff.returncode != 0:
        return None
    patch = _run(["git", "patch-id", "--stable"], cwd=cwd, input_text=diff.stdout)
    if patch.returncode != 0:
        return None
    return patch.stdout.strip()


def classify_verdict(verified_sha: str, head_sha: str, *, cwd: Path = ROOT, base: str = "master") -> Classification:
    """Compare locally reachable candidate patches for verdict staleness."""
    if verified_sha == head_sha:
        return Classification("READY", "verdict matches current head")
    old_patch = _patch_id(verified_sha, cwd=cwd, base=base)
    new_patch = _patch_id(head_sha, cwd=cwd, base=base)
    if old_patch is None or new_patch is None:
        return Classification("INDETERMINATE", "candidate commit is not locally reachable")
    if old_patch == new_patch:
        return Classification("REBASED", "verdict carries")
    return Classification("STALE-VERDICT", "content drift -- re-verify")


def _classify_one(pr: str, repo: str | None, verified_sha: str | None) -> tuple[dict[str, Any] | None, Classification]:
    try:
        snapshot = fetch_snapshot(pr, repo)
    except (RuntimeError, OSError, ValueError) as exc:
        return None, Classification("FETCH-ERROR", str(exc))
    result = classify(snapshot)
    if verified_sha and result.state not in {"MERGED", "CLOSED"}:
        verdict = classify_verdict(verified_sha, str(snapshot.get("headRefOid") or ""))
        if verdict.state in {"STALE-VERDICT", "INDETERMINATE"}:
            result = verdict
        elif verdict.state == "REBASED":
            result = Classification(result.state, f"{result.reason}; REBASED ({verdict.reason})")
    return snapshot, result


def _line(snapshot: dict[str, Any] | None, selector: str, result: Classification) -> str:
    number = snapshot.get("number") if snapshot else selector
    return f"PR #{number} {result.state}: {result.reason}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prs", nargs="*", help="PR number or branch")
    parser.add_argument("--repo", help="GitHub owner/name")
    parser.add_argument("--watch", action="store_true", help="poll until actionable")
    parser.add_argument("--interval", type=float, default=20.0, help="watch polling interval")
    parser.add_argument("--verified-sha", help="sha bound to the assurance verdict")
    args = parser.parse_args(argv)
    if args.watch and len(args.prs) != 1:
        parser.error("--watch requires exactly one PR")
    if args.verified_sha and len(args.prs) != 1:
        parser.error("--verified-sha requires exactly one PR")

    prs = args.prs
    if not prs:
        repo_args = ["--repo", args.repo] if args.repo else []
        try:
            listed = _gh_json(["pr", "list", *repo_args, "--state", "open", "--json", "number"])
        except RuntimeError as exc:
            print(f"PR #? FETCH-ERROR: {exc}")
            return EXIT_CODES["FETCH-ERROR"]
        prs = [str(item["number"]) for item in listed]

    final_code = 0
    for pr in prs:
        previous: Classification | None = None
        while True:
            snapshot, result = _classify_one(pr, args.repo, args.verified_sha)
            if result != previous:
                print(_line(snapshot, pr, result), flush=True)
                previous = result
            code = EXIT_CODES.get(result.state, 0)
            final_code = max(final_code, code)
            if not args.watch or result.state not in {"CI-PENDING", "UNRESOLVED-THREADS"}:
                break
            time.sleep(max(0.0, args.interval * random.uniform(0.9, 1.1)))
    return final_code


if __name__ == "__main__":
    sys.exit(main())
