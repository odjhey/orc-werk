---
id: SCN-005
type: scenario
status: current
authority: normative
description: Fan-in work remains blocked until all required upstream completion conditions are committed.
---

# SCN-005 — Dependency fan-in

## Given

```text
A ─┐
   ├→ C
B ─┘
```

A and B are initially ready. C requires accepted completion of both.

## Then
- A and B may dispatch independently.
- C is not returned by `WorkGraphPort.ready` after only A completes.
- C becomes eligible only after both required upstream conditions are committed.

Verifies: `INV-015`, `INV-016`.
