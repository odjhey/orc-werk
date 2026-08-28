---
id: PROTOCOL-EFFECTS
type: protocol
status: current
authority: normative
description: Canonical external effects emitted by the orchestration kernel.
---

# Effects

Effects are requested mutations delegated to ports/adapters.

| ID | Effect | Target port |
|---|---|---|
| `FX-CREATE-WORK` | CreateWork | WorkGraphPort |
| `FX-CLAIM-WORK` | ClaimWork | WorkGraphPort |
| `FX-START-EXECUTION` | StartExecution | ExecutionPort |
| `FX-SEND-EXECUTION` | SendExecutionMessage | ExecutionPort |
| `FX-CANCEL-EXECUTION` | CancelExecution | ExecutionPort |
| `FX-IDENTIFY-CANDIDATE` | IdentifyCandidate | CandidatePort |
| `FX-START-ASSURANCE` | StartAssurance | AssurancePort |
| `FX-COMPLETE-WORK` | CompleteWork | WorkGraphPort |
| `FX-BLOCK-WORK` | BlockWork | WorkGraphPort |
| `FX-NOTIFY-OPERATOR` | NotifyOperator | optional attention/notification adapter |

All state-changing effects MUST satisfy `INV-020`, including its idempotency-key derivation rule.
