---
id: EXT-GIT-CANDIDATE-IDENTIFICATION-V1-SEMANTICS
type: contract
status: current
authority: normative
version: 1
description: Emission and interpretation rules for git-candidate-identification/v1.
---

# `git-candidate-identification/v1` semantics

The Git candidate adapter emits this extension only when identification observed an advance and the final bound head differs from the initial head. It emits no marker or note for stable observations or an ABA sequence whose final bound head equals its initial head.

The marker records identification provenance only. Candidate fingerprinting excludes the `extensions` key and continues to use the identity fields `head_sha`, `diff_digest`, and optional `repo_path`. Marked and unmarked observations of the same subject therefore fingerprint identically.

The payload cannot override or redefine candidate identity (`EXT-003`) and is never the sole carrier of canonical identity or other canonical information (`EXT-007`). Consumers MAY display, retain, or ignore its opaque fields without changing candidate equality or freshness.
