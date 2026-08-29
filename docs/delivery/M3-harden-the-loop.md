---
id: M3-HARDEN-THE-LOOP
type: milestone
status: current
authority: normative
description: M3 — close the wedge class the adoption testing exposed, and make autonomous runs fast to review; most of the originally-proposed scope shipped ahead of the milestone.
---

# M3 — Harden the loop

## Context, and why this milestone is small

M2 closed on wild-adoption evidence (`M2-close-the-loop.md`, M2c status
note). The adoption harvest (2026-08-29) drove a delivery burst that
shipped most of what issue #101 originally proposed for M3 *before this
document existed*: the reference-first surfaces (`orc refs`, PR #104; the
crew-report removal, PR #107; the reference-first disposition in
`CONTRACT-DURABILITY`) and the agent-native error surface (error
affordances, PR #108) are already on master. This milestone deliberately
does not re-claim delivered work; it scopes exactly what remains.

**Theme:** make the xatu-class wedge — a run stuck or corrupted by a
rejected/foreign settlement path — structurally impossible, then stop.

## Phase M3b — Wedge-class closure

Two cards, sequential (both touch assurance/verdict semantics; the first
amends the state machine the second relies on).

- `TASK-M3B-001` — verdict inheritance + operator abandon record
  (approved ruling, issue #76; also resolves issue #95). Docs first:
  `STATE-DELIVERY` transition + scenario before kernel code.
- `TASK-M3B-002` — no-mistakes inspect-side identity guard (issue #92
  scope extension). An already-bound divergent provider run must never
  settle this candidate's verdict.

## Phase M3c — Review experience (operator direction, 2026-08-29)

Autonomy is only trustworthy if reviewing what the autonomous machinery
did is fast. The operator's target experience is one descending
staircase, each level one command: *what happened/is happening* (bare
`orc` + the mirror board) → *this run in depth, including briefs and
hand-offs per turn* → *adapter-specific content via the provider's own
tooling*. Levels one and four have surfaces (`orc`, `orc refs`); the
middle is the gap — a run's narrative is scattered across the journal
(intent, facts, findings), the persisted config (briefs), and provider
transcripts (prompts, agent turns), with nothing composing them. The
issue #111 briefs-starvation incident is the proof of pain.

- `TASK-M3C-001` — `orc show <run> [work]`: the terminal narrative
  view. Per work, per attempt: what was asked (brief/intent, and which
  text actually became the prompt — derived and displayed, never
  guessed), who executed (provider, session ref, duration from the
  times sidecar), what was produced (candidate identity), what was
  judged (verdict, findings summary, evidence refs), and where full
  content lives (resolve commands inline, reference-first). Pure
  composition of existing readers; no new storage.
- `TASK-M3C-002` — `orc refs --resolve <ref>`: shell out to the
  provider's own tooling and show the referenced content inline (the
  issue #100 deferred nice-to-have). Fragility caveat documented per
  the TOON known-issues pattern: assumes the provider CLI surface at
  the pinned version; re-probe on upgrade.

Sequenced after the issue #113 listing-convention lane lands, so both
new surfaces are born conforming to the listing convention rather than
retrofitted. Full task cards authored at dispatch time (the M2 "details
firm up at dispatch" convention); this phase note is their design
source.

## Phase M3d — Onboarding experience (operator direction, 2026-08-29)

Adoption today is hand-work: the `orc` console script exists
(`[project.scripts]` in `pyproject.toml`) but `PRODUCT-ADOPTION` never
states the install path (the live second-repo adoption ran on a
`PYTHONPATH` alias); the orc-ledger skill must be hand-copied into an
adopting repo; subagents in adopting repos have no packaged onboarding
(the skill serves interactive sessions; agents need a repo-doc block or
a file their briefs can name). The pending/incremental default only
works when a fresh seat *knows the protocol* — onboarding is therefore a
correctness surface, not polish.

- `TASK-M3D-001` — `orc onboard` (name firmed at dispatch): scaffolds
  an adopting repo mechanically — `.orc/` gitignore entry, the
  orc-ledger skill installed into the repo's skill path (content
  sourced from the installed package, one canonical origin), a
  printable/writable agents-onboarding block for `AGENTS.md`-style
  files (the six-rule protocol, resurrecting the superseded issue #55
  snippet idea for the audience it was right for: subagents in
  adopting repos), and an install-verification step (`orc` runnable,
  journal dir resolvable, `bd` presence noted-optional). Idempotent
  re-run; refuses nothing it didn't create without saying so.
- Docs: `PRODUCT-ADOPTION` gains the mechanical install story per rung
  (pip install from path/URL → console script; the alias form retained
  as the zero-install fallback), and the onboarding command becomes the
  rung-2 entry step.

## Tail (explicitly unglamorous)

- Trivia sweep (in flight at draft time: DFS-013 enumeration, stale CLI
  doc snapshots, issue #45 payload hygiene).
- Test-hardening (`mutmut`/`hypothesis`) — LOW priority per operator
  ruling (2026-08-29); dev-only, one card when pulled, zero core impact
  (`CLAUDE.md` rule 8 unaffected). Not scheduled to a phase; pulled when
  someone wants it.

## Explicitly NOT in M3 (dormant registry, triggers unchanged)

Rozoro (deferred stands); `acpx claude` provider swap; policy
parameterization; Beads authority graduation (issue #47); multi-repo
registry/profiles (the shared-portfolio *convention* — one `bd`
workspace + `ORC_JOURNAL_DIR` — is in live trial and may generate this
trigger); `--json` (issue #53, trigger: a structured consumer exists);
attention model.

## Acceptance

- `TASK-M3B-001`, `TASK-M3B-002`, `TASK-M3C-001`, `TASK-M3C-002`, and
  `TASK-M3D-001` accepted through the ledger with the standard
  adversarial-verification pipeline.
- A clean scratch repo reaches a working incremental-mode delivery from
  `orc onboard`'s output alone (the M3d acceptance).
- The operator's four review questions (what happened / this run in
  depth / briefs+hand-offs per turn / adapter content) each answerable
  in one command from the previous level's output.
- A regression scenario exists for each wedge shape (same-candidate
  retry; foreign-run settlement) proving the closed behavior.
- The dormant registry above is untouched.
