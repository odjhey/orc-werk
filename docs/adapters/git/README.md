---
id: ADAPTER-GIT
type: adapter
status: draft
authority: informative
description: Planned Git adapter for exact Candidate identity.
---

# Git candidate adapter

Intended role: first real implementation of `PORT-CANDIDATE` for software-delivery work.

The adapter may use commit/tree/base/merge-base or other exact Git identities internally, but the core receives only canonical subject identity and fingerprint.
