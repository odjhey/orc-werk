---
id: TASK-FIX-288
type: task-card
status: current
authority: normative
description: Fix issue #288 — operator --abandon-work landing a Work at BLOCKED left blocked_reason=None, indistinguishable from an ordinary in-flight resting point across text and JSON consumers. Derives the existing attempt-abandoned reason eagerly; no new field, no retry/cancellation change.
implements:
  - STATE-DELIVERY item 9
verifies:
  - SCN-010
---

# TASK-FIX-288 — abandon-to-BLOCKED `blocked_reason` derived eagerly

Design source: `STATE-DELIVERY` item 9; `SCN-010`; `INV-018`; `INV-019`; issue #288.

## The gap

`STATE-DELIVERY` item 9's transition table row for `FACT-ATTEMPT-ABANDONED`
resolving to `BLOCKED` (retry budget exhausted) followed the same shape
every other `BLOCKED`-bound row uses: `blocked_reason` stayed `None` until
a *later* dispatch's confirming `FACT-WORK-BLOCKED` set it. Every other
`BLOCKED`-bound row's next dispatch is always the ordinary continuation of
the same `orc dispatch` process (no adapter-selection concern), so the gap
between "entered `BLOCKED`" and "confirmed" is invisible in practice.
Item 9's abandon branch is different: `--abandon-work` deliberately stops
short of calling `orchestrator.run()` in the same invocation (issue #165 —
`--abandon-work` forces `scripted` adapters, and running the next dispatch
phase immediately would risk minting a real port Effect through a
stub-shaped provider). The confirming `FACT-WORK-BLOCKED` is therefore left
to a genuinely separate, later, real-config dispatch — which an operator
may not run again for some time. Meanwhile `orc status`/`orc history` and
the `next:` guidance showed `blocked_reason=None`, indistinguishable from
a Work still resting mid-flight, even though the operator's full
free-form `--abandon-reason` was already durable on `FACT-ATTEMPT-ABANDONED`
in the journal the whole time.

## Fix (no new field, no retry/cancellation change)

`core/reducer.py`'s `FACT-ATTEMPT-ABANDONED` fold now derives
`blocked_reason` *eagerly*, the instant the Work lands at `BLOCKED` —
the identical "state entered eagerly, confirmation is a separate later
idempotency marker" convention (the module docstring's own
"State-derivation convention" note) every other row already uses for its
terminal *state*; only `blocked_reason` on this one row was, until now,
withheld until confirmation. The literal it derives —
`"attempt-abandoned"` — is not new: `core/policy.py`'s `_block_reason`
already special-cased this exact trigger Fact into this exact string for
the *later* `FACT-WORK-BLOCKED`'s own `reason` field; the reducer now
computes the same literal a step earlier, from the same trigger Fact, so
the eventual confirmation re-asserts the identical value rather than
overwriting it with something else. `blocked_confirmed` is untouched
(stays `False`) and no port Effect is dispatched by `abandon_attempt()` —
it remains a purely journal-only recording surface, exactly as documented;
the confirming `DEC-BLOCK`/`FX-BLOCK-WORK`/`FACT-WORK-BLOCKED` still folds
the ordinary way, whenever a later `run()` pass next advances policy for
this Work.

An earlier implementation attempt instead had `abandon_attempt()` itself
call `_apply_decision` to fold the confirming `DEC-BLOCK` immediately, in
the same operator step. A verify-seat review rejected this: `FX-BLOCK-WORK`
calls `self.work_graph.block(...)`, a real `WorkGraphPort` side effect, so
that shape violated `abandon_attempt`'s own "journal-only, never a port
Effect" contract even though `FX-BLOCK-WORK` happens to target only the
in-process bookkeeping port. The eager-derivation fix above achieves the
same observable outcome (`blocked_reason` set immediately) without ever
touching a port from the abandon path.

## In scope

- `src/orc_werk/core/reducer.py` — `FACT-ATTEMPT-ABANDONED`'s `BLOCKED`
  branch: derive `blocked_reason` eagerly.
- `src/orc_werk/cli/affordances.py` — `render_next_block`/`next_entries`'s
  shared `blocked-*` grouping: a distinct `attempt-abandoned` budget-note
  branch so `next:` guidance never falls through to the generic
  assurance-budget wording.
- `src/orc_werk/cli/journal_reading.py` — `BLOCKED_REASON_ATTEMPT_ABANDONED`
  constant, named for the same CLI-presentation-only reason as its two
  siblings (`BLOCKED_REASON_RETRY_BUDGET_EXHAUSTED`,
  `BLOCKED_REASON_ASSURANCE_INCONCLUSIVE`).
- `docs/domain/state-machines/delivery.md` — item 9's transition-table row
  and prose corrected to describe the eager-derivation, deferred-
  confirmation shape.
- `docs/scenarios/SCN-010-abandon-attempt.md` — step 3 and the mutation
  check corrected to match.
- `CHANGELOG.md` — `Unreleased`/`Fixed` entry.
- `tests/scenarios/test_cli_abandon.py` — regression: a real, temp-journal
  CLI abandon that exhausts the retry budget lands `blocked_reason=
  attempt-abandoned` immediately in text and JSON, durable across a fresh
  `orc status` process, without any `FACT-WORK-BLOCKED`/`DEC-BLOCK` having
  folded yet.
- This card and its index registration.

## Out of scope

- Any change to the retry budget (`INV-018`/`INV-019`), the assurance
  budget (`INV-021`), or `orc cancel`'s cancellation semantics.
- A new sentinel or a new field carrying the operator's prose: the prose
  was always durable on `FACT-ATTEMPT-ABANDONED` and stays there;
  `blocked_reason` stays the single existing discriminator field.
- Folding the confirming `FACT-WORK-BLOCKED` from within `abandon_attempt`
  itself, or otherwise dispatching any port Effect from the abandon path
  (rejected shape, see above): issue #165's stub-port-wedge concern is
  unchanged and still governs when that confirmation may safely fire.
- Issue #254 (`orc --state active` never clears a terminal `BLOCKED` row):
  a related but distinct residue-visibility gap, not this card's scope.

## Acceptance

- `bash scripts/check.sh` is green.
- A real, temporary-journal `orc dispatch --abandon-work ... --abandon-
  reason ...` that exhausts the retry budget prints
  `blocked_reason=attempt-abandoned` in its own text output and in a
  subsequent, fresh `orc status --json` process's `works[].blocked_reason`
  — never `None`/`null` and never `retry-budget-exhausted`.
- The same run's `next:` guidance (text and JSON) names the
  `attempt-abandoned` reason directly, never the generic
  `assurance-inconclusive` budget wording.
- Regression coverage distinguishes terminal abandon-to-`BLOCKED` from
  ordinary `retry-budget-exhausted` and from a `READY`-with-budget abandon
  (the two other item-9 shapes), and confirms no `FACT-WORK-BLOCKED`/
  `DEC-BLOCK` has folded within the abandon invocation itself.

## Ambiguities encountered

None. Issue #288 names the existing `blocked_reason` field as the
discriminator to fix and explicitly permits either exposing the existing
literal or a new one carrying the same distinguishing property; this card
takes the former (no new sentinel needed — `policy._block_reason` already
defines `"attempt-abandoned"` for `FACT-WORK-BLOCKED`'s later
confirmation) per the "no new sentinel or new fields when existing
contract suffices" instruction.
