---
id: TASK-FIX-281-293
type: task-card
status: current
authority: normative
description: Resolve issue #281 (executor-identity/v1.model self-reporting and qualification drift) and issue #293 (orc cancel reaches a terminal state with no execution outcome and no caller-role authorization) per operator ruling. Docs-only; no new validation, no new CLI flag, no hook.
implements:
  - EXT-EXECUTOR-IDENTITY-V1
  - ADR-0007
verifies: []
---

# TASK-FIX-281-293 — executor-identity producer convention and cancellation/record-before-yield boundary

Design source: `EXT-EXECUTOR-IDENTITY-V1-SCHEMA`; `EXT-EXECUTOR-IDENTITY-V1-SEMANTICS`;
`ADR-0007`; `STATE-DELIVERY` items 8–10; issue #281; issue #293.

## The gap

Two open, read-only-recon'd issues, each already carrying an operator
ruling this card implements verbatim — no new design choice is made here:

- **#281** — `executor-identity/v1.model` is recorded inconsistently
  across runs driven by the same `.omp/agents/ship.md` definition (some
  settlements qualify the provider, e.g. `anthropic/claude-sonnet-5`;
  others record the bare `claude-sonnet-5`). The schema and semantics
  docs never stated a producer convention for qualification, so the seat
  instructions and packaged scaffold that type the `--model` flag never
  had one to follow either.
- **#293** — `orc cancel` reaches terminal `CANCELLED` from any
  non-terminal state (`STATE-DELIVERY` item 10, intended and retained)
  with no execution outcome and no caller-role authorization
  (`src/orc_werk/cli/main.py:1157-1196`). `ADR-0007`'s own record-
  before-yield claim (§"Record-before-yield") left three questions open
  at issue #293's filing rather than resolving them.

## Operator ruling implemented (verbatim scope, no new decision)

**#281:**
1. Producer convention: a producer records `model` fully qualified
   (`<provider>/<model-name>`) when the provider is *genuinely known* to
   it; a producer MUST NOT guess or infer a provider it did not observe.
2. `executor-identity/v1` stays observational self-report: no new field,
   no normalization, no required-format validation. Absent, unqualified,
   and historical values remain fully valid and are never rewritten.
3. Self-reported `model` cannot prove runtime model family or detect a
   mid-run model switch; that would need harness-observed identity, a
   separate, future, versioned design — out of scope here.
4. OMP's ability to read a running agent's role inside a hook
   (`docs/adapters/omp/mapping.md`'s `role` row) is harness-level
   visibility, not `orc`-authenticated caller identity; the two must not
   be conflated.
5. Seat/record instructions and the packaged OMP scaffold are updated
   only where they embed the old, unqualified convention (the `--model
   <your model id>` command-line placeholder text) — nothing else about
   those files changes.

**#293:**
1. Cancel-from-any-non-terminal-state stays exactly as `STATE-DELIVERY`
   item 10 already specifies. No transition-table change.
2. Record-before-yield is stated precisely, not left implicit: it is
   structurally enforced only for the two paths gated by bound assurance
   (`ACCEPTED`, fresh or inherited; the assurance-triggered branch of
   `BLOCKED`). It is **not** claimed for `BLOCKED` reached by plain
   retry-budget exhaustion after repeated failed executions (no
   assurance ever requested) or for `CANCELLED` (deliberately
   assurance-free by design).
3. An inherited `ACCEPTED` (item 8) still rests on real, previously
   recorded assurance evidence; inheritance reuses a verdict, it does
   not fabricate one.
4. No caller-role authorization gate and no provenance-only `--by` flag
   are added to `orc cancel`: every seat in this repository shares one
   OS identity and one GitHub credential, so a CLI-side role check would
   be self-asserted and trivially bypassed.
5. The standing posture for every gap above is after-the-fact ledger/PR
   audit, which **detects** an escape once it has happened and **never
   prevents** one from happening.
6. Core contract/domain docs (`docs/contracts/`, `docs/domain/`) stay
   generic; the harness-specific "record-before-yield" vocabulary and
   its resolution live where they already lived, in `ADR-0007`.
7. `docs/decisions/ADR-0007-omp-primary-harness.md`'s own prior amendment
   text (2026-09-07) explicitly left these three questions open; this
   card resolves them there, in place, rather than inventing a new
   document.

## Outcome

- `docs/extensions/executor-identity/v1/schema.md` gains a "Producer
  convention for `model`" section (the qualify-when-genuinely-known
  rule, no guessing, no normalization/validation, historical values
  untouched) and a one-sentence disclosure that the "no other fields"
  rule is unenforced on the hand-edited backing-config path (an existing
  gap, not fixed here).
- `docs/extensions/executor-identity/v1/semantics.md` gains a "Known
  limitation" section: self-reported `model` cannot establish runtime
  family or a mid-run switch; harness-observed identity needs a separate
  versioned design.
- `docs/adapters/omp/mapping.md`'s `role` field-mapping paragraph gains
  one clarifying sentence: harness-level role visibility is not
  `orc`-authenticated caller identity (cross-referencing issue #293).
- `docs/decisions/ADR-0007-omp-primary-harness.md`'s "Record-before-
  yield" section replaces its "issue #293 leaves open" paragraph with
  the resolved ruling above, grounded in `reducer.py`.
- `.omp/agents/ship.md` and `.omp/agents/verify.md`'s `orc record`
  command lines replace `--model <your model id>` with qualify-when-
  known guidance; `src/orc_werk/omp_scaffold/agents/{ship,verify}.md`
  get the identical change (not a new adopter-facing substitution — the
  line is currently byte-identical between live and packaged copies).
- This card and its index registration.

## In scope

- `docs/extensions/executor-identity/v1/schema.md`
- `docs/extensions/executor-identity/v1/semantics.md`
- `docs/adapters/omp/mapping.md` — the `role` row's trailing paragraph only.
- `docs/decisions/ADR-0007-omp-primary-harness.md` — the "Record-before-yield" section's closing paragraph only.
- `.omp/agents/ship.md`, `.omp/agents/verify.md` — the `orc record` command-line's `--model` placeholder only.
- `src/orc_werk/omp_scaffold/agents/ship.md`, `src/orc_werk/omp_scaffold/agents/verify.md` — the identical mirrored change.
- This card and its index registration.

## Out of scope

- Any new `CONF-*` requirement, golden scenario, or CLI flag: no new
  testable behavior is introduced by either ruling, so none is added.
- Normalizing, validating, or backfilling any recorded `model` string
  (v1 stays observational self-report; issue #281 rules this out
  explicitly).
- Detecting or recording a mid-run model-family switch, and any
  harness-observed (non-self-reported) identity design — a future,
  separately versioned extension, not this card.
- Any `orc cancel` code change: no `--by` flag, no caller-role gate, no
  reducer change. `STATE-DELIVERY` item 10 is unchanged.
- The unregistered `note` field found on
  `.orc/recover-consolidation-docs-truth`'s hand-authored payload
  (issue #281's comment): disclosed as an existing validation gap in
  the hand-edit path, not fixed here, and no historical journal entry is
  rewritten to conform to any convention in this card.
- `docs/adapters/omp/README.md`, `docs/adapters/omp/capabilities.md`,
  `docs/adapters/omp/conformance.md`, `docs/delivery/watchtower-
  operations.md` — issue #282/#287 capability-doc reconciliation,
  owned by a separate card/PR.
- `docs/playbooks/agent-cli-usage.md` §3/§4 (ship/verify protocol
  steps), candidate re-observation warnings, and recovery docs — issue
  #289/#295, owned by a separate card/PR.

## Acceptance

- `docs_check.py` passes.
- `docs/extensions/executor-identity/v1/schema.md` and `semantics.md`
  state the producer convention and its limitation without adding a new
  field, a required-format rule, or a `CONF-EXT-*` id.
- `docs/decisions/ADR-0007-omp-primary-harness.md` no longer says issue
  #293 "leaves open" the three questions it names; it states the
  resolved ruling, still grounded in `reducer.py` line citations that
  match this repository's own head.
- `.omp/agents/ship.md`'s and `.omp/agents/verify.md`'s `orc record`
  command lines no longer read `--model <your model id>` unqualified;
  `src/orc_werk/omp_scaffold/agents/{ship,verify}.md` match them
  byte-for-byte on that line (`PackagedScaffoldDriftTest` stays green
  with no new `_ADOPTER_SUBSTITUTIONS` entry required).
- `orc cancel --help` and `orc record --help`, run against this
  worktree's own installed CLI, are unchanged and confirm no `--by`
  flag and no role-authorization option exist (grounding, not a new
  requirement).
- `bash scripts/check.sh` is green.

## Ambiguities encountered

None. Both issues carry an explicit, dated operator ruling this card
implements verbatim; no contract-level question was left for this card
to decide.
