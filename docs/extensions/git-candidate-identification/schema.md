---
id: EXT-GIT-CANDIDATE-IDENTIFICATION-V1-SCHEMA
type: contract
status: current
authority: normative
version: 1
description: Portable schema for git-candidate-identification/v1 provenance.
---

# `git-candidate-identification/v1` schema

```text
GitCandidateIdentificationV1 {
    worktree_advanced: boolean
    initial_head: opaque string
    bound_head: opaque string
    note: opaque string
}
```

All fields are required when emitted and are adapter-local, opaque provenance. Values MUST be portable JSON-compatible data (`EXT-006`). The payload travels under `subject_identity.extensions["git-candidate-identification/v1"]`; it does not add, alter, or participate in canonical candidate identity.
