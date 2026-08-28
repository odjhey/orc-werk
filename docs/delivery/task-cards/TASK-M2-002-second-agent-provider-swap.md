---
id: TASK-M2-002
type: task-card
status: current
authority: normative
description: acpx claude as a second agent through the existing acp PORT-EXECUTION adapter, zero adapter code change — the P-001 provider-swap proof.
implements:
  - P-001
verifies: []
---

# TASK-M2-002 — Second agent, same adapter (P-001 proof)

## Outcome

Configure `acpx claude` as a second agent driven through the **same**
`PORT-EXECUTION` adapter M1b shipped for Pi (`TASK-M1-005`). This is the
concrete cross-provider proof that the adapter is agent-agnostic at the
ACP protocol layer, not Claude-orchestrating-Claude wearing a Pi costume
the other way around.

## In scope

- configuration/session-target changes only (agent binary, session name
  derivation inputs) needed to point the existing adapter at
  `acpx claude` instead of `acpx pi`;
- re-running `CONF-EXEC-001` through `CONF-EXEC-004` against the new
  configured target.

## Out of scope

Any change to `src/orc_werk/adapters/acp/` adapter code itself — that is
the acceptance bar, not an implementation detail. Capability set
re-negotiation beyond what the existing capability-advertisement machinery
already handles.

## Must not change

Adapter source code. If driving `acpx claude` genuinely requires an
adapter code change, that is itself a finding to report (the P-001 proof
would then be disproven, not achieved) — do not quietly relax the
"zero code change" acceptance bar to make the card pass.

## Acceptance

- `acpx claude` completes at least one real Work through the existing
  adapter;
- a diff of the adapter's source tree between the Pi-only state and the
  claude-added state shows zero changes to adapter code (config/session-
  target changes only);
- `CONF-EXEC-001` through `-004` pass against the `acpx claude` target.
