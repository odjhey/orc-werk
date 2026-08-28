---
id: ADAPTER-ACP-CAPABILITIES
type: adapter-capabilities
status: current
authority: informative
description: ACP/acpx (AcpExecution) advertised capabilities.
---

# ACP/acpx capabilities

`AcpExecution` (`src/orc_werk/adapters/acp/execution.py`) advertises exactly:

- `CAP-EXEC-SEND`
- `CAP-EXEC-CANCEL`
- `CAP-EXEC-RESUME-BEST-EFFORT`
- `CAP-EXEC-STRUCTURED-LIFECYCLE`

`CAP-EXEC-RESUME-EXACT` is **never advertised** — `AcpExecution.__init__` raises `ValueError` if constructed with it requested. See `docs/adapters/acp/mapping.md`'s "Capability honesty" section for the proving condition and why it fails for `pi-acp@0.0.31` (no native `agentSessionId`, confirmed both by the 2026-08-28 spike and this task's own reproduction).

Proof basis for each advertised capability, and the full withholding rationale, live in the mapping doc, not duplicated here per `docs/adapters/README.md`'s "list only... document" split.
