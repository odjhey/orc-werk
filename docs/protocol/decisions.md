---
id: PROTOCOL-DECISIONS
type: protocol
status: current
authority: normative
description: Canonical orchestration decisions.
---

# Decisions

A Decision records what orchestration policy chose and why.

| ID | Decision | Meaning |
|---|---|---|
| `DEC-DISPATCH` | Dispatch | Start a new Execution for eligible Work. |
| `DEC-RETRY` | Retry | Start another Execution for the same Work while preserving history. |
| `DEC-REQUEST-ASSURANCE` | RequestAssurance | Evaluate one exact Candidate. |
| `DEC-ACCEPT` | Accept | Commit Work completion after required assurance succeeds. |
| `DEC-BLOCK` | Block | Stop autonomous progress pending changed state/input/authority. |
| `DEC-ABANDON-ATTEMPT` | AbandonAttempt | Consume an attempt's unresolved candidate-observation conflict, settled-completed Execution with no bound candidate, or unsettleable Assurance, settling that attempt as failed so ordinary retry/block machinery proceeds. |
| `DEC-ESCALATE` | Escalate | Request human or higher-policy attention. |
| `DEC-CANCEL` | Cancel | Intentionally terminate the Work/DeliveryRun. |

Every Decision MUST satisfy `INV-011` and `INV-012`.

`DEC-ABANDON-ATTEMPT` (`TASK-M3B-001`, issues #76/#95) is a Decision an *operator* attributes rather than v0 policy (`attribution` names the operator, not `V0_POLICY_ATTRIBUTION`) — legal exactly when `STATE-DELIVERY` mechanical fact sequencing item 9 applies at one of its three resting points: an attempt's candidate observation is in irrecoverable conflict (a re-observed candidate identity that verdict inheritance, item 8, cannot resolve), its Execution settled completed but no Candidate could be bound, or its current Assurance is unsettleable by any seat (issue #95's adapter-owned in-flight case). It is paired with `FACT-ATTEMPT-ABANDONED` (`PROTOCOL-FACTS`), never with a `FACT-ASSURE-SETTLED` — an abandon settles the *attempt*, not the candidate's verdict, so `INV-003`/`INV-009` (rejected/inconclusive assurance is not acceptance; execution settlement is not acceptance) are never at stake and no assurance evidence is fabricated (`INV-003`). `basis` (`INV-012`) cites the conflicting `FACT-CANDIDATE-OBSERVED`, the null-candidate rest's `FACT-EXEC-SETTLED`, or the unsettled `FACT-ASSURE-STARTED`; `data` carries the operator's stated reason. Recorded through the CLI operator surface documented in `docs/playbooks/cli-usage.md`, never through the ship/verify agent observation path (`docs/playbooks/agent-cli-usage.md`) — abandoning an attempt is an operator power, not an observation.

`DEC-CANCEL` is likewise an operator-attributed Decision reachable in v0/M0, never emitted by deterministic policy and never available through the ship/verify agent path. It is legal from any non-terminal Work state and pairs with `FACT-WORK-CANCELLED`, which closes the Work directly as terminal `CANCELLED` without a port Effect (`STATE-DELIVERY` item 10). `attribution` names the operator, `basis` cites an appropriate Fact for the Work's current state, and `data` carries the free-form reason (`INV-011`/`INV-012`). Cancellation is deliberate closure without acceptance, not an assurance verdict; it never fabricates `FACT-ASSURE-SETTLED` (`INV-003`, `INV-009`).
