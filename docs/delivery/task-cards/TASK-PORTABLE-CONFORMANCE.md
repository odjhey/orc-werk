---
id: TASK-PORTABLE-CONFORMANCE
type: task-card
status: current
authority: normative
description: A versioned, language-neutral JSON/JSONL portable conformance fixture kit under conformance/, letting any implementation of the documented STATE-DELIVERY replay boundary check its observable results without Python -- the portable-fixture investment named in M3-harden-the-loop.md.
implements: []
verifies: []
---

# TASK-PORTABLE-CONFORMANCE -- portable conformance fixture kit

Design source: issue #313, `docs/delivery/M3-harden-the-loop.md`'s
portable-fixture investment note. Not tied to any M-series milestone: a
standalone tooling card, dispatched directly by run id rather than as a
milestone-sequenced card.

## The gap

Every existing conformance artifact under `tests/conformance/` and
`docs/conformance/` is authoritative but Python-shaped: pytest fixtures,
Python dataclass construction, and in-process reducer calls. Someone
implementing the documented `STATE-DELIVERY` transition contract in
another language has no way to check their implementation's observable
results against the real reference core short of reading and
re-deriving the pytest suite by hand. `M3-harden-the-loop.md` names this
gap explicitly as a deliberately-deferred, not-yet-shipped investment.

## Outcome

`conformance/` at the repository root: a versioned, static JSON fixture
corpus (`cases/CASE-NNN-*.json`, `manifest.json`) plus a small,
normatively-documented stdin/stdout driver command boundary
(`docs/conformance/portable-kit.md`, id `CONFORMANCE-PORTABLE-KIT`) any
language can implement to be checked by the reference checker
(`conformance/checker.py`) or to build its own comparison against the
same plain-JSON fixtures. No Python object, import path, enum, or
dynamic fixture generation is required to *consume* the kit -- only
(optionally) to run its bundled reference driver/checker.

The kit is a **conformance transport** over the existing
`PORT-JOURNAL-ENVELOPE` shape and the existing `STATE-DELIVERY`
reducer/policy contract, not a new domain journal format and not a
product-language rewrite. It is bounded evidence for the named
scenarios below, never proof that every contract in `docs/contracts/`
is complete.

## In scope

- `docs/conformance/portable-kit.md` (`CONFORMANCE-PORTABLE-KIT`,
  normative I/O contract, published before the driver's implementation
  per the docs-first requirement).
- `docs/conformance/README.md`: a link to the portable kit doc.
- `conformance/manifest.json`: the case index, mapping each `case_id` to
  its current stable `SCN-*`/`INV-*`/`CONF-*` IDs.
- `conformance/cases/CASE-001-*.json` through `CASE-023-*.json`: static,
  versioned input+expected fixtures, each authored by asserting it
  against the real reference core's actual output.
- `conformance/reference/run_case.py`: the reference driver adapter
  (Python, subprocess-invoked, never imported by the checker).
- `conformance/checker.py`: the reference checker/CLI, including
  `--probe` falsification probes proving the checker's subset-equality
  comparison actually rejects wrong output.
- This card.

## Out of scope

- Any `src/` runtime change (the kit is read-only tooling over the
  existing `orc_werk.core` reducer/policy pair; no core behavior gap was
  found while authoring it).
- `WorkGraphPort` dependency fan-in dispatch-eligibility mechanics
  (`SCN-005`) and capability-negotiation failure (`SCN-006`) -- both are
  provider/adapter-boundary concerns a pure fact-replay `history` cannot
  exercise; already covered by
  `tests/conformance/test_work_graph_conformance.py` and
  `tests/scenarios/test_scn_006_*.py` respectively.
- Extension producer/consumer conformance (`CONF-EXT-*`) -- has its own
  dedicated document and suite; out of this kit's scope by design.
- `orc census`/`orc verdict` and any other CLI/ledger-wide aggregate
  read -- filesystem-backed, not single-run replay.
- A non-Python second driver implementation -- this card ships the
  contract and the reference adapter; writing a second-language driver
  against that contract is a separate, later effort this task
  deliberately does not block on.
- Root `README.md`, `docs/INDEX.md`, and the product/playbook guides --
  owned by a parallel docs lane landing adoption-facing prose in the
  same window; this card links the kit from the existing conformance
  index only.

## Acceptance

- `conformance/manifest.json` and every `conformance/cases/*.json` file
  parse as plain JSON with no Python-specific construct, and each case's
  `expected` block is satisfied by running `conformance/checker.py`
  against the real reference core (`python3 conformance/checker.py`
  exits 0, printing `PASS` for all 23 cases).
- `python3 conformance/checker.py --probe` exits 0, printing `PROBE OK`
  for every falsification probe (wrong acceptance, wrong candidate
  binding, wrong replay-budget outcome, wrong pending behavior, wrong
  error id, wrong outcome, and a type-confused value) -- proving the
  checker's comparison rejects incorrect driver output rather than
  accepting any non-error output.
- `docs/conformance/portable-kit.md` states the full stdin/stdout wire
  contract, the subset-equality comparison rule, and the exact coverage
  and non-coverage list, and is linked from
  `docs/conformance/README.md`.
- `env -u ORC_JOURNAL_DIR bash scripts/check.sh` remains green,
  unmodified and unweakened.

## Ambiguities and design decisions made within this card's scope

- **Case ID vs. semantic dispatch.** `case_id` is an opaque correlation
  string a driver never sees (only `input` is placed on its stdin); no
  driver behavior may branch on it. Resolved without escalation -- this
  is exactly the docs-first trust-boundary requirement this card's
  contract states normatively.
- **`failing_fact_index` indexing.** Counts only `kind: "fact"` envelopes
  (0-based), not a raw index into the full `history` including
  effect/decision envelopes, matching the natural index a driver's own
  fact-folding loop already tracks. Recorded in
  `docs/conformance/portable-kit.md`; a mechanical choice, not a
  contract question.
- **Error message wording.** `expected.error` never pins `message` text,
  only the canonical `error` id and observable state fields
  (`failing_fact_id`, `failing_work_id`) -- per the explicit instruction
  that error assertions must not pin reference wording.
