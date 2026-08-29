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
| EXECUTING | `FACT-CANDIDATE-OBSERVED` naming a candidate identity with a prior `accepted` verdict (verdict inheritance, item 8 below) | *(none — mechanical, `INV-011`)* | ACCEPTED | *(none — see the `DEC-ACCEPT`/`FX-COMPLETE-WORK` row above)* |
| EXECUTING | `FACT-CANDIDATE-OBSERVED` naming a candidate identity with a prior `rejected` verdict, retry budget available (verdict inheritance, item 8 below) | *(none — mechanical, `INV-011`)* | READY | *(none — see the `DEC-RETRY` row above)* |
| EXECUTING | `FACT-CANDIDATE-OBSERVED` naming a candidate identity with a prior `rejected` verdict, retry budget exhausted (verdict inheritance, item 8 below) | *(none — mechanical, `INV-011`)* | BLOCKED | *(none — see the `DEC-BLOCK` row above)* |
| EXECUTING (candidate-observation conflict, item 9 below) or ASSURING (current assurance unsettled — item 9 below) | `FACT-ATTEMPT-ABANDONED` | `DEC-ABANDON-ATTEMPT` | READY (retry, budget permitting) \| BLOCKED (budget exhausted) | *(none — journal-only; the abandon record targets no port)* |

Retry-budget exhaustion (`INV-018`/`INV-019`) resolves deterministically to `DEC-BLOCK` → BLOCKED via `FX-BLOCK-WORK`/`FACT-WORK-BLOCKED`. This is the single v0 budget-exhaustion terminal; the state machine does not branch to any other outcome when the budget is exhausted.

`max_attempts = 3` is the v0 default policy budget used by the retry-budget checks above (`INV-018`/`INV-019`). Policy configuration MAY override this default; `INV-019` requires any configured budget be finite.

## Mechanical fact sequencing

The transition table names the Fact that triggers each row's state change. Some Facts in a Work's lineage confirm a transition already entered by another row, or gate eligibility/claim without moving the Work between states, rather than triggering a table row directly. These sequencing rules are normative:

1. **Creation vs. readiness.** A Work enters `READY` on `FACT-WORK-CREATED`. `FACT-WORK-READY` does not itself transition state; it records the `INV-015` eligibility confirmation that `DEC-DISPATCH` requires before dispatch.
2. **Retry does not require re-confirmed readiness.** When `DEC-RETRY` returns a Work to `READY` (from `EXECUTING` on a failed settlement, or from `ASSURING` on a rejected verdict, budget permitting), the Work does not require a fresh `FACT-WORK-READY`. The `INV-015` eligibility confirmation persists across all attempts within one Work lineage.
3. **Dispatch and assurance-entry confirmations.** `FACT-EXEC-STARTED` is the only legal continuation of `READY` and effects the `READY` → `EXECUTING` transition (dispatch confirmation). `FACT-CANDIDATE-OBSERVED` effects the `EXECUTING` → `ASSURING` transition and is legal only once the current Execution has settled with outcome `completed`; it MUST NOT precede that settlement.
4. **Terminal confirmations.** `FACT-WORK-COMPLETED` is the only legal continuation of `ACCEPTED`; `FACT-WORK-BLOCKED` is the only legal continuation of `BLOCKED`. Each confirms the Work's committed terminal outcome and MUST NOT be recorded more than once per Work.
5. **Claim recording.** `FACT-WORK-CLAIMED` is legal only while a Work is `READY`. It does not transition state; it records `claim_ref` prior to dispatch. A claim is once per Work lineage: it persists across all retry attempts within the lineage (`DEC-RETRY` returning the Work to `READY` does not clear or require re-recording the claim), and the claim holder drives every attempt from journal state.
6. **Dispatch-gate failure normalizes to a failed execution attempt.** When `DEC-DISPATCH`'s `FX-START-EXECUTION` cannot be carried out — the capability gate rejects it or the provider cannot start it at all (`ERR-UNSUPPORTED-CAPABILITY`/`ERR-PROVIDER-UNAVAILABLE`) — the orchestrator MUST record the failure as a failed execution attempt rather than inventing a separate dispatch-failure exit from `READY`: it journals `FACT-EXEC-STARTED` carrying a unique synthetic execution reference, immediately followed by `FACT-EXEC-SETTLED` with outcome `failed`, and preserves the canonical error in the corresponding effect record's `dispatch_result`. This keeps the transition table total, routes the attempt through the ordinary `EXECUTING` retry/`DEC-BLOCK` machinery (`INV-018`/`INV-019`), and never silently degrades capability (`INV-013`). The synthetic execution reference identifies a dispatch attempt, not a provider-side execution.
7. **Absence of a settlement observation is not a settlement.** A started Execution whose outcome has not yet been observed (no `FACT-EXEC-SETTLED`, and likewise no `FACT-ASSURE-SETTLED` for a started-but-unverdicted Assurance) MUST NOT be recorded as any outcome — not `completed`, not `failed`, and not a synthetic default. No Fact is journaled for waiting: the orchestrator records only what it has actually observed. A started-but-unobserved Execution or Assurance leaves the Work at `EXECUTING`/`ASSURING` indefinitely, for as long as the outcome remains unrecorded; this is a normal, non-erroneous resting point of the state machine, not a stalled or degraded one. Waiting MUST NOT consume retry budget (`INV-018`/`INV-019`): waiting journals no new execution-start record, so the cumulative count of execution-start records (`INV-018`) is unchanged — a pending attempt is already counted as its own `attempt_number` from its start, and the count advances only on the next start (a retry), never on waiting or settlement. This rule governs only the absence of an outcome after a successful dispatch; it does not alter item 6 above — an unsupported capability or unavailable provider at dispatch time is still journaled as a failed execution attempt immediately, never left pending. A bounded-wait/timeout policy is a future policy concern: making a wait expire into any outcome requires an explicit new transition per the "Reserved states and decisions" rule below, and is not forbidden by this clause — "indefinitely" describes the v0 default behavior, not a prohibition.

8. **Re-observation resolution (verdict inheritance).** `FACT-CANDIDATE-OBSERVED` naming a `candidate_id` that already exists in the Work's lineage (a candidate re-produced by a later attempt — the common case is an unchanged worktree re-executed after a rejection, or a resumed provider session) is legal, not a conflict, exactly when the reused identity is exact: the incoming `fingerprint` matches the fingerprint already recorded for that `candidate_id` (`INV-006`) and a prior `FACT-ASSURE-SETTLED` exists for that same `candidate_id`. The kernel resolves it mechanically (`P-007`, `INV-011` — no `DEC-*` accompanies this step, matching item 6's `FX-IDENTIFY-CANDIDATE`-class mechanics) by **inheriting** the prior verdict rather than re-running assurance: evidence is candidate-bound and already applies (`INV-007`, `INV-008`) and is never re-fabricated (`INV-003` — no new `FACT-ASSURE-SETTLED` is journaled; the transition table's three new EXECUTING rows above cite the *existing* settlement as basis for whatever `DEC-*` the ordinary machinery next emits). A previously-`accepted` candidate re-observed resolves immediately to `ACCEPTED` (idempotent-harmless: `DEC-ACCEPT` fires exactly as it would have from a freshly-settled acceptance, citing the inherited settlement as basis). A previously-`rejected` candidate re-observed resolves immediately toward the ordinary retry/exhaustion path — `READY` (budget permitting) or `BLOCKED` (budget exhausted) — via the same `INV-018`/`INV-019` arithmetic the `ASSURING`/`FACT-ASSURE-SETTLED(rejected)` row already uses, with the *inherited* settlement (not a fresh one) as the `DEC-RETRY`/`DEC-BLOCK` basis (`INV-012`). This closes the permanent-wedge failure mode where re-observing the same candidate after a rejection previously raised `ERR-CONFLICT` on every replay forever (an append-only journal cannot un-observe a durably recorded Fact) — the issue #76 live specimen.

9. **Candidate-observation conflict and the abandon transition.** A re-observed `candidate_id` that is *not* an exact re-observation under item 8 — the incoming `fingerprint` does not match the fingerprint already on record for that `candidate_id` (an identity collision `INV-006`/`INV-008` forbid resolving via inheritance), or no prior `FACT-ASSURE-SETTLED` exists yet for that candidate to inherit from (its only prior assurance never settled) — is nonetheless still journaled: the Fact is an immutable observation and MUST NOT be discarded (`PROTOCOL-FACTS`). The Work rests at `EXECUTING`, marked with this unresolved candidate-observation conflict, rather than the fold raising a hard replay error — mirroring item 7's "waiting is a normal resting point" precedent, this is a second, distinct normal (non-erroneous) resting point: the kernel cannot resolve the conflict on its own, but the journal, and everything derived from it, stays legible and replayable. The other resting point this item's transition row names is item 7's existing `ASSURING`-with-no-settlement rest: the kernel has no way to *detect* "unsettleable" (a started Assurance that will never produce a verdict — issue #95's adapter-owned in-flight case) from journal state alone; it is indistinguishable from "still genuinely in flight" until an operator, with out-of-band knowledge, judges otherwise. From either resting point, `FACT-ATTEMPT-ABANDONED` is now a legal continuation, paired with `DEC-ABANDON-ATTEMPT` (`PROTOCOL-DECISIONS`): an operator decision, attributed to the operator (not `V0_POLICY_ATTRIBUTION` — `INV-011`), citing the conflicting Fact or the unsettled Assurance's `FACT-ASSURE-STARTED` as basis (`INV-012`), and carrying who/why in its own `attribution`/`data`. It is an *abandon*, never a verdict: it settles the *attempt* as failed, not the candidate as rejected or accepted — no `FACT-ASSURE-SETTLED` is fabricated (`INV-003`, `INV-009` intact), so a later, different candidate from a fresh attempt remains fully assurable on its own merits. Folding `FACT-ATTEMPT-ABANDONED` clears the conflict/in-flight marker and resolves via the identical `INV-018`/`INV-019` retry-budget arithmetic every other failed-attempt row already uses: `READY` (budget permitting, an ordinary `DEC-RETRY` follows) or `BLOCKED` (budget exhausted, an ordinary `DEC-BLOCK` follows, `reason: "attempt-abandoned"`). No port Effect accompanies `DEC-ABANDON-ATTEMPT`/`FACT-ATTEMPT-ABANDONED`: this is a journal-only kernel operation (no adapter is asked to do anything), recorded through the CLI operator surface `PROTOCOL-DECISIONS` and `docs/playbooks/cli-usage.md` document.

Note (informative): `FACT-WORK-BLOCKED`'s `reason` field is free-form per `PROTOCOL-FACTS`. The v0 policy emits exactly three values: `retry-budget-exhausted` (retry budget exhausted per `INV-018`/`INV-019`), `assurance-inconclusive` (an `inconclusive` assurance verdict), and `attempt-abandoned` (item 9's `FACT-ATTEMPT-ABANDONED` exhausted the retry budget on resolution). Future policies MAY emit other values.

## Reserved states and decisions

`FAILED`, `CANCELLED`, `DEC-ESCALATE`, `DEC-CANCEL`, and `FACT-WORK-CANCELLED` are declared in `PROTOCOL-DECISIONS`/`PROTOCOL-FACTS` but have no transition row in this v0/M0 state machine. They are reserved for a future contract revision, MUST NOT be produced by v0/M0 policy, and require an explicit contract change (a new transition row here) to become reachable.

The state machine deliberately omits provider-specific lifecycle states.
