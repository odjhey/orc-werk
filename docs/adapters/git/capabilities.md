---
id: ADAPTER-GIT-CAPABILITIES
type: adapter-capabilities
status: current
authority: informative
description: Git candidate adapter capability notes.
---

# Git capabilities

`GitDiffCandidate.capabilities()` returns an empty set — `CONTRACT-CAPABILITIES` defines no `CandidatePort` capability ids as of this writing (mirrors `ScriptedCandidate`). No extra canonical capability is required for v0 beyond successful `PORT-CANDIDATE` conformance (`CONF-CAND-001` through `CONF-CAND-003`), which this adapter passes against a real temporary `git` repository fixture — see `docs/adapters/git/conformance.md`.
