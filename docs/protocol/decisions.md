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
| `DEC-ESCALATE` | Escalate | Request human or higher-policy attention. |
| `DEC-CANCEL` | Cancel | Intentionally terminate the Work/DeliveryRun. |

Every Decision MUST satisfy `INV-011` and `INV-012`.
