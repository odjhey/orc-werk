---
id: EXT-GIT-CANDIDATE-IDENTIFICATION-V1-EXAMPLES
type: example
status: current
authority: informative
version: 1
description: Example git-candidate-identification/v1 provenance payload.
---

# `git-candidate-identification/v1` examples

```json
{
  "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "diff_digest": "sha256:0123456789abcdef01234567",
  "repo_path": "/work/repo",
  "extensions": {
    "git-candidate-identification/v1": {
      "worktree_advanced": true,
      "initial_head": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "bound_head": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "note": "worktree advanced during identification; bound the final observed head"
    }
  }
}
```

The extension explains the observation race. Removing `extensions` from this subject leaves the exact material used for its candidate fingerprint.
