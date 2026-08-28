---
id: M-000
type: milestone
status: current
authority: normative
description: First milestone proving provider-free orchestration semantics.
---

# M0 — Pure core

## Goal

Given an intent and scripted/in-memory providers, the CLI can autonomously drive:

```text
intent
→ ready work
→ dispatch attempt 1
→ candidate A
→ assurance rejected
→ retry attempt 2
→ candidate B
→ assurance accepted
→ work complete
```

while preserving inspectable facts, decisions, effects, candidate identities, and evidence identities.

## Required contracts

- `ORCHESTRATION-CONTRACT`
- `PORT-WORK-GRAPH`
- `PORT-EXECUTION`
- `PORT-CANDIDATE`
- `PORT-ASSURANCE`
- `PORT-JOURNAL`

## Required scenarios

- `SCN-001` through `SCN-006`

## Required implementation

- pure core types/reducer/policy;
- MemoryWorkGraph adapter;
- ScriptedExecution adapter;
- ScriptedCandidate adapter;
- ScriptedAssurance adapter;
- MemoryJournal or JSONLJournal;
- CLI: `dispatch`, `status`, `watch/history` minimum;
- conformance tests for memory/scripted adapters.

## Explicitly out of scope

- Beads adapter;
- zxro/ACP integration;
- no-mistakes integration;
- LLM planner/watchtower policy;
- daemon;
- web UI;
- merge/integration port;
- general policy DSL.
