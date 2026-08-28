---
id: STATE-DELIVERY
type: state-machine
status: current
authority: normative
description: Initial canonical delivery state machine for one Work item.
---

# Delivery state machine

## Canonical v0 states

```text
READY
  ↓ Dispatch
EXECUTING
  ↓ Candidate observed
ASSURING
  ├─ accepted      → ACCEPTED
  ├─ rejected      → READY (retry if budget permits)
  └─ inconclusive  → BLOCKED

Terminal/side states:
BLOCKED
FAILED
CANCELLED
```

## Transition table

| Current | Fact | Decision | Next | Typical effect |
|---|---|---|---|---|
| READY | `FACT-WORK-READY` | `DEC-DISPATCH` | EXECUTING | `FX-START-EXECUTION` |
| EXECUTING | `FACT-EXEC-SETTLED(completed)` + candidate available | `DEC-REQUEST-ASSURANCE` | ASSURING | `FX-START-ASSURANCE` |
| EXECUTING | `FACT-EXEC-SETTLED(failed)` | `DEC-RETRY` or `DEC-BLOCK` | READY/BLOCKED | `FX-START-EXECUTION` or `FX-BLOCK-WORK` |
| ASSURING | `FACT-ASSURE-SETTLED(accepted)` | `DEC-ACCEPT` | ACCEPTED | `FX-COMPLETE-WORK` |
| ASSURING | `FACT-ASSURE-SETTLED(rejected)` | `DEC-RETRY` or `DEC-BLOCK` | READY/BLOCKED | `FX-START-EXECUTION` or `FX-BLOCK-WORK` |
| ASSURING | `FACT-ASSURE-SETTLED(inconclusive)` | `DEC-BLOCK` | BLOCKED | `FX-BLOCK-WORK` |

The state machine deliberately omits provider-specific lifecycle states.
