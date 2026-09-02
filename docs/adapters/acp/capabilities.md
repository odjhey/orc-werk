---
id: ADAPTER-ACP-CAPABILITIES
type: adapter-capabilities
status: superseded
authority: informative
description: ACP/acpx (AcpExecution) advertised capabilities.
---

> **Superseded** (operator ruling ADR-0005, issue #214). The `acp` `ExecutionPort` adapter was **removed** in 0.5.0, pre-1.0, no backward compatibility; the last release carrying it is v0.4.1. See `docs/decisions/ADR-0005-push-recording-not-pull-observation.md` for the ruling and its dormant-registry entry in `docs/delivery/M4-cockpit-and-clarity.md`; push-shaped pending-settlement semantics now live in `docs/scenarios/SCN-007-pending-settlement.md` and `docs/scenarios/SCN-017-wait-resting-point.md`. Retained as historical reference only.

# ACP/acpx capabilities

`AcpExecution` (`src/orc_werk/adapters/acp/execution.py`) advertises exactly:

- `CAP-EXEC-SEND`
- `CAP-EXEC-CANCEL`
- `CAP-EXEC-RESUME-BEST-EFFORT`
- `CAP-EXEC-STRUCTURED-LIFECYCLE`

`CAP-EXEC-RESUME-EXACT` is **never advertised** — `AcpExecution.__init__` raises `ValueError` if constructed with it requested. See `docs/adapters/acp/mapping.md`'s "Capability honesty" section for the proving condition and why it fails for `pi-acp@0.0.31` (no native `agentSessionId`, confirmed both by the 2026-08-28 spike and this task's own reproduction).

Proof basis for each advertised capability, and the full withholding rationale, live in the mapping doc, not duplicated here per `docs/adapters/README.md`'s "list only... document" split.
