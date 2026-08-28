---
id: ADAPTER-ACP
type: adapter
status: current
authority: informative
description: ACP/acpx runtime adapter (AcpExecution) for ExecutionPort, driving Pi.
---

# ACP/acpx adapter

Implemented (`TASK-M1-005`): `src/orc_werk/adapters/acp/execution.py`'s `AcpExecution` is a harness-neutral `PORT-EXECUTION` adapter over the `acpx` CLI (an Agent Client Protocol client), driving Pi (`acpx pi`) as its first configured agent. It is agent-agnostic at the protocol layer — swapping `agent="pi"` for another `acpx`-supported agent (e.g. `agent="claude"`) requires no code change (`P-001` provider-swap demonstration path).

Exact resume, structured lifecycle, send, and cancel are capability-negotiated, never assumed — see `docs/adapters/acp/capabilities.md`. Full design decisions, operation mapping, footguns, and version pins: `docs/adapters/acp/mapping.md`. Conformance status: `docs/adapters/acp/conformance.md`.

Related: `docs/delivery/task-cards/TASK-M1-005-acp-adapter.md`, `docs/reports/2026-08-28-acpx-pi-spike.md` (the empirical ground truth this adapter's subprocess pattern follows).
