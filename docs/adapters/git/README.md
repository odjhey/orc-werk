---
id: ADAPTER-GIT
type: adapter
status: current
authority: informative
description: Git adapter for exact Candidate identity (GitDiffCandidate).
---

# Git candidate adapter

Implemented (`TASK-M1-005`): `src/orc_werk/adapters/git/candidate.py`'s `GitDiffCandidate` is the first real `PORT-CANDIDATE` implementation for software-delivery work. It fingerprints a real `git` worktree/ref — the exact commit (`head_sha`) plus a digest of uncommitted worktree changes relative to it (`diff_digest`) — rather than a scripted subject.

The adapter uses `git rev-parse`/`git diff` internally; the core receives only the canonical `subject_identity`/`fingerprint` shape (`PORT-CANDIDATE`'s `Candidate`). Full field rationale, decline conditions, and fingerprinting details: `docs/adapters/git/mapping.md`. Conformance status: `docs/adapters/git/conformance.md`.
