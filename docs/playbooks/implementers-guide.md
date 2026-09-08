---
id: PLAYBOOK-IMPLEMENTERS-GUIDE
type: playbook
status: current
authority: informative
description: Independent-implementation / bring-your-own-CLI walkthrough — reading order, minimum port obligations, record envelope, replay/idempotency, candidate binding, bounded budgets, error handling, interoperability boundaries, worked portable record examples, and an observable verification checklist for a non-Python conforming implementation.
---

# Independent implementation guide

This playbook is for someone building a conforming Orc Werk implementation
in a language other than Python, or composing a bespoke tool around the
canonical contracts without using the reference CLI's config/output shapes.
`ADR-0003` already commits the product to this being possible — "a future
implementation in Go or another language must conform to the same contracts
and scenarios" — this guide is the walkthrough that promise was missing.

This is one of four adoption entry points; see `PRODUCT-ADOPTION`'s "Choose
your entry point" section for how this compares to practice-only
(`PLAYBOOK-PRACTICE-ADOPTION`), the reference Python CLI, and custom
composition around the Python package.

**What this guide is not.** It is not a substitute for reading the
contracts themselves — every section below cites the owning stable ID
instead of restating its normative text (`DOCS-ROOT`'s authoring rule), and
you will open those documents. It is also not an instruction to read the
Python implementation's source as a spec — a conforming implementation is
derived from `docs/`, not from `src/orc_werk`. Nowhere below does this guide
say "see how `src/orc_werk` does it."

## 1. Reading and build order

Read in this order; each layer only makes sense once the one before it is
load-bearing in your head.

1. `ORCHESTRATION-CONTRACT` — the ten-clause constitutional boundary.
   Everything else refines this.
2. `CONTRACT-INVARIANTS` (`INV-001` through `INV-021`) — the enforceable
   rules a conforming implementation must satisfy. Read this in full before
   writing any code; most implementation mistakes are one of these
   invariants silently violated.
3. `STATE-DELIVERY` — the state machine you are implementing: states,
   transition table, and the eleven mechanical-fact-sequencing rules. This
   is the single most important document in this list.
4. `PROTOCOL-FACTS`, `PROTOCOL-DECISIONS`, `PROTOCOL-EFFECTS` — the closed
   vocabulary of Facts/Decisions/Effects the state machine emits and
   consumes. Build your enum/union types from these tables directly.
5. `PORTS-INDEX` and each of the five mandatory port documents
   (`PORT-WORK-GRAPH`, `PORT-EXECUTION`, `PORT-CANDIDATE`, `PORT-ASSURANCE`,
   `PORT-JOURNAL`) — the operations your adapters must expose. §2 below is
   the condensed obligation table; read the linked documents for the full
   operation-by-operation contract.
6. `PORT-JOURNAL`'s canonical record envelope section — the wire shape
   every persisted record must use. §4 below walks it in detail.
7. `CONTRACT-EXTENSIONS` — how to carry anything domain-specific (review
   findings, session provenance, your own private payloads) without
   touching the core.
8. `CONTRACT-ERRORS` — the closed error taxonomy your ports translate
   provider-native failures into.
9. `CONTRACT-STORAGE-CONCURRENCY` — required only if you build a durable
   local-file-backed journal yourself (most independent implementations
   will); locking, atomic replacement, append safety, and the durability
   level you must declare.
10. `CONTRACT-DURABILITY` — which non-core information needs an explicit
    durable owner if your deployment produces it (reports, provenance,
    anything else); the ownership matrix is the template for classifying
    your own additions.
11. `CONFORMANCE-INDEX` and `docs/conformance/extensions.md` — the
    acceptance tests your implementation is measured against, one
    `CONF-*` requirement per row. §12 below turns the relevant ones into an
    observable checklist you can run without any of this repository's own
    tooling.
12. `docs/scenarios/README.md` and the individual `SCN-*` golden scenarios —
    executable specifications; each one should become a test in your own
    suite.
13. `ADR-0003`, `ADR-0005`, `ADR-0006` — why the current shape is what it
    is. Not required to implement correctly, but each explains a design
    decision you will otherwise be tempted to "fix": ADR-0003 is why the
    reference implementation's language is irrelevant to your obligations;
    ADR-0005 is why there is no pull-observation port to implement (you
    never poll a live process's lifecycle — executors and verifiers always
    push their observations in); ADR-0006 is why an `inconclusive` verdict
    re-requests assurance instead of blocking outright.

## 2. Minimum port obligations

Five ports are mandatory (`PORTS-INDEX`). This table is a checklist of
*operations to expose*; the linked document is the operation-by-operation
contract, including required error behavior.

| Port | Operations you must expose | Document |
|---|---|---|
| WorkGraphPort | create, snapshot, ready, claim, complete, block | `PORT-WORK-GRAPH` |
| ExecutionPort | start, inspect (send/cancel/resume optional, capability-gated) | `PORT-EXECUTION` |
| CandidatePort | identify, current, compare | `PORT-CANDIDATE` |
| AssurancePort | request, inspect | `PORT-ASSURANCE` |
| JournalPort | append_fact, append_decision, append_effect_record, history, load_projection | `PORT-JOURNAL` |

Three ports are named but optional, added only when your deployment needs
the concept at all (`PORTS-INDEX`): AttentionPort, PlanningPort,
IntegrationPort. Do not build these speculatively — nothing in the core
state machine (`STATE-DELIVERY`) requires them.

A capability your adapter cannot genuinely deliver must fail explicitly
(`ERR-UNSUPPORTED-CAPABILITY`) rather than being silently approximated
(`INV-013`); this is the rule that keeps a thin/scripted implementation
honest while you build out real providers.

## 3. Record envelope and schema/version sources

Every persisted or interchanged record — fact, decision, or effect — uses
one canonical envelope, defined normatively at `PORT-JOURNAL`'s
`PORT-JOURNAL-ENVELOPE` section:

```json
{
  "schema_version": 1,
  "seq": 0,
  "delivery_run_id": "string",
  "kind": "fact | decision | effect",
  "id": "<FACT-*|DEC-*|FX-*>",
  "data": {},
  "extensions": {}
}
```

Sources of truth for each field, so you never have to guess a value's
shape:

- `schema_version` — an integer, starting at `1`. A future breaking change
  to this envelope shape bumps it; you branch on it, you never assume it.
- `seq` — a per-`delivery_run_id` monotonically increasing integer,
  **assigned by your JournalPort implementation on append, never supplied
  by the caller.** It is the deterministic ordering key `CONF-JOURNAL-001`
  and `CONF-JOURNAL-003` require. If two records could tie on wall-clock
  time, `seq` is still exact; do not use a timestamp as the ordering key.
- `kind`/`id` — resolve against `PROTOCOL-FACTS` (`FACT-*`),
  `PROTOCOL-DECISIONS` (`DEC-*`), or `PROTOCOL-EFFECTS` (`FX-*`) — a closed
  vocabulary; an implementation MUST NOT invent a new canonical `id` outside
  these three registries without a contract amendment.
- `data` — kind-specific required fields: `PROTOCOL-FACTS`'s "Required
  data" column for facts, `PROTOCOL-DECISIONS` (plus `basis`, per
  `INV-012`) for decisions, and `PORT-JOURNAL`'s effect-record shape
  (identity, idempotency key, `dispatch_result`) for effects. `data.
  dispatch_result` is reserved: an effect payload must not define its own
  field of that name (`PORT-JOURNAL-003`).
- `extensions` — present only when carrying an extension payload; any
  namespaced, versioned key satisfying `CONTRACT-EXTENSIONS` is legal
  (`EXT-001` requires only that the identifier itself be stable and
  versioned, not that it appear in this repository's own extension
  registry) — see §4 below for the shape and the two extensions already
  registered in this repository that you can reuse as templates:
  `EXT-EXECUTOR-IDENTITY-V1`, `EXT-REVIEW-FINDINGS-V1`.

Portability constraint, carried from `ADR-0003`: canonical persisted/
interchange records must not depend on pickle, language-native class
names, exception objects, or any non-JSON-portable value. Every envelope
above must be representable as plain JSON in any language — that is the
entire point of building an independent implementation against this
contract rather than against the Python types.

## 4. Extensions — carrying your own payloads

`CONTRACT-EXTENSIONS` is the generic transport; read it in full (seven
short rules, `EXT-001` through `EXT-007`). The two rules worth restating as
a checklist because they are the ones an implementer forgets:

- An extension key is namespaced and versioned (`review-findings/v1`, not
  `findings`) — `EXT-001`.
- Your core loop must never branch on an extension payload's internals —
  `EXT-002`. If your dispatch logic needs to look inside an extension to
  decide what state to transition to, that information belongs in a
  canonical Fact/Decision field instead, not an extension.
- A component that promises lossless round-trip (your own `history`
  implementation, for instance) must preserve an *unknown* extension key
  byte-for-byte, even though it does not understand it — `EXT-005`. This is
  how two independently-tailored implementations can share one journal file
  and safely ignore each other's private payloads.

Two extensions are already registered and worth reading as a template for
your own: `EXT-EXECUTOR-IDENTITY-V1` (seat/model/session provenance riding
an execution or assurance entry's `extensions` slot) and
`EXT-REVIEW-FINDINGS-V1` (structured verifier findings). Full schema/
semantics/examples live under `docs/extensions/<name>/`.

## 5. Replay, reconciliation, and idempotency ordering

Two separate correctness properties, easy to conflate:

**Replay determinism (`PORT-JOURNAL-005`, `CONF-JOURNAL-003`).** Given the
same ordered history, `load_projection` must reconstruct the same canonical
state every time — same states, same attempt counts, same candidate
fingerprints. Two required subtleties an implementer commonly misses:

- Replay must fold under the run's own durably recorded budgets, not your
  process's own default. `FX-CREATE-WORK`'s effect record carries
  `data.max_attempts` and `data.max_assurance_attempts`; `load_projection`
  reads those back and uses them, never a hardcoded constant. A journal
  written before `max_assurance_attempts` existed folds under `1` (not that
  field's schema default of `2`) — the two legacy fallbacks are different
  values and are not interchangeable (`CONF-JOURNAL-003`).
- This "read the run's own recorded budget, not your own default" rule
  applies to every verb that replays a journal with an existing
  `FX-CREATE-WORK` record, read-side and write-side, in any process — not
  only whatever you call your own load-projection function.

**Idempotency (`INV-020`).** Effects carry a stable idempotency key derived
deterministically from durable canonical state — never from randomness,
wall-clock time, or process/runtime identity — so that replaying the same
history twice reproduces identical keys, and a crash-then-retry converges
to the same outcome instead of duplicating the underlying operation. The
standard key tuple is `(delivery_run_id, work_id, attempt_number,
effect_id)`, with these named exceptions (`INV-020`'s full breakdown):

| Effect | Key form | Why it differs |
|---|---|---|
| `FX-CREATE-WORK` | `(delivery_run_id, effect_id)` | Exactly one plan creation per run in v0; no work/attempt scope yet exists. |
| `FX-CLAIM-WORK` | `(delivery_run_id, work_id, effect_id)` | Once per Work lineage — held across every retry attempt, never re-acquired. |
| `FX-START-EXECUTION`, `FX-SEND-EXECUTION`, `FX-CANCEL-EXECUTION`, `FX-IDENTIFY-CANDIDATE`, `FX-COMPLETE-WORK`, `FX-BLOCK-WORK` | standard tuple | — |
| `FX-START-ASSURANCE` | standard tuple + `candidate_fingerprint`, plus `assurance_number` when `> 1` | The first assurance of a candidate keeps the pre-`ADR-0006` key form so old journals replay unchanged; only the second-and-later re-request within the same execution attempt adds the new component. |

Your idempotency check must be determinable from durable state (your
provider's own durable records, or the journal itself) — never from
process-local memory alone. An in-process cache is a permitted fast path
over that durable check, never a substitute for it.

## 6. Candidate binding

`PORT-CANDIDATE`'s shape (`id`, `work_id`, `execution_id`,
`subject_identity`, `fingerprint`) and its three operations are the whole
port; read it, it is short. The rules worth internalizing before you write
a `compare()`:

- Identity must be exact (`INV-006`) — your fingerprint function must
  support deterministic equality, not "looks the same."
- Evidence is bound to the exact fingerprint it evaluated (`INV-007`) and
  never transfers to a different one, even a superficially similar one
  (`INV-008`).
- `current()` must return an explicit empty/none result rather than a
  stale or guessed candidate when it cannot determine one safely
  (`PORT-CAND-002`, `CONF-CAND-003`).

Two re-observation outcomes `STATE-DELIVERY` distinguishes, both worth
implementing deliberately rather than discovering by accident:

- **Verdict inheritance** (`STATE-DELIVERY` item 8) — a re-observed
  candidate id whose incoming fingerprint matches what's already on record,
  with a prior *settled* verdict already on record for that exact
  candidate, is not re-verified: no new `FACT-ASSURE-STARTED`/
  `FACT-ASSURE-SETTLED` pair is journaled at all for this re-observation —
  the existing verdict is cited as the `basis` of an ordinary
  `DEC-ACCEPT`/`DEC-RETRY`/`DEC-BLOCK` instead. This is distinct from an
  `inconclusive` re-request (item 11/`INV-021`, §7 below): that case has no
  settled verdict yet to inherit, so it *does* journal additional
  `FACT-ASSURE-STARTED`/`FACT-ASSURE-SETTLED` pairs against the same exact
  `candidate_id`/fingerprint, one per `assurance_number`, until one settles
  decisively or the assurance budget is exhausted.
- **Candidate-observation conflict** (`STATE-DELIVERY` item 9) — a
  re-observed candidate id whose fingerprint does *not* match (or which has
  no prior settled verdict to inherit from) is still journaled — Facts are
  immutable observations, never discarded — but the Work rests at
  `EXECUTING` with the conflict unresolved rather than being silently
  folded one way or the other. Resolving it is an operator-attributed
  `DEC-ABANDON-ATTEMPT`, never a mechanical fold.

## 7. Bounded retry and assurance budgets

Two independent, non-fungible budgets:

- **Retry budget** (`max_attempts`, default `3`, `INV-018`/`INV-019`) —
  bounds execution attempts per Work lineage. `attempt_number` is the
  cumulative count of execution-start records for that Work, first attempt
  `1`, deterministically reconstructable from history.
- **Assurance budget** (`max_assurance_attempts`, default `2`, `INV-021`,
  `ADR-0006`) — bounds how many times one candidate may be assured within
  one execution attempt before an `inconclusive` verdict blocks the Work.
  `assurance_number` is the per-execution-attempt assurance index, first
  assurance `1`, reconstructable as the count of `FACT-ASSURE-STARTED`
  records for the current execution.

The rule that trips up a first implementation: **an assurance re-request
never consumes the retry budget.** It journals no new `FACT-EXEC-STARTED`
and does not increment `attempt_number` — only a fresh execution attempt
does that. Both budgets are journaled once, at run creation, on
`FX-CREATE-WORK`'s effect record (`data.max_attempts`,
`data.max_assurance_attempts`); a run resumed with a differing explicit
value is refused (`ERR-VALIDATION`), never silently changed mid-run.

Budget exhaustion always resolves to `DEC-BLOCK` → terminal `BLOCKED`
(`STATE-DELIVERY`'s single v0 budget-exhaustion terminal — it never
branches to any other outcome), with `blocked_reason` distinguishing which
budget ran out: `retry-budget-exhausted`, `assurance-inconclusive`, or
`attempt-abandoned` (an abandoned attempt that itself exhausted the retry
budget).

## 8. Pending vs. terminal state

A started Execution or Assurance whose outcome has not yet been observed
is not a failure and not any other outcome — it is `EXECUTING`/`ASSURING`
resting, for as long as it takes, with no Fact journaled for the wait
(`STATE-DELIVERY`'s mechanical-sequencing item 7). This is the most
important thing to get right if you are building any kind of polling or
CLI loop on top of your implementation: **absence of an observation is not
itself an observation.** Do not invent a timeout-triggered synthetic
`failed`/`rejected` Fact — if you want a deadline, implement it as an
operator-driven `DEC-ABANDON-ATTEMPT` (item 9) or `DEC-CANCEL` (item 10),
both of which are explicit, attributed, and journaled as exactly what they
are, never as a fabricated settlement.

Terminal states reachable in v0 are `ACCEPTED`, `BLOCKED`, `CANCELLED`
(`STATE-DELIVERY`'s canonical v0 states section). `FAILED` and
`DEC-ESCALATE` are reserved — declared in `PROTOCOL-DECISIONS` but with no
transition row; do not make them reachable in your implementation without
first landing the contract amendment that would give them one.

## 9. Error handling

`CONTRACT-ERRORS` is the complete closed taxonomy your adapters translate
provider-native failures into — nine values, no more. Your core policy code
must never branch on a provider-native exit code, HTTP status, or
protocol-specific error; it branches only on this taxonomy. Two errors
worth flagging because they are easy to conflate: `ERR-TEMPORARY`
describes a provider-facing operation that may succeed on a policy-governed
retry; `ERR-BUSY` describes a purely local, mechanically bounded condition
(your own storage layer's lock could not be acquired within a fixed
timeout) with no provider and no retry-budget policy involved — never fall
back to an unlocked write because acquiring a lock produced this error
(`CONTRACT-STORAGE-CONCURRENCY` §11).

## 10. Interoperability boundaries

What makes an implementation interoperable with this repository's own
journals and with other independent implementations: the envelope (§3),
the closed Fact/Decision/Effect vocabulary (`PROTOCOL-FACTS`/
`PROTOCOL-DECISIONS`/`PROTOCOL-EFFECTS`), the state machine
(`STATE-DELIVERY`), and portable JSON — nothing else. A journal file
written by this repository's reference implementation is readable by
`jq`, by a from-scratch Go reader, or by hand, with zero dependency on
`orc_werk` being importable anywhere. Provider-specific vocabulary — a
tracker's issue-type names, an agent runtime's session-shape, a CI
system's job IDs — never appears in the canonical core (`INV-014`); it
stays inside your own adapter documentation, structured the way
`docs/adapters/README.md`'s mapping-document template describes if you
want a durable record of your own mapping choices.

## 11. Reference-specific vs. universal

Everything in this section is convenience the reference Python CLI chose;
none of it is a conformance requirement. An independent implementation may
use entirely different flags, config shape, on-disk layout, and output
schemas and still be fully conforming, provided it satisfies §3 through
§10 above.

| Reference-CLI-specific (yours may differ entirely) | Universal (every conforming implementation reproduces this) |
|---|---|
| `orc dispatch`/`record`/`status`/`history`/`verdict`/`report` flag names and argument shapes | The five port operation sets (§2) |
| The `config.json` dispatch-config schema (`execution`/`candidate`/`assurance`/`mirror`/`briefs`/`plan`/`attempts` keys) — explicitly CLI-owned composition, not a canonical protocol shape (`docs/cli/README.md`'s "Config schema" section) | The canonical record envelope (§3) and closed Fact/Decision/Effect vocabulary |
| The per-run directory layout (`<journal-dir>/<run_id>/journal.jsonl`, `config.json`, `times.jsonl`, `report.html`) | `PORT-JOURNAL`'s durable-journal recovery rule (torn-tail tolerance on the final record only; any earlier malformed record fails closed) |
| `orc-status/v1`/`orc-index/v1`/`orc-census/v1` JSON output shapes | `STATE-DELIVERY`'s states and transition table |
| `--wait`/`--poll-interval`/exit codes `0`/`1`/`2`/`3`/`4` as this CLI's specific resting-point signaling | The pending-is-not-a-failure semantics those exit codes are signaling (§8) |
| `$ORC_JOURNAL_DIR` env var and `--journal`/`ORC_JOURNAL_DIR`/`./.orc` precedence | `INV-020`'s idempotency key derivation rule (§5) |
| `orc onboard`'s skill/agents-block scaffold, `.omp/` seat files | The invariant registry (`CONTRACT-INVARIANTS`) and the port contracts themselves |

When in doubt whether a convention you are reading in `docs/cli/README.md`
or `docs/playbooks/cli-usage.md` is binding on you: those two documents are
explicitly informative/reference (`authority: informative` in their own
frontmatter), and `docs/cli/README.md` says so of itself directly — "the
CLI is a reference surface, not a contract." If a rule only appears there
and nowhere in `docs/contracts/`, `docs/domain/`, or `docs/protocol/`, it
is reference-specific.

## 12. Complete worked portable record examples

Both examples below are literal, minimal, valid JSONL you can replay by
hand against the rules in §3 through §8 — not excerpts, not pseudocode.
Field values (ids, hashes) are illustrative; your implementation generates
its own.

### 12.1 Single attempt, straight to acceptance

One Work, one execution, one assurance, accepted on the first try — the
shortest legal complete run. Seventeen records, `seq` 1 through 17:

```jsonl
{"schema_version":1,"seq":1,"delivery_run_id":"run-1","kind":"fact","id":"FACT-INTENT-SUBMITTED","data":{"intent_id":"run-1","text":"ship the widget"},"extensions":{}}
{"schema_version":1,"seq":2,"delivery_run_id":"run-1","kind":"effect","id":"FX-CREATE-WORK","data":{"idempotency_key":"run-1|FX-CREATE-WORK","plan":{"works":[{"work_id":"work-1","deps":[]}]},"max_attempts":3,"max_assurance_attempts":2,"dispatch_result":{"works":[{"work_id":"work-1"}]}},"extensions":{}}
{"schema_version":1,"seq":3,"delivery_run_id":"run-1","kind":"fact","id":"FACT-WORK-CREATED","data":{"work_id":"work-1","delivery_run_id":"run-1"},"extensions":{}}
{"schema_version":1,"seq":4,"delivery_run_id":"run-1","kind":"fact","id":"FACT-WORK-READY","data":{"work_id":"work-1"},"extensions":{}}
{"schema_version":1,"seq":5,"delivery_run_id":"run-1","kind":"decision","id":"DEC-DISPATCH","data":{"work_id":"work-1","attempt_number":1,"attribution":{"policy":"v0-deterministic"},"basis":[{"id":"FACT-WORK-READY","kind":"fact","data":{"work_id":"work-1"}}]},"extensions":{}}
{"schema_version":1,"seq":6,"delivery_run_id":"run-1","kind":"effect","id":"FX-START-EXECUTION","data":{"work_id":"work-1","attempt_number":1,"idempotency_key":"run-1|work-1|1|FX-START-EXECUTION","dispatch_result":{"execution_id":"exec-1"}},"extensions":{}}
{"schema_version":1,"seq":7,"delivery_run_id":"run-1","kind":"fact","id":"FACT-EXEC-STARTED","data":{"work_id":"work-1","execution_id":"exec-1"},"extensions":{}}
{"schema_version":1,"seq":8,"delivery_run_id":"run-1","kind":"fact","id":"FACT-EXEC-SETTLED","data":{"work_id":"work-1","execution_id":"exec-1","outcome":"completed","artifact_refs":["gh-pr:1","head:abc1111"]},"extensions":{"executor-identity/v1":{"role":"ship","model":"example/model-a","session_ref":"sess-ship-1","seat_ref":"ship-work-1-abc1111"}}}
{"schema_version":1,"seq":9,"delivery_run_id":"run-1","kind":"effect","id":"FX-IDENTIFY-CANDIDATE","data":{"work_id":"work-1","execution_id":"exec-1","idempotency_key":"run-1|work-1|1|FX-IDENTIFY-CANDIDATE","dispatch_result":{"candidate":{"id":"cand-1","work_id":"work-1","execution_id":"exec-1","fingerprint":"fp-abc1111","subject_identity":{"head_sha":"abc1111"}}}},"extensions":{}}
{"schema_version":1,"seq":10,"delivery_run_id":"run-1","kind":"fact","id":"FACT-CANDIDATE-OBSERVED","data":{"work_id":"work-1","execution_id":"exec-1","candidate_id":"cand-1","fingerprint":"fp-abc1111"},"extensions":{}}
{"schema_version":1,"seq":11,"delivery_run_id":"run-1","kind":"decision","id":"DEC-REQUEST-ASSURANCE","data":{"work_id":"work-1","candidate_id":"cand-1","max_assurance_attempts":2,"assurance_number":1,"attribution":{"policy":"v0-deterministic"},"basis":[{"id":"FACT-CANDIDATE-OBSERVED","kind":"fact","data":{"work_id":"work-1","candidate_id":"cand-1"}}]},"extensions":{}}
{"schema_version":1,"seq":12,"delivery_run_id":"run-1","kind":"effect","id":"FX-START-ASSURANCE","data":{"work_id":"work-1","candidate_id":"cand-1","candidate_fingerprint":"fp-abc1111","assurance_number":1,"idempotency_key":"run-1|work-1|1|FX-START-ASSURANCE|fp-abc1111","dispatch_result":{"assurance_id":"assure-1"}},"extensions":{}}
{"schema_version":1,"seq":13,"delivery_run_id":"run-1","kind":"fact","id":"FACT-ASSURE-STARTED","data":{"work_id":"work-1","candidate_id":"cand-1","assurance_id":"assure-1"},"extensions":{}}
{"schema_version":1,"seq":14,"delivery_run_id":"run-1","kind":"fact","id":"FACT-ASSURE-SETTLED","data":{"work_id":"work-1","assurance_id":"assure-1","candidate_fingerprint":"fp-abc1111","verdict":"accepted","evidence_refs":["gh-pr:1","head:abc1111"]},"extensions":{"executor-identity/v1":{"role":"verify","model":"example/model-b","session_ref":"sess-verify-1","seat_ref":"verify-work-1-abc1111"}}}
{"schema_version":1,"seq":15,"delivery_run_id":"run-1","kind":"decision","id":"DEC-ACCEPT","data":{"work_id":"work-1","attribution":{"policy":"v0-deterministic"},"basis":[{"id":"FACT-ASSURE-SETTLED","kind":"fact","data":{"work_id":"work-1","verdict":"accepted"}}]},"extensions":{}}
{"schema_version":1,"seq":16,"delivery_run_id":"run-1","kind":"effect","id":"FX-COMPLETE-WORK","data":{"work_id":"work-1","idempotency_key":"run-1|work-1|1|FX-COMPLETE-WORK","dispatch_result":{"work_id":"work-1"}},"extensions":{}}
{"schema_version":1,"seq":17,"delivery_run_id":"run-1","kind":"fact","id":"FACT-WORK-COMPLETED","data":{"work_id":"work-1"},"extensions":{}}
```

### 12.1a An invalid record, for the checklist's malformed-key test

§13's checklist asks you to confirm your reader rejects, rather than
silently ignores, an unknown/malformed top-level key. This is what such a
violation looks like — a decision record carrying a stray
`"schema_version:1"` key that does not belong in the envelope (contrast
with the legitimate `seq:5` record in 12.1 above, which has exactly the
canonical six top-level keys):

```jsonl
{"schema_version:1":true,"schema_version":1,"seq":5,"delivery_run_id":"run-1","kind":"decision","id":"DEC-DISPATCH","data":{"work_id":"work-1","attempt_number":1,"attribution":{"policy":"v0-deterministic"},"basis":[{"id":"FACT-WORK-READY","kind":"fact","data":{"work_id":"work-1"}}]},"extensions":{}}
```

A strict reader MUST reject this line rather than tolerate the extra key —
it is not part of `PORT-JOURNAL-ENVELOPE`'s canonical shape. This is a
standalone negative example; it is never part of a legal, complete run.

### 12.2 Rejected, then retried, then accepted

The same Work, but the first assurance rejects, forcing a second execution
attempt within the *same* run. A retry always creates a new Execution
identity (`INV-004` — historical Executions are never overwritten), so
`attempt_number` increments to `2` and a new `execution_id` is produced;
the candidate identification that follows the new execution typically
yields a new `candidate_id`/`fingerprint` too (a different artifact was
produced), though that is a consequence of the artifact actually differing,
not a rule this contract enforces on candidate identity itself — see §6's
verdict-inheritance case for when a re-observed candidate legitimately
keeps its prior identity instead. `DEC-RETRY` cites the rejecting
`FACT-ASSURE-SETTLED` as its `basis` (`INV-012`). Twenty-seven records,
`seq` 1 through 27, complete:

```jsonl
{"schema_version":1,"seq":1,"delivery_run_id":"run-2","kind":"fact","id":"FACT-INTENT-SUBMITTED","data":{"intent_id":"run-2","text":"ship the widget, v2"},"extensions":{}}
{"schema_version":1,"seq":2,"delivery_run_id":"run-2","kind":"effect","id":"FX-CREATE-WORK","data":{"idempotency_key":"run-2|FX-CREATE-WORK","plan":{"works":[{"work_id":"work-1","deps":[]}]},"max_attempts":3,"max_assurance_attempts":2,"dispatch_result":{"works":[{"work_id":"work-1"}]}},"extensions":{}}
{"schema_version":1,"seq":3,"delivery_run_id":"run-2","kind":"fact","id":"FACT-WORK-CREATED","data":{"work_id":"work-1","delivery_run_id":"run-2"},"extensions":{}}
{"schema_version":1,"seq":4,"delivery_run_id":"run-2","kind":"fact","id":"FACT-WORK-READY","data":{"work_id":"work-1"},"extensions":{}}
{"schema_version":1,"seq":5,"delivery_run_id":"run-2","kind":"decision","id":"DEC-DISPATCH","data":{"work_id":"work-1","attempt_number":1,"attribution":{"policy":"v0-deterministic"},"basis":[{"id":"FACT-WORK-READY","kind":"fact","data":{"work_id":"work-1"}}]},"extensions":{}}
{"schema_version":1,"seq":6,"delivery_run_id":"run-2","kind":"effect","id":"FX-START-EXECUTION","data":{"work_id":"work-1","attempt_number":1,"idempotency_key":"run-2|work-1|1|FX-START-EXECUTION","dispatch_result":{"execution_id":"exec-1"}},"extensions":{}}
{"schema_version":1,"seq":7,"delivery_run_id":"run-2","kind":"fact","id":"FACT-EXEC-STARTED","data":{"work_id":"work-1","execution_id":"exec-1"},"extensions":{}}
{"schema_version":1,"seq":8,"delivery_run_id":"run-2","kind":"fact","id":"FACT-EXEC-SETTLED","data":{"work_id":"work-1","execution_id":"exec-1","outcome":"completed","artifact_refs":["gh-pr:2","head:abc1111"]},"extensions":{"executor-identity/v1":{"role":"ship","model":"example/model-a","session_ref":"sess-ship-2","seat_ref":"ship-work-1-abc1111"}}}
{"schema_version":1,"seq":9,"delivery_run_id":"run-2","kind":"effect","id":"FX-IDENTIFY-CANDIDATE","data":{"work_id":"work-1","execution_id":"exec-1","idempotency_key":"run-2|work-1|1|FX-IDENTIFY-CANDIDATE","dispatch_result":{"candidate":{"id":"cand-1","work_id":"work-1","execution_id":"exec-1","fingerprint":"fp-abc1111","subject_identity":{"head_sha":"abc1111"}}}},"extensions":{}}
{"schema_version":1,"seq":10,"delivery_run_id":"run-2","kind":"fact","id":"FACT-CANDIDATE-OBSERVED","data":{"work_id":"work-1","execution_id":"exec-1","candidate_id":"cand-1","fingerprint":"fp-abc1111"},"extensions":{}}
{"schema_version":1,"seq":11,"delivery_run_id":"run-2","kind":"decision","id":"DEC-REQUEST-ASSURANCE","data":{"work_id":"work-1","candidate_id":"cand-1","max_assurance_attempts":2,"assurance_number":1,"attribution":{"policy":"v0-deterministic"},"basis":[{"id":"FACT-CANDIDATE-OBSERVED","kind":"fact","data":{"work_id":"work-1","candidate_id":"cand-1"}}]},"extensions":{}}
{"schema_version":1,"seq":12,"delivery_run_id":"run-2","kind":"effect","id":"FX-START-ASSURANCE","data":{"work_id":"work-1","candidate_id":"cand-1","candidate_fingerprint":"fp-abc1111","assurance_number":1,"idempotency_key":"run-2|work-1|1|FX-START-ASSURANCE|fp-abc1111","dispatch_result":{"assurance_id":"assure-1"}},"extensions":{}}
{"schema_version":1,"seq":13,"delivery_run_id":"run-2","kind":"fact","id":"FACT-ASSURE-STARTED","data":{"work_id":"work-1","candidate_id":"cand-1","assurance_id":"assure-1"},"extensions":{}}
{"schema_version":1,"seq":14,"delivery_run_id":"run-2","kind":"fact","id":"FACT-ASSURE-SETTLED","data":{"work_id":"work-1","assurance_id":"assure-1","candidate_fingerprint":"fp-abc1111","verdict":"rejected","evidence_refs":["gh-pr:2","head:abc1111"]},"extensions":{"review-findings/v1":{"findings":["REJECT: date range off by one day at week boundary"]}}}
{"schema_version":1,"seq":15,"delivery_run_id":"run-2","kind":"decision","id":"DEC-RETRY","data":{"work_id":"work-1","attempt_number":2,"attribution":{"policy":"v0-deterministic"},"basis":[{"id":"FACT-ASSURE-SETTLED","kind":"fact","data":{"work_id":"work-1","verdict":"rejected"}}]},"extensions":{}}
{"schema_version":1,"seq":16,"delivery_run_id":"run-2","kind":"effect","id":"FX-START-EXECUTION","data":{"work_id":"work-1","attempt_number":2,"idempotency_key":"run-2|work-1|2|FX-START-EXECUTION","dispatch_result":{"execution_id":"exec-2"}},"extensions":{}}
{"schema_version":1,"seq":17,"delivery_run_id":"run-2","kind":"fact","id":"FACT-EXEC-STARTED","data":{"work_id":"work-1","execution_id":"exec-2"},"extensions":{}}
{"schema_version":1,"seq":18,"delivery_run_id":"run-2","kind":"fact","id":"FACT-EXEC-SETTLED","data":{"work_id":"work-1","execution_id":"exec-2","outcome":"completed","artifact_refs":["gh-pr:2","head:def2222"]},"extensions":{"executor-identity/v1":{"role":"ship","model":"example/model-a","session_ref":"sess-ship-2","seat_ref":"ship-work-1-def2222"}}}
{"schema_version":1,"seq":19,"delivery_run_id":"run-2","kind":"effect","id":"FX-IDENTIFY-CANDIDATE","data":{"work_id":"work-1","execution_id":"exec-2","idempotency_key":"run-2|work-1|2|FX-IDENTIFY-CANDIDATE","dispatch_result":{"candidate":{"id":"cand-2","work_id":"work-1","execution_id":"exec-2","fingerprint":"fp-def2222","subject_identity":{"head_sha":"def2222"}}}},"extensions":{}}
{"schema_version":1,"seq":20,"delivery_run_id":"run-2","kind":"fact","id":"FACT-CANDIDATE-OBSERVED","data":{"work_id":"work-1","execution_id":"exec-2","candidate_id":"cand-2","fingerprint":"fp-def2222"},"extensions":{}}
{"schema_version":1,"seq":21,"delivery_run_id":"run-2","kind":"decision","id":"DEC-REQUEST-ASSURANCE","data":{"work_id":"work-1","candidate_id":"cand-2","max_assurance_attempts":2,"assurance_number":1,"attribution":{"policy":"v0-deterministic"},"basis":[{"id":"FACT-CANDIDATE-OBSERVED","kind":"fact","data":{"work_id":"work-1","candidate_id":"cand-2"}}]},"extensions":{}}
{"schema_version":1,"seq":22,"delivery_run_id":"run-2","kind":"effect","id":"FX-START-ASSURANCE","data":{"work_id":"work-1","candidate_id":"cand-2","candidate_fingerprint":"fp-def2222","assurance_number":1,"idempotency_key":"run-2|work-1|2|FX-START-ASSURANCE|fp-def2222","dispatch_result":{"assurance_id":"assure-2"}},"extensions":{}}
{"schema_version":1,"seq":23,"delivery_run_id":"run-2","kind":"fact","id":"FACT-ASSURE-STARTED","data":{"work_id":"work-1","candidate_id":"cand-2","assurance_id":"assure-2"},"extensions":{}}
{"schema_version":1,"seq":24,"delivery_run_id":"run-2","kind":"fact","id":"FACT-ASSURE-SETTLED","data":{"work_id":"work-1","assurance_id":"assure-2","candidate_fingerprint":"fp-def2222","verdict":"accepted","evidence_refs":["gh-pr:2","head:def2222"]},"extensions":{"executor-identity/v1":{"role":"verify","model":"example/model-b","session_ref":"sess-verify-2","seat_ref":"verify-work-1-def2222"}}}
{"schema_version":1,"seq":25,"delivery_run_id":"run-2","kind":"decision","id":"DEC-ACCEPT","data":{"work_id":"work-1","attribution":{"policy":"v0-deterministic"},"basis":[{"id":"FACT-ASSURE-SETTLED","kind":"fact","data":{"work_id":"work-1","verdict":"accepted"}}]},"extensions":{}}
{"schema_version":1,"seq":26,"delivery_run_id":"run-2","kind":"effect","id":"FX-COMPLETE-WORK","data":{"work_id":"work-1","idempotency_key":"run-2|work-1|2|FX-COMPLETE-WORK","dispatch_result":{"work_id":"work-1"}},"extensions":{}}
{"schema_version":1,"seq":27,"delivery_run_id":"run-2","kind":"fact","id":"FACT-WORK-COMPLETED","data":{"work_id":"work-1"},"extensions":{}}
```

### 12.3 An `inconclusive` re-request (fragment, not a complete run)

Unlike 12.1 and 12.2 above, this is deliberately only a fragment — it
exists to show the assurance-budget-only fork from §7 (never touching
`attempt_number`), the shape a second assurance of the *same* candidate
takes after an `inconclusive` settlement — note `assurance_number: 2` and
the extra `assurance_number` component on `FX-START-ASSURANCE`'s
idempotency key, with `attempt_number` untouched from whatever it already
was. As §6 notes, this second `FACT-ASSURE-SETTLED` under a new assurance
identity for the same `candidate_id` is exactly what item 8's verdict
inheritance does *not* produce — inheritance only applies once one of these
re-requests actually settles decisively:

```jsonl
{"schema_version":1,"seq":20,"delivery_run_id":"run-3","kind":"fact","id":"FACT-ASSURE-SETTLED","data":{"work_id":"work-1","assurance_id":"assure-1","candidate_fingerprint":"fp-abc1111","verdict":"inconclusive","evidence_refs":["sandbox-timeout"]},"extensions":{}}
{"schema_version":1,"seq":21,"delivery_run_id":"run-3","kind":"decision","id":"DEC-REQUEST-ASSURANCE","data":{"work_id":"work-1","candidate_id":"cand-1","max_assurance_attempts":2,"assurance_number":2,"attribution":{"policy":"v0-deterministic"},"basis":[{"id":"FACT-ASSURE-SETTLED","kind":"fact","data":{"work_id":"work-1","verdict":"inconclusive"}}]},"extensions":{}}
{"schema_version":1,"seq":22,"delivery_run_id":"run-3","kind":"effect","id":"FX-START-ASSURANCE","data":{"work_id":"work-1","candidate_id":"cand-1","candidate_fingerprint":"fp-abc1111","assurance_number":2,"idempotency_key":"run-3|work-1|1|FX-START-ASSURANCE|fp-abc1111|2","dispatch_result":{"assurance_id":"assure-2"}},"extensions":{}}
```

## 13. Observable verification checklist

Everything below is verifiable by inspecting a journal file directly (`cat`,
`jq`, or your own reader) and by exercising your implementation's own
CLI/API surface — never by reading Python source as a stand-in for the
check.

- [ ] **Envelope shape.** Every line is valid JSON with all six top-level
      keys (`schema_version`, `seq`, `delivery_run_id`, `kind`, `id`,
      `data`) present; `extensions` present or absent per §3.
- [ ] **Seq monotonicity.** `seq` values within one `delivery_run_id` are
      strictly increasing integers assigned by your JournalPort on append
      (`PORT-JOURNAL-ENVELOPE`), never repeated, regardless of how many
      processes appended concurrently. `PORT-JOURNAL` requires only
      monotonic increase, not a specific starting value or gaplessness —
      the reference implementation happens to start at `1` with no gaps,
      but that specific numbering is reference-specific (§11), not a
      universal conformance requirement.
- [ ] **Vocabulary closure.** Every `id` resolves against exactly one of
      `PROTOCOL-FACTS`, `PROTOCOL-DECISIONS`, or `PROTOCOL-EFFECTS`,
      matching its declared `kind`.
- [ ] **Replay agreement.** Two independent reads of the same unchanged
      journal (your own reader run twice, or your reader compared against a
      second implementation's reader) reconstruct byte-identical or
      structurally-identical projected state (§5).
- [ ] **Idempotent effect replay.** Deliberately re-run the same effect
      dispatch twice with the same idempotency key (simulate a crash-then-
      retry); confirm no duplicate underlying operation occurs and the
      journal gains no duplicate Fact for it (§5, `INV-020`).
- [ ] **Budget arithmetic matches what's recorded.** Count
      `FACT-EXEC-STARTED` records for a Work and confirm it never exceeds
      the `max_attempts` recorded on that run's `FX-CREATE-WORK`; count
      `FACT-ASSURE-STARTED` records for one execution attempt and confirm
      it never exceeds `max_assurance_attempts` (§7).
- [ ] **Exact candidate gating.** Construct two candidates with different
      subjects but confirm your fingerprint function assigns them different
      fingerprints (`CONF-CAND-002`), and the same subject observed twice
      yields the same fingerprint (`CONF-CAND-001`).
- [ ] **Verdict never upgrades.** Confirm no code path can turn a
      `rejected` or `inconclusive` `FACT-ASSURE-SETTLED` into an accepted
      Work without a fresh `accepted` verdict against the current candidate
      (`INV-009`).
- [ ] **Cancellation legality.** `FACT-WORK-CANCELLED` is reachable from
      `READY`/`EXECUTING`/`ASSURING` and rejected from every terminal state
      (`ACCEPTED`/`BLOCKED`/`CANCELLED` itself) — exercise both the legal
      and illegal case and confirm the illegal one is refused, not silently
      accepted.
- [ ] **Torn-tail tolerance, not corruption tolerance.** Truncate a
      journal file mid-record on its *final* line with at least one valid
      record before it; confirm your reader recovers the valid prefix. Then
      corrupt a record that is *not* the final one; confirm your reader
      fails closed (`ERR-VALIDATION`-equivalent) rather than silently
      skipping it (`PORT-JOURNAL`'s durable-journal recovery rule).
- [ ] **Lock-busy behavior, if you built local concurrent storage.**
      Deliberately hold your storage lock from one process and attempt a
      concurrent mutation from a second; confirm the second fails with a
      structured busy error within a bounded timeout rather than either
      hanging forever or writing unlocked (`CONTRACT-STORAGE-CONCURRENCY`
      §11).
- [ ] **No fabricated wait.** Leave an execution or assurance genuinely
      unsettled and confirm your implementation records nothing for the
      wait itself — no synthetic Fact, no timeout-triggered outcome — and
      the Work simply rests at its current non-terminal state (§8).

Passing every item above is evidence toward conformance; it is not itself a
conformance certificate. `CONFORMANCE-INDEX` names the full `CONF-*`
requirement set your implementation is ultimately measured against, and a
small worked example — including everything in §12 — demonstrates the
shape of correct behavior without exercising every edge those requirements
cover (concurrent multi-process races, every capability-gated port
operation, every error-taxonomy translation). Treat this checklist as your
own pre-flight, and `CONFORMANCE-INDEX`'s full suite as the actual bar.

## Related

- `PRODUCT-ADOPTION`
- `PLAYBOOK-PRACTICE-ADOPTION`
- `ORCHESTRATION-CONTRACT`
- `CONTRACT-INVARIANTS`
- `STATE-DELIVERY`
- `PROTOCOL-FACTS`
- `PROTOCOL-DECISIONS`
- `PROTOCOL-EFFECTS`
- `PORTS-INDEX`
- `PORT-JOURNAL`
- `CONTRACT-EXTENSIONS`
- `CONTRACT-ERRORS`
- `CONTRACT-STORAGE-CONCURRENCY`
- `CONTRACT-DURABILITY`
- `CONFORMANCE-INDEX`
- `ADR-0003`
- `ADR-0005`
- `ADR-0006`
- `docs/conformance/README.md`
