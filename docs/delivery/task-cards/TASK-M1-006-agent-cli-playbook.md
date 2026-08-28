---
id: TASK-M1-006
type: task-card
status: current
authority: normative
description: Author the M1a+ agent CLI guidance playbook — subagents recording observations through the orc CLI (push mode).
implements:
  - M-001
verifies: []
---

# TASK-M1-006 — Agent CLI guidance playbook (M1a+ push mode)

## Outcome

Author the written guidance playbook for agents using the orc CLI, under `docs/playbooks/` (either a dedicated agent-cli-usage playbook or a clearly-scoped section of `PLAYBOOK-CLI-USAGE`), enabling the M1a+ stage: ship/verify subagents record their own observations through the CLI, with no adapters.

The playbook must cover:

- **role separation** — never self-assurance: the settlement recorder and the verdict recorder MUST be different agents (a ship agent claims its Work and records execution settlement + candidate; a separate verification agent records the assurance verdict with `evidence_refs`);
- **no agent records decisions** — decisions remain kernel policy per `INV-011`;
- **claim-before-work**;
- **one writer per run journal**;
- **what belongs in candidate content**;
- **exit-code handling**, including the M1a in-progress exit code;
- that recorded outcomes are **observations/claims only** — the kernel enforces claim ≠ acceptance structurally (`INV-003`, `INV-011`); role separation is process discipline, documented rather than kernel-enforced at this stage.

## Depends on

`TASK-M1-001`, `TASK-M1-002` — the playbook documents the SCN-007 command surface and pending-mode exit codes, so guidance must not precede the commands it documents.

## Out of scope

Any code change; any kernel enforcement of role separation; M1b adapter work.

## Must not change

Canonical contracts. The playbook is informative operational guidance (like `PLAYBOOK-CLI-USAGE`); canonical semantics stay in the contracts it cites.

## Acceptance

- the playbook exists under `docs/playbooks/`, is indexed in `docs/INDEX.md`, and covers every bullet above;
- a ship agent and a separate verification agent can drive one Work through the ledger (claim → settlement + candidate → verdict with `evidence_refs`) following only the playbook, with no agent recording a decision;
- `python3 scripts/docs_check.py` passes.
