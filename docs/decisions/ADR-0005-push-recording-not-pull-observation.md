---
id: ADR-0005
type: decision
status: current
authority: informative
description: Orc Werk goes all-in on push-recorded observation; it never pull-observes another process's lifecycle.
---

# ADR-0005 — Push recording, not pull observation

## Status

Accepted.

## Context

Orc Werk has run two observation models side by side since M1b:

- **Pull observation** — an adapter itself infers liveness or settlement by
  probing a provider's live process or session (the `acp` `ExecutionPort`
  adapter's `inspect()` scanning a session stream for `stopReason`/activity;
  the no-mistakes `AssurancePort` adapter inferring pipeline state).
- **Push recording** — an external executor authoritatively records an
  observation into the ledger (`orc record`, a merge-only config edit, or a
  re-dispatch that replays the journal), and orc only ever reacts to what was
  pushed.

Every production wedge since M1b traces to the pull side, all through a
pre-1.0 provider stack (`acpx` 0.13.1 / `pi-acp` 0.0.31):

- issue #157 — daemon cold-start false-fails (ambiguous early-stream
  evidence misread as failure);
- issue #181 — terminal-quiescence survey (no reliable "is this process
  still alive" signal without polling);
- issue #203 — empty-stream death with no recovery verb;
- issue #206 — vanished worker, whose own fix lane self-wedged;
- issue #207 — keep-alive leak;
- issue #210 — operator misdiagnosis of settlement (five finished lanes sat
  unnoticed because nothing pushed the news).

Over the same window, the push path — scripted/incremental config edits,
`orc record`, command assurance — ran multiple zero-rejection delivery waves
and never wedged. The issue #210 wave's response, `--wait` (`SCN-017`), is
adapter-agnostic by construction: it internalizes the re-dispatch/observe
loop without adding any new pull mechanism, which is the shape this ADR
generalizes.

## Options considered

1. Keep the `acp` `ExecutionPort` adapter and the no-mistakes `AssurancePort`
   adapter, and keep patching pull-observation edge cases as they surface.
2. Gate pull observation behind an opt-in capability/mode flag, kept in the
   codebase but off by default.
3. Remove pull observation entirely and redefine the product around a single
   model: orc is the contract-first delivery ledger and seat protocol —
   the durable, replayable, seat-disciplined coordination substrate that any
   executor (a Claude session, an acpx lane, a CI job, a human) records
   observations INTO. Executors are always external and push observations
   in; orc never pull-observes another process's lifecycle.

## Decision

Choose option 3.

Six issues in five months against one pre-1.0 provider stack, each one a
distinct flavor of the same root cause ("orc tried to infer another
process's lifecycle instead of being told"), is not noise; it is the
provider stack itself refusing to support the model. Option 1 keeps paying
that tax indefinitely. Option 2 keeps the failure-prone code on the
maintenance surface for a mode dogfooding never chose. Option 3 matches
what the project's own delivery practice already does: the orc-werk
watchtower ships every task card through an external-harness-plus-`record`
lane, never through the `acp` adapter's pull path.

0.5.0 removes the `acp` `ExecutionPort` adapter and the no-mistakes
`AssurancePort` adapter (Breaking). v0.4.1 is the last tag carrying them.
Command assurance (`SCN-015`, issue #194) is the push-shaped verify-seat
replacement for the no-mistakes adapter's role. Autonomous execution goes
dormant with the named trigger recorded in ruling A1's registry entry below
— the descope is a mode change, not an autonomy prohibition.

### Rulings

- **A1.** `execution.ttl` dies with the adapter: it is acp-exclusive and has
  no other consumer.
- **A2.** The `orc refs --resolve` read-only acpx/no-mistakes resolver
  branches are **kept**. Historical journals carry those refs forever, and
  read-only narrative reference resolution is reference-first doctrine
  (`CONTRACT-DURABILITY`), not lifecycle pull observation — resolving a
  reference a past run recorded is not probing a live process.
- **A3.** In-flight `acp` runs on the live ledger are settled or cancelled
  by the watchtower before the removal PR merges. There is no legacy
  validation carve-out.
- **A4.** Removed-behavior docs move to `status: superseded`, linking this
  ADR and the dormant-registry entry it adds; the informative acpx spike
  report (`docs/reports/2026-08-28-acpx-pi-spike.md`) moves to `status:
  archived`.
- **A5.** `TASK-M1-005`'s supersession carves out its surviving
  git-candidate half — the parts of that task card that are not
  acp-specific remain live.
- **A6.** `CONF-EXEC-005` is superseded in place (annotated, not deleted):
  the conformance requirement it specified only has meaning for a
  pull-observing execution adapter.
- **A7.** Issues #203 and #207 close as descoped after removal, not fixed.
  Issue #126's dormant trigger (AcpAssurance) is re-worded — see the
  dormant-registry amendment in `docs/delivery/M4-cockpit-and-clarity.md`.
- **A8.** Beads/git adapter source comments that reference the removed
  adapters (for example, `src/orc_werk/adapters/beads/mirror.py`'s
  "matching the established acp/no-mistakes adapter pattern" comments) are
  comment-only and stay comment-only; they are historical precedent notes,
  not live dependencies, and are out of this ADR's and this PR's scope to
  edit.

### What 0.5.0 removes

- the `acp` `ExecutionPort` adapter (`docs/adapters/acp/`);
- the no-mistakes `AssurancePort` adapter (`docs/adapters/no-mistakes/`);
- `execution.ttl` (A1);
- `CONF-EXEC-005` as a live, testable requirement (superseded in place, A6).

### What 0.5.0 keeps

- `execution-session/v1` (`EXT-EXECUTION-SESSION-V1`) — a provider-neutral
  push channel for session provenance. It was never pull-observation itself;
  it is the durable record an external executor pushes in, and it survives
  unchanged.
- `orc refs` and its resolvers, including the read-only acpx/no-mistakes
  resolve branches (A2).
- `SCN-012`, `SCN-015`, `SCN-017`.
- `CONF-EXEC-001` through `CONF-EXEC-004` and `CONF-ASSURE-001` through
  `CONF-ASSURE-007`, except `CONF-EXEC-005` (A6).

### Migration guidance

Deployments that depend on the `acp` `ExecutionPort` adapter or the
no-mistakes `AssurancePort` adapter should either pin to `v0.4.1`, or shift
those lanes to the external-harness-plus-`record` pattern the orc-werk
watchtower itself already uses for every task card in this repository
(`PLAYBOOK-WATCHTOWER`): an executor runs outside orc's observation and
pushes its outcome in via `orc record` or a merge-only config edit.

Anchor issue: **#214**.

## Consequences

Positive:

- One observation model instead of two competing ones; the class of wedge
  bugs this ADR's evidence base documents has no pull-observation surface
  left to recur on.
- Matches actual dogfooding practice rather than an aspirational autonomous
  mode nothing here has exercised safely.
- `execution-session/v1` and `orc refs` are unaffected — provenance and
  reference resolution were never the pull-observing part.
- Frees the adapter surface for `TASK-M1-005`'s surviving git-candidate
  half (A5) without carrying acp-specific baggage.

Costs:

- Breaking change for any deployment using the `acp` or no-mistakes
  adapters; `v0.4.1` is the last tag that carries them, and migration
  requires either a version pin or a lane redesign (see Migration
  guidance).
- `CONF-EXEC-005`'s pull-observation conformance requirement no longer has
  a live adapter to exercise it against; it is retained as annotated
  history (A6), not deleted, so past journals and docs referencing it
  remain interpretable.
- Autonomous (pull-observed) execution goes dormant; reopening it is a
  fresh spike gated on both a real consumer need and a stable, contractually
  versioned settlement/liveness API from a target provider (dormant-registry
  entry, `docs/delivery/M4-cockpit-and-clarity.md`) — not a quick revival of
  removed code.
- Issue #126's AcpAssurance dormant entry needs its trigger re-worded, since
  its original trigger named the now-removed no-mistakes adapter.

## Related contract IDs

- `CONTRACT-EXTENSIONS`
- `CONTRACT-DURABILITY`
- `PORT-EXECUTION`
- `PORT-ASSURANCE`
- `EXT-EXECUTION-SESSION-V1`
- `INV-013`
- `INV-014`
- `P-001`
- `P-002`
- `P-005`
- `CONF-EXEC-005`
- `TASK-M1-005`
