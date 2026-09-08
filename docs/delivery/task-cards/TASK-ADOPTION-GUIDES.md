---
id: TASK-ADOPTION-GUIDES
type: task-card
status: current
authority: normative
description: Adoption portability — a tool-independent practice guide and an independent-implementation/bring-your-own-CLI walkthrough, with an explicit entry-point choice alongside the existing Python CLI path.
implements: []
verifies: []
---

# TASK-ADOPTION-GUIDES — practice-only and independent-implementation adoption guides

Design source: issue #312, following the docs-readiness audit (operator
instruction, 2026-09-08, "watchtower instruction to handle adoption
portability"). Not tied to any M-series milestone: a standalone docs card,
dispatched directly by run id.

## The gap

`PRODUCT-ADOPTION` and `docs/playbooks/agent-onboarding.md` describe
adoption entirely in terms of installing and driving the Python `orc` CLI.
Nothing tells an adopter who has neither Python nor `orc` (no interpreter,
no package, no willingness to run either) how to run the seat protocol by
hand, and nothing tells a team that wants to build their own
non-Python implementation what the minimum conforming surface actually is
without reading the Python source. Both are real adopters this repository's
own thesis (`PRODUCT-THESIS`: "a future implementation in Go or another
language must conform to the same contracts and scenarios") already
promises are legitimate, but neither had a walkthrough.

## Outcome

Two new playbooks, plus navigation and an explicit entry-point choice, so an
adopter picks the right rung in one read instead of guessing:

1. **`docs/playbooks/practice-adoption.md`** (`PLAYBOOK-PRACTICE-ADOPTION`)
   — the practice-only path. Requires neither Python/`orc` nor
   OMP/GitHub/Beads. Maps an adopter's existing tracker, executor,
   independent verifier, and evidence store onto the canonical roles, walks
   one real work through intent, immutable candidate identity, a pushed ship
   observation, an independently derived and bound verdict, acceptance, and
   fresh-session recovery, and names exactly which guarantees are manual
   discipline versus mechanically enforced by the reference kernel. It does
   not claim a manual checklist is a conforming kernel.
2. **`docs/playbooks/implementers-guide.md`** (`PLAYBOOK-IMPLEMENTERS-GUIDE`)
   — the independent-implementation / bring-your-own-CLI walkthrough. Gives a
   concrete reading/build order, the minimum port obligations, the record
   envelope and where its schema/version come from, replay/reconciliation
   and idempotency ordering, candidate binding, bounded retry and assurance
   budgets, pending-vs-terminal state, error handling, and interoperability
   boundaries, and explicitly separates reference-CLI-specific conventions
   (flags, config shape, file layout, output schemas) from what every
   conforming implementation must reproduce. It includes complete worked
   portable JSONL record examples (adapted from a real accepted-after-retry
   run in this repository's own ledger) and an observable verification
   checklist — never "read the Python source" as a substitute step. It does
   not claim that the existing conformance suites certify all of
   conformance by themselves; it names what they cover and what an
   implementer must additionally verify.
3. **`docs/product/adoption.md`** gains an explicit "choose your entry
   point" decision surface distinguishing four paths — practice-only, the
   reference Python CLI, custom composition around the Python package
   (`PLAYBOOK-CLI-USAGE`'s composition-layer guidance), and a genuinely
   independent implementation — so the choice is made once, at the top,
   rather than discovered by reading every playbook.
4. `README.md` and `docs/INDEX.md` gain the navigation to reach both new
   playbooks from the root, without duplicating any normative contract text
   they already cite by stable ID.

## In scope

- `docs/playbooks/practice-adoption.md` (new).
- `docs/playbooks/implementers-guide.md` (new).
- `docs/product/adoption.md`: an entry-point section near the top.
- `README.md`: a pointer to the entry-point section and both new playbooks.
- `docs/INDEX.md`: navigation entries for both new playbooks and this task
  card.
- This task card.

## Out of scope

- Any change under `docs/conformance/` or `conformance/` (owned by the
  parallel portable-conformance-kit lane; this task links only the
  existing `docs/conformance/README.md`, which is the correct, current
  conformance entry point).
- Any `src/` change — these are documentation-only guides.
- Building or maintaining a second production implementation (Go, JS, or
  otherwise). The independent-implementation guide is a walkthrough for
  someone who chooses to build one; this task does not build one, and any
  portability proof exercised against it is a throwaway verification
  exercise, not a new maintained codebase.
- Restating normative contract prose (`ORCHESTRATION-CONTRACT`,
  `CONTRACT-INVARIANTS`, `STATE-DELIVERY`, `PROTOCOL-FACTS`,
  `PROTOCOL-DECISIONS`, `PROTOCOL-EFFECTS`, port contracts,
  `CONTRACT-EXTENSIONS`, `CONTRACT-ERRORS`, `CONTRACT-STORAGE-CONCURRENCY`,
  `CONTRACT-DURABILITY`) — both guides cite stable IDs instead.

## Contract obligations

- `DOCS-ROOT`'s authoring rules: no duplicated MUST/ONLY/REQUIRED prose;
  cite the owning stable ID.
- `CONTRACT-EXTENSIONS`, `PROTOCOL-FACTS`/`PROTOCOL-DECISIONS`/
  `PROTOCOL-EFFECTS`, `STATE-DELIVERY`, and the port contracts remain the
  sole normative source for the vocabulary and record shapes both guides
  walk through.
- `ADR-0003`: implementation language is not part of the product contract;
  the independent-implementation guide must not smuggle Python-specific
  behavior in as if it were required.
- `PRODUCT-ADOPTION`'s existing rungs and install path for the Python CLI
  stay intact and supported; the entry-point section adds a choice, it does
  not replace or narrow the ladder.

## Produces

- `PLAYBOOK-PRACTICE-ADOPTION`
- `PLAYBOOK-IMPLEMENTERS-GUIDE`
- An entry-point section on `PRODUCT-ADOPTION`.
- Navigation entries on `DOCS-ROOT`'s index (`DOCS-INDEX`) and root
  `README.md`.

## Consumes

- `ORCHESTRATION-CONTRACT`, `CONTRACT-INVARIANTS`, `STATE-DELIVERY`,
  `PROTOCOL-FACTS`, `PROTOCOL-DECISIONS`, `PROTOCOL-EFFECTS`,
  `PORTS-INDEX` and each port document, `PORT-JOURNAL`'s envelope,
  `CONTRACT-EXTENSIONS`, `CONTRACT-ERRORS`, `CONTRACT-STORAGE-CONCURRENCY`,
  `CONTRACT-DURABILITY`, `CONFORMANCE-INDEX`, `ADR-0003`, `ADR-0005`,
  `ADR-0006`, `PLAYBOOK-WATCHTOWER`, `PLAYBOOK-ENGINEERING-METHOD`,
  `PRODUCT-ADOPTION`, `PLAYBOOK-CLI-USAGE`, `docs/cli/README.md`
  (`CLI-REFERENCE`).

## Must not change

- Any file under `docs/conformance/` or `conformance/`.
- Any `src/` file.
- The existing Python install path or CLI reference documentation's
  meaning (informative cross-references only).

## Acceptance criteria

1. `docs/playbooks/practice-adoption.md` requires neither Python/`orc` nor
   OMP/GitHub/Beads to follow; it maps tracker, executor, independent
   verifier, and evidence store to the canonical roles, walks one real work
   through intent, immutable candidate identity, ship observation,
   independently bound verdict, acceptance, and fresh-session recovery, and
   explicitly names which guarantees are manual versus mechanically
   enforced. It states plainly that a manual checklist is not a conforming
   kernel.
2. `docs/playbooks/implementers-guide.md` gives a concrete reading/build
   order, the minimum port obligations, the record envelope and its
   schema/version sources, replay/reconciliation and idempotency ordering,
   candidate binding, bounded retry and assurance budgets, pending-vs-
   terminal state, error handling, and interoperability boundaries; it
   distinguishes reference-CLI-specific conventions from universal
   requirements; it includes complete worked portable record examples and
   an observable verification checklist, with no instruction to read Python
   source or import a Python module as a substitute for reading the
   contracts.
3. Both new playbooks are reachable from `README.md` and `docs/product/
   adoption.md`; neither duplicates normative rules already owned
   elsewhere. The existing Python install path in `PRODUCT-ADOPTION`
   remains fully documented and supported. Neither guide claims the
   existing conformance suites certify all of conformance from a small
   example alone.
4. This task card exists before/alongside the guides it describes.
5. `python3 scripts/docs_check.py` and `bash scripts/check.sh` (run with
   `ORC_JOURNAL_DIR` unset) stay green; the practice-only walkthrough is
   smoke-tested end to end without invoking Python or `orc`.

## Verification commands

```bash
python3 scripts/docs_check.py
env -u ORC_JOURNAL_DIR bash scripts/check.sh
```
