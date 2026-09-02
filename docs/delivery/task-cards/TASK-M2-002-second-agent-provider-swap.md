---
id: TASK-M2-002
type: task-card
status: superseded
authority: normative
description: acpx claude as a second agent through the existing acp PORT-EXECUTION adapter, zero adapter code change — the P-001 provider-swap proof.
implements:
  - P-001
verifies: []
---

> **Superseded** (operator ruling ADR-0005, issue #214). Moot: this card's whole premise was swapping which agent drives the `acp` `ExecutionPort` adapter, and that adapter was **removed** in 0.5.0, pre-1.0, no backward compatibility (last release carrying it: v0.4.1). See `docs/decisions/ADR-0005-push-recording-not-pull-observation.md` and `docs/adapters/acp/README.md`. Retained as historical reference only.

# TASK-M2-002 — Second agent, same adapter (P-001 proof)

### Deferred — removed from M2 scope

**Operator ruling (M2 reshape, 2026-08-28): this card is deferred, out of
M2 scope.** The card's design below stands as-is for whenever it is
picked up — no rework needed at pull time — but M2 does not schedule it.
Recorded on the milestone's deferred list
(`docs/delivery/M2-close-the-loop.md`, "Deferred (M2 reshape)").

**Pull trigger (named, per `PLAYBOOK-WATCHTOWER`'s dormant-feature
lifecycle):** provider-diversity proof wanted, or the first Pi-capability
gap encountered. Either concretely motivates re-proving `P-001` with a
second provider; absent one of those, `acpx pi` alone continues to prove
the adapter is being dogfooded, and a same-adapter second-provider swap
adds no scope M2 currently needs.

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
