---
id: CONFORMANCE-PORTABLE-KIT
type: contract
status: current
authority: normative
description: Language-neutral I/O contract for the portable conformance fixture kit under `conformance/` -- a conformance transport, not a new domain journal format.
---

# CONFORMANCE-PORTABLE-KIT -- the portable conformance kit

Design source: issue #313, `docs/delivery/M3-harden-the-loop.md`'s
portable-fixture investment note, `docs/delivery/task-cards/TASK-PORTABLE-CONFORMANCE.md`.

## Purpose and non-purpose

Someone implementing the documented `STATE-DELIVERY` transition contract
without Python needs a way to check their implementation's *observable*
results against the real reference core, without reading Python source,
importing a Python object, or running a Python fixture generator. This
kit is that check. It is:

- **bounded evidence** for the named cases below, never a certification
  that an implementation is complete or bug-free;
- a **conformance transport** over the existing `PORT-JOURNAL-ENVELOPE`
  shape and the existing `STATE-DELIVERY` reducer/policy contract --
  it invents no new domain journal format, no new Fact/Decision/Effect
  vocabulary, and no new semantics beyond what `docs/contracts/` and
  `docs/scenarios/` already state normatively.

It is emphatically **not** a rewrite of `orc-werk`'s core in another
language, and not a promise that passing this kit's cases makes an
implementation drop-in production-ready.

## Location and versioning

Everything a consumer needs lives under `conformance/` at the repository
root:

```
conformance/
  manifest.json          -- case index: id, title, mapped contract/scenario IDs
  cases/CASE-NNN-*.json  -- one static, versioned fixture per case
  reference/run_case.py  -- reference driver (Python; read for its shape only)
  checker.py             -- reference checker/CLI (Python; optional to use)
```

Every case file and the manifest carry `"schema_version": 1`. A future
breaking change to the input or expected-output shape bumps this integer;
existing case files at schema version 1 remain valid and are never
silently reinterpreted under a new schema. Adding a case, a `maps_to`
entry, or an `expected` key is additive and does not require a version
bump; changing the *meaning* of an existing key does.

## The case fixture (`conformance/cases/CASE-NNN-*.json`)

Each file is one static JSON object, portable to any language with a JSON
parser -- no Python object, enum, or import path anywhere in it:

```json
{
  "schema_version": 1,
  "case_id": "CASE-001-happy-path-acceptance",
  "title": "...",
  "maps_to": ["SCN-001", "INV-003", "..."],
  "description": "...",
  "input": {
    "delivery_run_id": "run-1",
    "history": [ /* ordered PORT-JOURNAL-ENVELOPE records, see below */ ]
  },
  "expected": { /* subset-equality projection of the driver's stdout, see below */ }
}
```

`maps_to` names the current stable contract/scenario IDs (`SCN-*`,
`INV-*`, `CONF-*`) this case is evidence for. It is informative
cross-referencing, not itself part of the wire contract a driver must
satisfy.

### `input` -- the journal-envelope replay boundary

`input.history` is an ordered list of envelopes in the *exact* on-disk
shape a real `.orc/*/journal.jsonl` line has (`PORT-JOURNAL-ENVELOPE`):

```json
{"schema_version": 1, "seq": 1, "delivery_run_id": "run-1", "kind": "fact", "id": "FACT-WORK-CREATED", "data": {...}, "extensions": {}}
```

`kind` is one of `"fact"`, `"decision"`, `"effect"`; `seq` is the replay
order. A case's `history` always opens with an `FX-CREATE-WORK` effect
envelope (carrying `data.plan` and, where the case is testing a specific
or legacy budget, `data.max_attempts`/`data.max_assurance_attempts`)
followed by `fact` envelopes in dispatch order. This is the *same*
replay a real `JournalPort.load_projection` performs
(`CONF-JOURNAL-003`): both run-scoped budgets are derived from the
history's own `FX-CREATE-WORK` record, per `SCN-008`'s single-authority
ruling (issue #240) and `SCN-021`'s legacy-fallback amendment -- never
supplied out of band alongside the history. A conforming driver MUST NOT
accept, require, or honor a caller-supplied budget override; deriving it
from anything other than the given `history` is itself a conformance
failure this kit's replay-budget cases are built to catch.

This is a **replay-focused** boundary: it exercises the pure
fact-folding/policy-decision core (`orc_werk.core` in the reference
implementation) reachable from a journal's own recorded history. It
deliberately does not cover the `WorkGraphPort`/`ExecutionPort`
dependency-fan-in *dispatch-eligibility* surface (`CONF-WORK-001`,
`PORT-WORK-GRAPH`) or the `CAP-*` capability-negotiation surface
(`SCN-006`): those are provider/adapter concerns outside a pure replay,
not something a `history` list can exercise. See "Not covered" below.

### `expected` -- subset-equality over the driver's stdout

`expected` is compared against the driver's parsed stdout JSON under
**subset equality**: for every key present in `expected`, the same key
MUST be present in `observed` with an equal value (dicts compared
key-by-key recursively under the same rule; lists compared
element-by-element, same length, same rule per element; `bool` is never
treated as equal to `1`/`0`). A key `expected` does not mention is never
checked and never causes a mismatch -- this lets a case assert only the
fields it cares about, without pinning every field the driver happens to
emit. Missing or changed keys `expected` *does* mention are always a
mismatch. This is the entire comparison rule; no adapter may weaken it,
and a comparison that accepts any non-error output regardless of content
is not a conforming checker.

## The driver command boundary (the transport)

A driver is any executable, in any language, invoked as a subprocess
(never imported, never linked) that:

1. Reads **exactly one JSON object** on stdin:
   `{"delivery_run_id": "<string>", "history": [<envelope>, ...]}` --
   the case's `input` block, verbatim. The driver receives **only** this
   input; it is never given the case's `expected` block, the `case_id`,
   `title`, or `maps_to`. A driver that could see its own expected
   answer could pass by echoing it back without implementing anything --
   this is a hard trust boundary the checker enforces by construction
   (it never serializes `expected` onto the driver's stdin).
2. Performs the replay described above: derive both budgets from the
   history's own `FX-CREATE-WORK` record, fold every `fact` envelope in
   `seq` order under those derived budgets, then report the
   currently-applicable next Decision/Effect(s) per Work (or none, where
   the Work is already resting on nothing pending).
3. Writes **exactly one JSON object** to stdout:
   - On success: `{"kit_version": 1, "outcome": "ok", "derived_max_attempts": <int>, "derived_max_assurance_attempts": <int>, "projection": {<work_id>: {...}}, "decisions": {<work_id>: {"decision": {...}, "effects": [...]}, or null}}`.
   - On a legally-rejected fact (an illegal transition, a validation
     failure, a fingerprint/conflict violation -- anything the reducer
     itself would raise `CoreError`/`ValueError` for): `{"kit_version": 1, "outcome": "error", "failing_fact_index": <int|null>, "failing_fact_id": <string|null>, "failing_work_id": <string|null>, "error": {"error": "<canonical ERR-* id>", "message": "<string>", "details": {...}}}`.
     `failing_fact_index` counts only `kind: "fact"` envelopes (0-based),
     matching the natural "which fact in my own fold loop failed" index
     a driver already has; it is never an index into the full `history`
     including effect/decision envelopes.
4. Exits `0` in both cases above (a driver **crash** -- non-zero exit,
   unparseable stdout -- is always a checker failure, never silently
   treated as a passing `"error"` outcome).

A comparison against `expected.error` pins the canonical `error` id
(`ERR-VALIDATION`, `ERR-CONFLICT`, ...) and observable state fields
(`failing_fact_id`, `failing_work_id`) -- never `message` wording, which
is documented informative-only and MAY vary by implementation/locale.

This is the entire wire contract. It pins no Python dataclass layout, no
incidental UUID, no private function name, and no field beyond the ones
named above. `projection` and `decisions` entries mirror the canonical
`WorkProjection`/`Decision`/`Effect.to_dict()` shapes documented in
`docs/contracts/`, `docs/domain/state-delivery.md`,
`docs/domain/facts.md`/`decisions.md`/`effects.md` -- a driver derives
its own output shape from those normative documents, not from reading
`src/orc_werk/core/*.py`.

Any implementation satisfying steps 1-4 is a drop-in substitute for the
reference driver via `checker.py --driver-cmd "<command>"`; the checker
never imports or introspects the driver, only pipes JSON to its stdin and
parses JSON from its stdout.

## Coverage (`conformance/manifest.json`)

23 cases (`CASE-001` through `CASE-023`) currently cover:

- happy-path acceptance (`SCN-001`);
- rejected verdict then a retry that accepts (`SCN-002`);
- execution failure then a retry that accepts (`SCN-003`);
- execution retry-budget exhaustion, both under the schema default and a
  legacy journal with no recorded `max_attempts` at all (`SCN-004`,
  `SCN-008`);
- execution pending and assurance pending, the two `SCN-007` legs;
- fresh-process replay under a recorded non-default retry budget
  (`SCN-008`);
- candidate fingerprint mismatch at assurance settlement, rejected with
  `ERR-CONFLICT` (`INV-007`/`INV-008`);
- a malformed (non-canonical) assurance verdict, rejected with
  `ERR-VALIDATION` rather than silently guessed toward a real verdict
  (`CONF-ASSURE-006`);
- bounded inconclusive assurance re-request and exhaustion, plus the
  legacy assurance-budget fallback of `1` (`SCN-021`, `ADR-0006`,
  `CONF-ASSURE-008`);
- exact-candidate verdict inheritance on re-observation, including the
  no-inheritable-verdict resting conflict and its abandon-driven recovery
  (`SCN-009`);
- attempt abandonment from an unresolved candidate-observation conflict,
  from an unsettleable in-flight assurance, and from a null (no
  candidate ever bound) settled execution (`SCN-010`, `SCN-014`,
  `STATE-DELIVERY` mechanical fact sequencing item 9, `CONF-CAND-004`);
- operator cancellation from `READY`/`EXECUTING`/`ASSURING`, and its
  rejection as illegal from a terminal `ACCEPTED` state (`SCN-011`,
  `CONF-JOURNAL-004`).

See `conformance/manifest.json` for the authoritative, exact list with
each case's mapped IDs.

### Not covered

This kit's replay boundary is the pure fact-fold/policy-decide core
reachable from a `history` list alone. The following are **explicitly
not exercised** here and MUST NOT be inferred as passing from a green
run of this kit:

- `WorkGraphPort` dependency fan-in *dispatch-eligibility* mechanics
  (`SCN-005`, `CONF-WORK-001`/`002`/`004`) -- these live on the
  provider-adapter side of the `WorkGraphPort` boundary, not in a fact
  replay; `SCN-005`'s fan-in behavior is a port-level test, covered by
  `tests/conformance/test_work_graph_conformance.py`, not this kit.
- Capability negotiation / unsupported-capability failure (`SCN-006`,
  `CONF-EXEC-004`) -- adapter-selection policy over `CAP-*` strings, not
  a fact-fold outcome.
- Extension producer/consumer conformance (`CONF-EXT-*`,
  `docs/conformance/extensions.md`) -- already has its own dedicated
  conformance suite and normative document; out of this kit's scope by
  design, not by oversight.
- CLI presentation, `orc census`/`orc verdict` aggregate reads
  (`CONF-CLI-CENSUS-*`) -- ledger-wide, filesystem-backed commands, not
  single-run replay.
- Real adapter I/O (`adapters/jsonl`, git candidate identity,
  `acpx`/ACP execution) -- this kit's `history` is always given, never
  produced by a live adapter.

A driver passing every case in this kit is evidence it correctly
implements the named replay boundary for the named scenarios -- it is
not proof that every contract in `docs/contracts/` and
`docs/scenarios/` is complete, and it is never to be represented as
full-implementation certification.

## Running the kit

```
python3 conformance/checker.py                 # run every case against the reference driver
python3 conformance/checker.py CASE-001-...     # run one case
python3 conformance/checker.py --driver-cmd "your-binary"   # substitute another implementation
python3 conformance/checker.py --probe          # falsification probes: prove the checker rejects wrong output
```

`checker.py` is the reference checker: convenient, not required. Any
other language MAY read `manifest.json` and `cases/*.json` directly (both
are plain JSON, no Python needed) and implement its own subset-equality
comparison per the rule stated above -- no Python is required to *consume*
this kit, only (optionally) to run its bundled reference checker/driver.

## Falsification probes

`checker.py --probe` runs the real reference driver against a subset of
cases, then deliberately corrupts a copy of each case's `expected` block
(claims a wrong terminal state, a wrong candidate binding, a wrong
replay-budget outcome, a wrong pending behavior, a wrong error id, a
wrong `outcome`, and a type-confused value) and asserts that
`subset_equal` rejects each corrupted claim against the real, unmutated
observed output. A probe that is *not* rejected is a bug in the checker,
and fails the run -- this is how the kit demonstrates its own comparison
actually discriminates right from wrong output, rather than trivially
accepting anything.

## Extending the kit

A new case is a new `conformance/cases/CASE-NNN-*.json` file plus a new
entry in `conformance/manifest.json`; both are additive, so adding a
case never invalidates an existing consumer. A case's `expected` block
MUST be authored by asserting it against the real reference core's
actual output (never hand-guessed), so that a case can never enshrine a
core bug as the "expected" behavior; where a real bug is found through
this process it is fixed in `src/orc_werk/core`, never worked around by
loosening a fixture.
