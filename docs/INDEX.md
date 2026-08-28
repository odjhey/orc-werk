---
id: DOCS-INDEX
type: index
status: current
authority: informative
description: Flat documentation index.
---

# Documentation index

## Product
- [Thesis](product/thesis.md)
- [Principles](product/principles.md)
- [Boundaries](product/boundaries.md)
- [Adoption guide](product/adoption.md)

## Domain
- [Ubiquitous language](domain/ubiquitous-language.md)
- [Delivery state machine](domain/state-machines/delivery.md)

## Contracts
- [Orchestration contract](contracts/orchestration-contract.md)
- [Invariant registry](contracts/invariants.md)
- [Errors](contracts/errors.md)
- [Capabilities](contracts/capabilities.md)
- [Extensions](contracts/extensions.md)
- [Durability responsibilities](contracts/durability-responsibilities.md)
- [Ports](contracts/ports/README.md)

## Protocol
- [Facts](protocol/facts.md)
- [Decisions](protocol/decisions.md)
- [Effects](protocol/effects.md)

## Extensions
- [Extension registry](extensions/README.md)
- [`review-findings/v1`](extensions/review-findings/README.md)
- [`execution-session/v1`](extensions/execution-session/README.md)
- [`crew-report/v1`](extensions/crew-report/README.md)

## Verification
- [Golden scenarios](scenarios/README.md)
- [Conformance](conformance/README.md)
- [Extension conformance](conformance/extensions.md)

## Architecture
- [Architecture index](architecture/README.md)
- [Repository structure and dependency rules](architecture/repository-structure.md)

## Adapters
- [Adapter contract and template](adapters/README.md)

## Initial adapter slots
- [Beads](adapters/beads/README.md)
- [zxro](adapters/zxro/README.md)
- [ACP/acpx](adapters/acp/README.md)
- [no-mistakes](adapters/no-mistakes/README.md)
- [Git candidate](adapters/git/README.md)

## Decisions
- [ADR-0001 Pure core](decisions/ADR-0001-pure-core.md)
- [ADR-0002 Candidate-bound assurance](decisions/ADR-0002-candidate-bound-assurance.md)
- [ADR-0003 Python-first reference implementation](decisions/ADR-0003-python-reference-implementation.md)
- [ADR-0004 Versioned extensions](decisions/ADR-0004-versioned-extensions.md)

## Research and lineage
- [Research lineage](research/README.md)

## Delivery
- [M0 pure core](delivery/M0-pure-core.md)
- [M1 delivery ledger](delivery/M1-delivery-ledger.md)
- [M2 close the loop](delivery/M2-close-the-loop.md)
- [Watchtower operations playbook](delivery/watchtower-operations.md)
- [Delivery stance](delivery/delivery-stance.md)
- [CLI usage guide](playbooks/cli-usage.md)
- [Agent CLI usage playbook](playbooks/agent-cli-usage.md)
- [CLI reference](cli/README.md)

## Dogfooding
- [Dogfood scenario corpus](../dogfood/README.md)

## M0 task cards
- [TASK-M0-001](delivery/task-cards/TASK-M0-001-core.md)
- [TASK-M0-002](delivery/task-cards/TASK-M0-002-work.md)
- [TASK-M0-003](delivery/task-cards/TASK-M0-003-scripted.md)
- [TASK-M0-004](delivery/task-cards/TASK-M0-004-journal.md)
- [TASK-M0-005](delivery/task-cards/TASK-M0-005-cli.md)
- [TASK-M0-006](delivery/task-cards/TASK-M0-006-ports-foundation.md)

## M1 task cards
- [TASK-M1-001](delivery/task-cards/TASK-M1-001-pending-scenario.md)
- [TASK-M1-002](delivery/task-cards/TASK-M1-002-pending-mode.md)
- [TASK-M1-003](delivery/task-cards/TASK-M1-003-cli-ux.md)
- [TASK-M1-004](delivery/task-cards/TASK-M1-004-durability-contract.md)
- [TASK-M1-005](delivery/task-cards/TASK-M1-005-acp-adapter.md)
- [TASK-M1-006](delivery/task-cards/TASK-M1-006-agent-cli-playbook.md)
- [TASK-M1-007](delivery/task-cards/TASK-M1-007-crew-report-log.md)
- [TASK-M1-008](delivery/task-cards/TASK-M1-008-run-report-renderer.md)

## M2 task cards
- [TASK-M2-001](delivery/task-cards/TASK-M2-001-no-mistakes-assurance.md)
- [TASK-M2-002](delivery/task-cards/TASK-M2-002-second-agent-provider-swap.md) (deferred out of M2)
- [TASK-M2-003](delivery/task-cards/TASK-M2-003-multi-work-real-dags.md)
- [TASK-M2-004](delivery/task-cards/TASK-M2-004-second-repo-adoption.md)
- [TASK-M2-005](delivery/task-cards/TASK-M2-005-policy-parameterization.md) (deferred out of M2)
- [TASK-M2-006](delivery/task-cards/TASK-M2-006-beads-mirror.md)
