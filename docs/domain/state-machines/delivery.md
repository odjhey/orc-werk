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
  ├─ rejected      → READY (retry, budget permitting) | BLOCKED (budget exhausted)
  └─ inconclusive  → BLOCKED

Terminal states (v0/M0 reachable):
ACCEPTED
BLOCKED

Reserved (declared, not reachable in v0/M0 — see "Reserved states and decisions"):
FAILED
CANCELLED
```

## Transition table

| Current | Fact | Decision | Next | Typical effect |
|---|---|---|---|---|
| READY | `FACT-WORK-READY` | `DEC-DISPATCH` | EXECUTING | `FX-START-EXECUTION` |
| EXECUTING | `FACT-EXEC-SETTLED(completed)` + candidate available | `DEC-REQUEST-ASSURANCE` | ASSURING | `FX-START-ASSURANCE` |
| EXECUTING | `FACT-EXEC-SETTLED(failed)`, retry budget available (`INV-018`/`INV-019`) | `DEC-RETRY` | READY | `FX-START-EXECUTION` |
| EXECUTING | `FACT-EXEC-SETTLED(failed)`, retry budget exhausted (`INV-018`/`INV-019`) | `DEC-BLOCK` | BLOCKED | `FX-BLOCK-WORK` |
| ASSURING | `FACT-ASSURE-SETTLED(accepted)` | `DEC-ACCEPT` | ACCEPTED | `FX-COMPLETE-WORK` |
| ASSURING | `FACT-ASSURE-SETTLED(rejected)`, retry budget available (`INV-018`/`INV-019`) | `DEC-RETRY` | READY | `FX-START-EXECUTION` |
| ASSURING | `FACT-ASSURE-SETTLED(rejected)`, retry budget exhausted (`INV-018`/`INV-019`) | `DEC-BLOCK` | BLOCKED | `FX-BLOCK-WORK` |
| ASSURING | `FACT-ASSURE-SETTLED(inconclusive)` | `DEC-BLOCK` | BLOCKED | `FX-BLOCK-WORK` |

Retry-budget exhaustion (`INV-018`/`INV-019`) resolves deterministically to `DEC-BLOCK` → BLOCKED via `FX-BLOCK-WORK`/`FACT-WORK-BLOCKED`. This is the single v0 budget-exhaustion terminal; the state machine does not branch to any other outcome when the budget is exhausted.

## Reserved states and decisions

`FAILED`, `CANCELLED`, `DEC-ESCALATE`, `DEC-CANCEL`, and `FACT-WORK-CANCELLED` are declared in `PROTOCOL-DECISIONS`/`PROTOCOL-FACTS` but have no transition row in this v0/M0 state machine. They are reserved for a future contract revision, MUST NOT be produced by v0/M0 policy, and require an explicit contract change (a new transition row here) to become reachable.

The state machine deliberately omits provider-specific lifecycle states.
