---
id: ADAPTER-GIT-MAPPING
type: adapter-mapping
status: current
authority: informative
description: Git-to-CandidatePort mapping for GitDiffCandidate (TASK-M1-005).
---

# Git candidate mapping

Implemented by `src/orc_werk/adapters/git/candidate.py` (`GitDiffCandidate`).

## Which Git identities contribute to Candidate equality/freshness

`subject_identity`:

```python
{
  "head_sha": "<git rev-parse of the identified ref, default HEAD>",
  "diff_digest": "sha256:<truncated hex digest of `git diff <ref>` output>",
  "repo_path": "<configured repository path>",  # present unless include_repo_path=False
}
```

- **`head_sha`** pins the exact commit the candidate is relative to. Required: `git diff` alone is relative, so two different base commits that happen to produce textually identical diffs must not compare as the same candidate.
- **`diff_digest`** captures uncommitted worktree state — both staged and unstaged changes relative to `head_sha` (`git diff <ref>`, no `--cached` restriction) — as a compact digest rather than the raw diff text. `subject_identity` is an identity payload, not an artifact store (the same "ref/digest over content" posture `execution-session/v1`'s `transcript_ref` takes, for the same reason): a digest is deterministic, bounded in size regardless of diff size, and never risks `Candidate` becoming a de facto artifact carrier. Computed via the shared `fingerprint_of` helper (see below), so it reuses the same canonical-JSON sha256 scheme as the fingerprint itself rather than a second hashing implementation.
- **`repo_path`** disambiguates candidates across repositories/worktrees, and is included by default. This adapter's target use is one Work per one configured worktree, so including it in the fingerprint does not create false negatives in that usage; it deliberately participates in equality like every other field rather than being carved out into a second, adapter-private fingerprint scheme. `GitDiffCandidate(..., include_repo_path=False)` opts out for callers that want cross-path identity instead.

## Fingerprinting

Reuses `orc_werk.adapters.scripted.candidate.fingerprint_of` — the same canonical-JSON sha256 helper every other adapter uses (sha256 over `sort_keys=True` JSON of the portable subject content, truncated to 24 hex chars, `fp-` prefixed). `CONF-CAND-001`/`CONF-CAND-002` only need `subject_identity` to be deterministic content; the digest algorithm itself is shared infrastructure, not adapter-specific.

## `identify()` / `current()` — declining explicitly

Per `PORT-CAND-001`/`PORT-CAND-002` ("no assurable subject" / "cannot be determined safely" are valid, non-error outcomes — never a stale or guessed candidate): `identify()`/`current()` return `None` whenever the requested ref cannot be safely resolved:

- `repo_path` does not exist or is not a directory;
- the path is not a git repository, or has an unborn `HEAD` (no commits yet);
- the configured `git` binary cannot be executed;
- a caller-supplied `artifact_refs['ref']` does not resolve to a real commit.

None of these raise — `PORT-CAND-001` frames "no assurable subject" as a valid outcome, not an error. `CoreError`/`ERR-VALIDATION` is raised only for malformed caller *input* (non-portable `artifact_refs`, or a non-string/empty `artifact_refs['ref']`) — a contract violation, not an environmental "can't tell" condition.

`identify(execution_id, artifact_refs)`: `execution_id` is not used to look anything up (there is no `{execution_id: subject}` mapping for a real adapter to consult) — it is only threaded through into the returned `Candidate.execution_id` and `Candidate.work_id` (bookkeeping; `PORT-CAND-001` does not hand `identify()` a `work_id`, so this adapter synthesizes `Candidate.work_id = execution_id`). `artifact_refs['ref']`, when present, names the git ref to fingerprint instead of the default `HEAD`.

Before binding, `identify()` confirms a quiescent ref: two consecutive commit-resolution reads must agree, with a short bounded settle interval between them, and Git's resolved `index.lock` path must be absent. When a read advances, the later value becomes the next baseline. Confirmation is bounded to three comparisons. Exhaustion is **never a timeout-to-failure**: the adapter binds the latest observed commit and records/prints the honest race note `worktree advanced during identification; bound the final observed head`. The diff is then read against that bound SHA, not the moving ref. If the final bound SHA differs from the initial observation, dispatch stderr also says `note: worktree advanced during candidate identification (<A>..<B>); bound <B>`. The adapter-owned `git-candidate-identification/v1` marker appears in the candidate subject only on that race path.

The settle interval gates **when** Git is observed; its duration and wall-clock time are never canonical candidate or journal data (`INV-020`). Stable observations therefore retain the pre-rule candidate shape byte-for-byte. A still-present lock after the bound degrades to bind-latest rather than failing, with no invented timing data.

`current(work_id)`: fingerprints `HEAD` for the configured `repo_path`, using a synthesized `execution_id` (`f"git-diff-worktree:{work_id}"`) purely as bookkeeping — the returned `Candidate.work_id` is the real `work_id` passed in. Because `current()` is a point-in-time comparison rather than post-settlement identification, it does not perform the settle confirmation.

## Idempotency behavior

Every call re-reads real git state; there is no cached/idempotency-keyed identity to preserve beyond git's own commit/worktree state. Calling `identify()`/`current()` repeatedly against an unchanged worktree returns the same fingerprint every time (`CONF-CAND-001`); the CandidatePort has no `start`-style effect to make idempotent in the `INV-020` sense.

## Error translation

| Condition | Result |
|---|---|
| `artifact_refs` not portable/JSON-compatible | `ERR-VALIDATION` |
| `artifact_refs['ref']` present but not a non-empty string | `ERR-VALIDATION` |
| `repo_path` missing, not a git repo, unborn `HEAD`, or `git` binary unusable | `None` (decline, not an error) |
| `artifact_refs['ref']` does not resolve | `None` (decline, not an error) |

## Impossible mappings

None identified for v0 — the adapter's fingerprint surface (`head_sha` + worktree diff) is sufficient for `CONF-CAND-001` through `CONF-CAND-003` as implemented.
