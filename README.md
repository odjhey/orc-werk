# Orc Werk

> **Work, work.**

Orc Werk is a docs-driven, contract-first orchestration kernel for autonomous work delivery. The name is a playful reference to the Warcraft III peon acknowledgement; the project is not affiliated with Blizzard Entertainment.

Orc Werk defines stable product semantics for work graphs, external execution, exact candidates, assurance, decisions, and journaling while treating Beads, zxro, ACP/acpx, Git, no-mistakes, CI, and future systems as replaceable adapters.

## Product thesis

> Our semantics are authoritative. Providers adapt to Orc Werk; Orc Werk does not inherit provider semantics.

Python 3.11+ is the initial reference implementation for the dogfood phase. Python is not part of the product contract: canonical domain, protocol, journal, and port semantics must remain language-independent so another implementation, including a future Go implementation, can conform without redefining the product.

## Start here

1. [`docs/product/thesis.md`](docs/product/thesis.md)
2. [`docs/product/principles.md`](docs/product/principles.md)
3. [`docs/contracts/invariants.md`](docs/contracts/invariants.md)
4. [`docs/domain/ubiquitous-language.md`](docs/domain/ubiquitous-language.md)
5. [`docs/contracts/ports/README.md`](docs/contracts/ports/README.md)
6. [`docs/scenarios/README.md`](docs/scenarios/README.md)
7. [`docs/architecture/repository-structure.md`](docs/architecture/repository-structure.md)
8. [`docs/research/README.md`](docs/research/README.md)
9. [`docs/delivery/M0-pure-core.md`](docs/delivery/M0-pure-core.md)

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
docs/        normative product/domain/contracts/scenarios plus research lineage and delivery plans
src/         Python reference implementation; core must remain integration-free
tests/       core, conformance, and end-to-end scenario tests
scripts/     documentation integrity tooling
```

See [`docs/architecture/repository-structure.md`](docs/architecture/repository-structure.md) for dependency rules and the concrete package layout.

## Documentation integrity

Run:

```bash
python3 scripts/docs_check.py
```

The checker validates unique document IDs, required frontmatter on normative docs, and internal stable-ID references.
