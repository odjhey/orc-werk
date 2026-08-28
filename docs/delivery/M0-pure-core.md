---
id: M-000
type: milestone
status: current
authority: normative
description: First milestone proving provider-free orchestration semantics.
---

# M0 — Pure core

## Goal

Given an intent and scripted/in-memory providers, the Orc Werk CLI can autonomously drive:

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

- Python 3.11+ reference implementation under `src/orc_werk/`;
- pure core types/reducer/policy;
- MemoryWorkGraph adapter;
- ScriptedExecution adapter;
- ScriptedCandidate adapter;
- ScriptedAssurance adapter;
- MemoryJournal or JSONLJournal;
- CLI: `dispatch`, `status`, `watch/history` minimum;
- conformance tests for memory/scripted adapters.

## Portability acceptance

M0 canonical persisted/interchange records must be reconstructable from portable, explicit data without importing Python implementation classes. Do not use pickle, Python class names, exception objects, or arbitrary Python object graphs as canonical storage or protocol shapes.

Deleting all real integration adapters must leave the complete core, conformance, and golden-scenario suite runnable.

Self-healing/restart behavior introduced in M0 must be expressed through explicit durable state, replay, reconciliation, idempotent effects, and bounded policy so the semantics can be implemented in another language later.

## Explicitly out of scope

- Beads adapter;
- zxro/ACP integration;
- no-mistakes integration;
- LLM planner/watchtower policy;
- daemon;
- web UI;
- merge/integration port;
- general policy DSL;
- Go rewrite or a scheduled language migration.
