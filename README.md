# Orchestration Kernel

A docs-driven, contract-first orchestration kernel for autonomous work delivery.

The project defines stable product semantics for work graphs, external execution, exact candidates, assurance, decisions, and journaling while treating Beads, zxro, ACP/acpx, Git, no-mistakes, CI, and future systems as replaceable adapters.

## Product thesis

> Our semantics are authoritative. Providers adapt to the kernel; the kernel does not inherit provider semantics.

## Start here

1. [`docs/product/thesis.md`](docs/product/thesis.md)
2. [`docs/product/principles.md`](docs/product/principles.md)
3. [`docs/contracts/invariants.md`](docs/contracts/invariants.md)
4. [`docs/domain/ubiquitous-language.md`](docs/domain/ubiquitous-language.md)
5. [`docs/contracts/ports/README.md`](docs/contracts/ports/README.md)
6. [`docs/scenarios/README.md`](docs/scenarios/README.md)
7. [`docs/delivery/M0-pure-core.md`](docs/delivery/M0-pure-core.md)

## Docs-driven development rule

Do not solve a missing contract by inventing behavior in implementation.

When behavior is ambiguous:

1. identify the missing semantic;
2. update or propose the canonical contract;
3. add/update its invariant or scenario;
4. only then implement it.

Normative prose should have one canonical home. Other documents reference stable IDs instead of duplicating the rule.

## Repository shape

```text
docs/        normative product/domain/contracts/scenarios and delivery plans
src/         implementation skeleton; core must remain integration-free
tests/       core, conformance, and end-to-end scenario tests
scripts/     documentation integrity tooling
```

## Documentation integrity

Run:

```bash
python3 scripts/docs_check.py
```

The checker validates unique document IDs, required frontmatter on normative docs, and internal stable-ID references.
