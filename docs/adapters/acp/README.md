---
id: ADAPTER-ACP
type: adapter
status: superseded
authority: informative
description: ACP/acpx runtime adapter (AcpExecution) for ExecutionPort, driving Pi.
---

> **Superseded** (operator ruling ADR-0005, issue #214). The `acp` `ExecutionPort` adapter was **removed** in 0.5.0, pre-1.0, no backward compatibility; the last release carrying it is v0.4.1. See `docs/decisions/ADR-0005-push-recording-not-pull-observation.md` for the ruling and its dormant-registry entry in `docs/delivery/M4-cockpit-and-clarity.md`; push-shaped pending-settlement semantics now live in `docs/scenarios/SCN-007-pending-settlement.md` and `docs/scenarios/SCN-017-wait-resting-point.md`. Retained as historical reference only.

# ACP/acpx adapter

Implemented (`TASK-M1-005`): `src/orc_werk/adapters/acp/execution.py`'s `AcpExecution` is a harness-neutral `PORT-EXECUTION` adapter over the `acpx` CLI (an Agent Client Protocol client), driving Pi (`acpx pi`) as its first configured agent. It is agent-agnostic at the protocol layer — swapping `agent="pi"` for another `acpx`-supported agent (e.g. `agent="claude"`) requires no code change (`P-001` provider-swap demonstration path).

Exact resume, structured lifecycle, send, and cancel are capability-negotiated, never assumed — see `docs/adapters/acp/capabilities.md`. Full design decisions, operation mapping, footguns, and version pins: `docs/adapters/acp/mapping.md`. Conformance status: `docs/adapters/acp/conformance.md`.

Related: `docs/delivery/task-cards/TASK-M1-005-acp-adapter.md`, `docs/reports/2026-08-28-acpx-pi-spike.md` (the empirical ground truth this adapter's subprocess pattern follows).
