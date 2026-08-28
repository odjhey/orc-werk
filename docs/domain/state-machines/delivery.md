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

`max_attempts = 3` is the v0 default policy budget used by the retry-budget checks above (`INV-018`/`INV-019`). Policy configuration MAY override this default; `INV-019` requires any configured budget be finite.

## Mechanical fact sequencing

The transition table names the Fact that triggers each row's state change. Some Facts in a Work's lineage confirm a transition already entered by another row, or gate eligibility/claim without moving the Work between states, rather than triggering a table row directly. These sequencing rules are normative:

1. **Creation vs. readiness.** A Work enters `READY` on `FACT-WORK-CREATED`. `FACT-WORK-READY` does not itself transition state; it records the `INV-015` eligibility confirmation that `DEC-DISPATCH` requires before dispatch.
2. **Retry does not require re-confirmed readiness.** When `DEC-RETRY` returns a Work to `READY` (from `EXECUTING` on a failed settlement, or from `ASSURING` on a rejected verdict, budget permitting), the Work does not require a fresh `FACT-WORK-READY`. The `INV-015` eligibility confirmation persists across all attempts within one Work lineage.
3. **Dispatch and assurance-entry confirmations.** `FACT-EXEC-STARTED` is the only legal continuation of `READY` and effects the `READY` → `EXECUTING` transition (dispatch confirmation). `FACT-CANDIDATE-OBSERVED` effects the `EXECUTING` → `ASSURING` transition and is legal only once the current Execution has settled with outcome `completed`; it MUST NOT precede that settlement.
4. **Terminal confirmations.** `FACT-WORK-COMPLETED` is the only legal continuation of `ACCEPTED`; `FACT-WORK-BLOCKED` is the only legal continuation of `BLOCKED`. Each confirms the Work's committed terminal outcome and MUST NOT be recorded more than once per Work.
5. **Claim recording.** `FACT-WORK-CLAIMED` is legal only while a Work is `READY`. It does not transition state; it records `claim_ref` prior to dispatch. A claim is once per Work lineage: it persists across all retry attempts within the lineage (`DEC-RETRY` returning the Work to `READY` does not clear or require re-recording the claim), and the claim holder drives every attempt from journal state.

Note (informative): `FACT-WORK-BLOCKED`'s `reason` field is free-form per `PROTOCOL-FACTS`. The v0 policy emits exactly two values: `retry-budget-exhausted` (retry budget exhausted per `INV-018`/`INV-019`) and `assurance-inconclusive` (an `inconclusive` assurance verdict). Future policies MAY emit other values.

## Reserved states and decisions

`FAILED`, `CANCELLED`, `DEC-ESCALATE`, `DEC-CANCEL`, and `FACT-WORK-CANCELLED` are declared in `PROTOCOL-DECISIONS`/`PROTOCOL-FACTS` but have no transition row in this v0/M0 state machine. They are reserved for a future contract revision, MUST NOT be produced by v0/M0 policy, and require an explicit contract change (a new transition row here) to become reachable.

The state machine deliberately omits provider-specific lifecycle states.
