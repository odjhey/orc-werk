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
3. [`docs/product/adoption.md`](docs/product/adoption.md) — when to adopt, and the entry-point choice between practice-only, the reference CLI, custom composition, or an independent implementation
4. [`docs/contracts/invariants.md`](docs/contracts/invariants.md)
5. [`docs/domain/ubiquitous-language.md`](docs/domain/ubiquitous-language.md)
6. [`docs/contracts/ports/README.md`](docs/contracts/ports/README.md)
7. [`docs/contracts/extensions.md`](docs/contracts/extensions.md)
8. [`docs/scenarios/README.md`](docs/scenarios/README.md)
9. [`docs/delivery/M0-pure-core.md`](docs/delivery/M0-pure-core.md)
10. [`docs/research/README.md`](docs/research/README.md)

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

## Using the CLI

The `orc` CLI is the reference way to dispatch and read delivery runs. See
[`docs/cli/README.md`](docs/cli/README.md) for the full command reference
(quickstart, flags, exit codes, config schema, journal layout).

## Adopting without Python or `orc`

Neither Python nor this repository's CLI is required to use Orc Werk's
model. `docs/product/adoption.md` lays out four supported entry points;
the two that need no Python/`orc` install at all are:

- [`docs/playbooks/practice-adoption.md`](docs/playbooks/practice-adoption.md)
  — run the seat protocol by hand with any tracker, executor, verifier, and
  evidence store you already have.
- [`docs/playbooks/implementers-guide.md`](docs/playbooks/implementers-guide.md)
  — build an independent, conforming implementation in any language against
  the contracts alone.

## Documentation integrity

Run:

```bash
python3 scripts/docs_check.py
```

The checker validates unique document IDs, required frontmatter, and internal stable-ID references.
