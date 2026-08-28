# Orc Werk

> **work, work**

Orc Werk is a docs-driven, contract-first orchestration kernel for autonomous work delivery.

It defines stable product semantics for work graphs, external execution, exact candidates, assurance, decisions, journaling, and versioned extensions while treating Beads, zxro, ACP/acpx, Git, no-mistakes, CI, and future systems as replaceable adapters.

## Product thesis

> Our semantics are authoritative. Providers adapt to Orc Werk; Orc Werk does not inherit provider semantics.

Orc Werk is the contract and opinionated delivery model. Python is the v0.x reference implementation used for fast dogfooding, fault injection, and recovery experimentation; implementation language is not part of the product contract.

## Start here

1. [`docs/product/thesis.md`](docs/product/thesis.md)
2. [`docs/product/principles.md`](docs/product/principles.md)
3. [`docs/contracts/invariants.md`](docs/contracts/invariants.md)
4. [`docs/domain/ubiquitous-language.md`](docs/domain/ubiquitous-language.md)
5. [`docs/contracts/ports/README.md`](docs/contracts/ports/README.md)
6. [`docs/contracts/extensions.md`](docs/contracts/extensions.md)
7. [`docs/scenarios/README.md`](docs/scenarios/README.md)
8. [`docs/delivery/M0-pure-core.md`](docs/delivery/M0-pure-core.md)
9. [`docs/research/README.md`](docs/research/README.md)

## Docs-driven development rule

Do not solve a missing contract by inventing behavior in implementation.

When behavior is ambiguous:

1. identify the missing semantic;
2. update or propose the canonical contract;
3. add/update its invariant or scenario;
4. only then implement it.

Normative prose should have one canonical home. Other documents reference stable IDs instead of duplicating the rule.

Specialized semantics that are not required by the generic delivery state machine belong in versioned extensions rather than becoming mandatory core fields. The first registered example is `review-findings/v1` for structured code-review findings.

## Repository shape

```text
docs/        normative product/domain/contracts/extensions/scenarios and delivery plans
src/         Python reference implementation; core must remain integration-free
tests/       core, conformance, and end-to-end scenario tests
scripts/     documentation integrity tooling
```

See [`docs/architecture/repository-structure.md`](docs/architecture/repository-structure.md) for the concrete Python package layout and dependency rules.

## Documentation integrity

Run:

```bash
python3 scripts/docs_check.py
```

The checker validates unique document IDs, required frontmatter, and internal stable-ID references.
