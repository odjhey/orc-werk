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
envelope, and that envelope's `data` is the *complete*, canonical
`PORT-JOURNAL-003` settled-effect-record shape a real journal persists --
not a reduced or driver-convenience subset:

```json
{"plan": {"works": [{"work_id": "A", "deps": []}]}, "max_attempts": 3, "max_assurance_attempts": 2, "dispatch_result": {"works": [{"id": "A", "delivery_run_id": "run-1"}]}}
```

`data.plan` names every planned Work (`PORT-WORK-001`); `data.dispatch_result`
is the reserved key `PORT-JOURNAL-003` (`docs/contracts/ports/journal-port.md`)
requires on every persisted effect record, carrying the dispatch outcome as
portable data. `PORT-WORK-001` defines the Work-creation plan/semantics but
does not specify a generic serialized create return; the shape above
(`{"works": [{"id": ..., "delivery_run_id": ...}]}`, one entry per Work
named in `plan`, in the same order) is this kit's own reference adapter's
illustrative example of what a `WorkGraphPort.create` implementation may
record there, not a canonical cross-adapter output format. A conforming
driver replays `data.dispatch_result` verbatim from the given `history`;
it never re-derives or validates its shape.
`data.max_attempts`/`data.max_assurance_attempts` are
present where the case is testing a specific or legacy budget (a case
testing the legacy fallback for one of these two fields omits it
entirely, exactly as a pre-existing-field journal would). Every `fact`
envelope's `data.work_id` names a Work that appears in this same
`FX-CREATE-WORK` record's `data.plan.works` list -- a `history` naming a
Work fact for a Work absent from the plan is not a legal
`PORT-JOURNAL-ENVELOPE` history and is never a case in this kit.

`fact` envelopes follow, in dispatch order. This is the *same*
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
   - On success: `{"kit_version": 1, "outcome": "ok", "delivery_run_id": <string>, "derived_max_attempts": <int>, "derived_max_assurance_attempts": <int>, "projection": {<work_id>: {...}}, "decisions": {<work_id>: {"decision": {...}, "effects": [...]}, or null}}`.
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

**The error-location fields are exact, mechanical, and phase-independent
-- never inferential, never conditioned on how far parsing got, and
never derived from `expected` or from any Python type.** For a failure
associated with a raw `history` entry whose own `kind` is exactly
`"fact"`:

- `failing_fact_index` is that entry's zero-based ordinal counted only
  among `kind: "fact"` envelopes in `history` -- non-fact envelopes
  never increment it, and it is never an index into the full `history`
  including effect/decision envelopes. This is the natural "which fact
  in my own fold loop failed" index a driver already has. Association
  is by the raw envelope's position alone, even when its `id` or `data`
  cannot be decoded into a valid Fact at all.
- `failing_fact_id` is that envelope's raw `id` field when that value is
  a JSON string, `null` otherwise. This is raw location context, not a
  validated/normalized registry lookup: a string is reported verbatim
  even when it is empty, or names no known Fact id, or names a Fact id
  whose own kind was rejected for an unrelated reason -- it is never
  hidden merely because it turned out to be unknown or malformed, and a
  non-string value (a number, `null`, or the key being absent entirely)
  is never stringified or guessed at.
- `failing_work_id` is that envelope's raw `data.work_id` when `data` is
  a JSON object and that value is a JSON string, `null` otherwise. This
  is read straight off the untrusted raw envelope, independent of
  whether Fact construction/validation itself succeeded -- a
  decode/validation failure that never got as far as constructing a
  Fact object still reports the `work_id` available on the raw
  envelope; it MUST NOT be hidden merely because the envelope itself
  turned out to be invalid.

All three fields are **always present** in an `"outcome": "error"`
response. A driver MUST NOT special-case any particular fact id, error
id, or `expected` value to decide any of the three; it is the same one
generic raw-location extraction rule for every failure this driver can
hit.

**All three location fields are `null` when there is no associated raw
fact envelope at all** -- a transport/configuration/budget failure
raised before the driver ever reaches a `kind: "fact"` envelope to index
into (a missing or non-string top-level `delivery_run_id`; `history`
itself not being a JSON array; one of its entries not being a JSON
object), or a failure associated only with an effect/non-fact envelope.
These are all canonical `ERR-VALIDATION` failures with no fact envelope
to attribute them to, so `failing_fact_index`, `failing_fact_id`, and
`failing_work_id` are all `null`; a driver MUST NOT fabricate an index
(such as `0`) or guess at a work id merely because no fact was ever
identified. Note the distinction from the fact-envelope case above: a
raw `kind: "fact"` envelope with a missing or wrong-typed `id` is still
**located** by its position (`failing_fact_index` is set, `failing_fact_id`
is `null`) -- a missing/wrong-typed `id` on an otherwise-identifiable
fact envelope is never conflated with there being no associated fact
envelope at all.

None of this changes the canonical error id vocabulary or adds a new
error class: the reported `error.error` remains the existing canonical
`ERR-*` value the reducer/policy itself would raise, and `error.message`
remains informative-only, unasserted text that MAY vary by
implementation/locale.

A comparison against `expected.error` pins the canonical `error` id
(`ERR-VALIDATION`, `ERR-CONFLICT`, ...) and observable state fields
(`failing_fact_id`, `failing_work_id`) -- never `message` wording, which
is documented informative-only and MAY vary by implementation/locale.

This is the entire wire contract. It pins no Python dataclass layout, no
incidental UUID, and no private function name. The shapes below are
**this kit's own normalized JSON encoding** for observational read-back
of the domain's Fact/Decision/Effect/derived-state concepts -- pinned
here exactly, field by field, because no other document defines a JSON
*serialization* of them; `docs/domain/state-machines/delivery.md` and
`docs/protocol/facts.md`/`decisions.md`/`effects.md` define the state
vocabulary and each Fact's *required data fields* (what a producer must
supply), never a consumer-facing wire layout, and MUST NOT be read as
asserting that this encoding is itself part of those contracts. This
document is that encoding's normative source, stated here in full so a
non-Python implementation never has to read `src/orc_werk/core/*.py` to
derive it. The encoding below derives *observable* pending markers from
the domain's raw historical lists rather than exposing the Python
reducer's own retained-pointer fields verbatim: a private replay-cursor
quirk of one implementation (e.g. "which pointer resets on which fact")
is not part of what a real adapter would ever need to observe, and this
kit does not require reproducing it.

**A `projection[work_id]` entry** (one per Work) -- this kit's own
normalized encoding of the domain's per-Work derived state
(`docs/domain/state-machines/delivery.md`'s `STATE-DELIVERY` transition
contract), not an assertion that this JSON layout is itself part of that
contract. It carries no `work_id` or `delivery_run_id` field of its own
-- both are already the map key and the request-level `delivery_run_id`
respectively, and duplicating them per entry would be redundant:

| field | type | meaning |
|---|---|---|
| `state` | string | one of `READY`, `EXECUTING`, `ASSURING`, `ACCEPTED`, `BLOCKED`, `CANCELLED` (`docs/domain/state-machines/delivery.md`) |
| `attempt_number` | int | count of `FACT-EXEC-STARTED` folded for this Work's lineage (`INV-018`) |
| `executions` | array of object | one entry per started Execution, in fold order; each is `{"execution_id": string, "outcome": "completed"\|"failed"\|null}`. `outcome` is `null` while that Execution is unsettled |
| `candidates` | object | `{candidate_id: {"fingerprint": string, "execution_id": string}}`, one entry per distinct candidate ever observed; `execution_id` is that candidate's most recently re-attributed Execution (`INV-006`'s exact-identity candidate may move forward across a same-fingerprint re-observation) |
| `current_candidate_id` | string or null | the candidate currently bound (pending or settled assurance), or `null`. Reset to `null` by `FACT-WORK-CANCELLED` |
| `assurances` | array of object | one entry per started Assurance, in fold order; each is `{"assurance_id": string, "candidate_id": string, "execution_id": string, "verdict": "accepted"\|"rejected"\|"inconclusive"\|null, "abandoned": bool}`. `verdict` is `null` while unsettled and gains a `PROTOCOL-FACTS` `ASSURANCE_VERDICTS` value once `FACT-ASSURE-SETTLED` folds for it -- no other verdict value exists. `abandoned` is `true` only for the one entry `FACT-ATTEMPT-ABANDONED` marked unsettleable (`SCN-010`); this is *not* a fourth verdict value -- `verdict` stays `null` on that same entry, never a string `"abandoned"` |
| `pending_execution_id` | string or null | the currently open (unsettled) Execution's id, derived by scanning `executions` for an entry with `outcome: null`; `null` when no Execution is open |
| `pending_assurance_id` | string or null | the currently open (unsettled, non-abandoned) Assurance's id, derived by scanning `assurances` for an entry with `verdict: null` and `abandoned: false`; `null` when no Assurance is open |
| `assurance_pending` | bool | `true` exactly when `pending_assurance_id` is non-null; a convenience boolean for a driver that would rather branch on a flag than a null check |
| `blocked_reason` | string or null | `null` when not `BLOCKED`; otherwise a free-form reason string -- `PROTOCOL-FACTS` documents `FACT-WORK-BLOCKED.reason` as free-form, and `docs/domain/state-machines/delivery.md`'s informative note says the v0 policy emits exactly `retry-budget-exhausted`, `assurance-inconclusive`, or `attempt-abandoned` today, but future policies MAY emit other values. A conforming driver MUST treat this as an open string, never a closed three-value enum |
| `blocked_confirmed` | bool | `true` once a confirming `FACT-WORK-BLOCKED` has been folded |
| `cancelled_reason` | string or null | the recorded cancellation reason, or `null` |
| `cancelled_confirmed` | bool | `true` once `FACT-WORK-CANCELLED` has been folded |
| `candidate_conflict` | object or null | `{"candidate_id": string, "reason": "fingerprint-mismatch"\|"no-inheritable-verdict"}` while an unresolved re-observation conflict rests unresolved (`STATE-DELIVERY` mechanical fact sequencing item 9), else `null` |

**A `decisions[work_id]` entry** is `null` when nothing is currently
pending for that Work, else `{"decision": {...}, "effects": [...]}`.

**`decision`** (this kit's normalized encoding of a `PROTOCOL-DECISIONS`
decision): `{"id": string, "data": object}`. `id` is one of
`DEC-DISPATCH`, `DEC-RETRY`, `DEC-REQUEST-ASSURANCE`, `DEC-ACCEPT`,
`DEC-BLOCK` (the five IDs `orc_werk.core.policy.decide` can produce;
`docs/protocol/decisions.md` names the full ID vocabulary, including the
two operator-only IDs this driver boundary never emits). `work_id` and
`delivery_run_id` are omitted here for the same reason as the
projection entry: both are already known from the enclosing map key and
the top-level request. `data`'s exact shape is fixed per `id`:

| `id` | `data` shape |
|---|---|
| `DEC-DISPATCH` | `{}` -- always empty. The attempt this dispatches is observable via the paired `FX-START-EXECUTION` effect's `idempotency_scope`, not decision data |
| `DEC-RETRY` | `{}` -- always empty, for the same reason as `DEC-DISPATCH` |
| `DEC-REQUEST-ASSURANCE` | `{"candidate_id": string, "assurance_number": int, "max_assurance_attempts": int}` -- the selected candidate, the requested next per-execution assurance index (the first assurance of an Execution is `1`), and the effective journal-derived assurance budget |
| `DEC-ACCEPT` | `{}` -- always empty |
| `DEC-BLOCK` | `{"reason": string}` -- the current canonical block reason, the same open string documented for `blocked_reason` above |

This is a bounded v0 observation profile, not the complete canonical
Decision/Effect data payload: `decide()`'s real `Decision.data`/
`Effect.data` MAY carry additional domain-internal fields (e.g. the
retry/assurance budget arithmetic folded alongside `DEC-BLOCK.data.reason`)
that a real adapter does not need, because `projection` and
`idempotency_scope` already expose everything else this kit observes.
The reference driver emits exactly the key sets above, never more; a
conforming comparator MUST NOT require any key outside them, and MUST
NOT treat their absence elsewhere as evidence of a missing field.

**Each `effects[]` entry** (this kit's normalized encoding of a
`PROTOCOL-EFFECTS` effect): `{"id": string, "data": object, "idempotency_scope": array}`.
`id` is one of `FX-START-EXECUTION`, `FX-START-ASSURANCE`,
`FX-COMPLETE-WORK`, `FX-BLOCK-WORK` (the four a `decide()` outcome can
carry; `docs/protocol/effects.md` names the full ID vocabulary and each
ID's target port). `data`'s exact shape is fixed per `id`, the same
bounded-profile discipline as `decision.data` above:

| `id` | `data` shape |
|---|---|
| `FX-START-EXECUTION` | `{}` -- always empty; its target attempt is explicit in `idempotency_scope` instead |
| `FX-START-ASSURANCE` | `{"candidate_id": string, "candidate_fingerprint": string, "assurance_number": int}` -- the selected candidate's exact identity/fingerprint and requested assurance index, identical to the corresponding `idempotency_scope` dimensions |
| `FX-COMPLETE-WORK` | `{}` -- always empty |
| `FX-BLOCK-WORK` | `{"reason": string}` -- the same value as the triggering `DEC-BLOCK.data.reason` |

`idempotency_scope` is this kit's own structured stand-in for
`INV-020`'s idempotency key -- never itself the domain's opaque
`|`-joined string, which is documented informative detail with no
pinned wire form -- as the fixed six-element array
`[delivery_run_id, work_id, target_execution_attempt_number, effect_id, candidate_fingerprint_or_null, assurance_number_or_null]`.
`target_execution_attempt_number` is the exact attempt the effect
targets: the *next* attempt (the Work's recorded execution-start count
plus `1`) for `FX-START-EXECUTION`, the Work's *current* recorded
attempt for every other effect. The fifth and sixth elements mirror
`orc_werk.core.idempotency.idempotency_key`'s own `FX-START-ASSURANCE`
branch: both are `null` for every other effect; for `FX-START-ASSURANCE`
the fifth is always that candidate's exact fingerprint (never `null` --
two different candidates assured at the same `assurance_number` MUST
NOT collide on the same scope; `INV-020` names `candidate_fingerprint`
as a required identity dimension of that key) and the sixth is
`decide()`'s requested `assurance_number` when it is greater than `1`,
else `null` (`INV-020`'s legacy first-assurance production-key omission
is unchanged -- the normalized observation still *names* assurance
number `1`, it just omits it from the sixth element, per
`INV-020`/`ADR-0006`). This observes the key's canonical identity
dimensions only, never a copy or split of the domain's own opaque
production key encoding. A case comparing `idempotency_scope` pins this
array shape, never a byte-for-byte reproduction of the domain's own
`|`-joined key string.

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

## CI drift protection

`tests/conformance/test_portable_kit_corpus.py` runs inside the same
`env -u ORC_JOURNAL_DIR bash scripts/check.sh` gate every other
conformance suite runs under -- the corpus is not a standalone,
unexercised artifact. It asserts, against the real reference core:

- every case in `conformance/manifest.json` passes
  `conformance/checker.py` (a regression in either the corpus or
  `orc_werk.core` turns this test, and therefore the gate, red);
- every `--probe` falsification probe correctly detects its corrupted
  claim (a false-accept regression in `subset_equal` turns this test
  red);
- a **deliberately wrong** `expected` value (an in-test mutation, never
  a corpus file on disk) is rejected by `subset_equal` against the real
  driver's real output -- this is the drift-protection proof itself:
  it demonstrates that a wrong acceptance claim reaching this corpus
  would fail the gate, not merely that today's corpus happens to agree
  with today's code.

## Extending the kit

A new case is a new `conformance/cases/CASE-NNN-*.json` file plus a new
entry in `conformance/manifest.json`; both are additive, so adding a
case never invalidates an existing consumer.

**`docs/contracts/`, `docs/scenarios/`, and `docs/domain/` are the
authority for what `expected` must say -- never the reference
implementation's current output.** A case's `expected` block is authored
first from the specific `SCN-*`/`INV-*`/`CONF-*` requirement named in its
`maps_to`/`description` (what the contract says must happen), and only
then checked by running the real reference core (`conformance/checker.py`)
to catch transcription mistakes -- a typo'd state name, a wrong field
path, an off-by-one index. If the reference core's actual output
disagrees with what the cited contract requires, that is a candidate
core bug: it is investigated and, if confirmed, fixed in
`src/orc_werk/core` and the contract docs are left standing (issue
#313's fail-closed rule) -- a case's `expected` is never quietly
loosened, and the reference run is never treated as itself defining
correctness. `tests/conformance/test_portable_kit_corpus.py`'s gate
membership is what keeps this true over time: a later change to
`src/orc_werk/core` that silently drifts a case's real output away from
its contract-derived `expected` fails the gate rather than passing
unnoticed.
