---
id: EXT-GIT-CANDIDATE-IDENTIFICATION-V1
type: extension
status: current
authority: normative
version: 1
description: Git adapter-local provenance for a worktree advance observed during candidate identification.
---

# `git-candidate-identification/v1`

`git-candidate-identification/v1` is optional adapter-local provenance describing a Git worktree advance observed while identifying a candidate. The Git adapter emits it only when the final bound head differs from the initial head.

The payload rides under the candidate observation's `subject_identity.extensions`, but is excluded from candidate fingerprint material. Per `EXT-003`, it never overrides candidate identity. Per `EXT-007`, it is never the sole carrier of canonical identity or other canonical information.

## Files

- [Schema](schema.md)
- [Semantics](semantics.md)
- [Examples](examples.md)

## Related

- `CONTRACT-EXTENSIONS`
- `PORT-CANDIDATE`
- `ADAPTER-GIT-MAPPING`
