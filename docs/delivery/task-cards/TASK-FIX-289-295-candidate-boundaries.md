---
id: TASK-FIX-289-295
type: task-card
status: current
authority: normative
description: Candidate-only blocking assurance (issue #295) plus an explicit operator abandon basis and a real-git divergence warning for a frozen, externally-invalidated candidate (issue #289).
implements: []
verifies: []
---

# TASK-FIX-289-295 -- Candidate boundaries

Design source: issues #289 and #295, `docs/reports/2026-09-07-m5-pilot-retrospective.md`
§2 items 3/4, `agent://ScoutCandidateAuthority`'s recon. Not tied to any
M-series milestone: two standalone fix cards sharing one PR because both
are the same underlying boundary question -- what counts as "the
candidate" for assurance and re-verification purposes, and what an
operator may do when reality outside the ledger moves out from under a
frozen one.

## The gaps

**#295.** A verify seat's `reject` verdict is supposed to be about the
diff at the derived sha -- the candidate -- but nothing said so
explicitly. A real repro (`task-m5-007-r2`, PR #291) rejected an
otherwise-fully-verified candidate for exactly one defect that lived in
the PR's own mutable title/description text, not the diff. The fix round
corrected the PR body only; `orc record` + `orc dispatch` then re-observed
the identical git fingerprint, mechanically inherited the correction round's
fresh verdict with no review of the diff at all -- correct kernel
mechanics, but nothing in the seat docs said a PR-prose-only defect should
never have forced that reject/re-verify round in the first place, nor
that the watchtower carries a real, separate obligation to fix a
known-misleading PR description before merging even when the verdict
never blocked on it.

**#289.** A ship candidate can freeze at `orc record --outcome` and enter
`ASSURING`, and the ledger had no affordance to recognize -- let alone
recover from -- a *sibling* run's settlement (or any other external
event) invalidating a present-tense claim in that frozen candidate.
`record_execution_outcome_entry` rejects a second recorded outcome
unconditionally (`INV-007`/`INV-008`: rebinding a frozen candidate whose
evidence may already be bound to it would violate evidence-candidate
binding, not the assurance re-request budget the pilot retrospective
mis-cited as `INV-021`). `SCN-010`'s existing abandon-attempt scenario
only documented one basis for abandoning an unsettleable Assurance --
issue #95's adapter-orphaned session -- leaving no documented basis for
the mechanically identical case where the assurance is live and could
settle on its own terms, but the operator already knows the candidate no
longer reflects reality. Nothing detected the concrete git-divergence
shape of this either: `_warn_candidate_divergence` only ever compared a
*scripted* config's per-attempt candidate against its own journal
binding, with no view of a real git worktree moving underneath a frozen
candidate.

## Outcome

**#295 -- candidate-only blocking, docs-only.** `.omp/agents/verify.md`'s
verdict-decision step and `docs/delivery/watchtower-operations.md`'s merge
pipeline now state explicitly: the candidate is the diff at the derived
sha, never the PR's own mutable prose. A defect confined to that prose
MUST still be reported (`NON-BLOCKING` prefix on the existing free-text
`--finding` convention -- no new finding CLI feature, no structured
disposition field), but MUST NOT by itself turn an earned `accepted` into
`rejected`. The watchtower's merge gate correspondingly gains an explicit
obligation: fix the misleading prose before merging, since editing GitHub
PR text never changes the fingerprint a verdict already judged and so
never re-triggers verification.

**#289 -- explicit operator abandon basis, plus a real-git divergence
warning.** `docs/scenarios/SCN-010-abandon-attempt.md`'s
unsettleable-assurance shape is widened to document issue #289's
externally-invalidated-candidate case as an equally legal basis for the
SAME `DEC-ABANDON-ATTEMPT` mechanics already specified -- same Fact
sequence, same attempt cost, same frozen candidate identity
(`INV-007`/`INV-008`), no new verb, no supersession, no budget waiver; an
exhausted run still requires a new run. `orc_werk.cli.main` gains
`_warn_git_candidate_divergence`, the first real caller of `PORT-CAND-002`
(`CandidatePort.current`) anywhere in the tree: on every non-abandon
dispatch of a `git`-backed run, for each Work resting at
`EXECUTING`/`ASSURING` with a bound candidate, it compares the live
worktree's current fingerprint against the frozen one and warns on a real
mismatch -- silently skipping the adapter's documented `None`
("cannot determine safely") result and never catching or masking a real
adapter error. It never rebinds, never fabricates a verdict, and never
fires on an unchanged worktree or a scripted run (that path stays
`_warn_candidate_divergence`, unchanged). `orc_werk.cli.main` also gains
`_warn_verdict_inheritance`, scoped strictly to `FACT-CANDIDATE-OBSERVED`
records newly appended by the current dispatch pass with no accompanying
fresh `FACT-ASSURE-STARTED`: it names which prior attempt/verdict was
mechanically inherited (`STATE-DELIVERY` item 8), reusing `orc show`'s own
`_settled_fingerprints_by_work` derivation rather than re-implementing the
reducer's `candidate_id`+fingerprint gate, so it can never mis-fire on two
different candidate ids that merely happen to share a fingerprint.

## In scope

- `docs/scenarios/SCN-010-abandon-attempt.md`: widen the
  unsettleable-assurance shape to name issue #289's externally-invalidated
  basis; add `INV-007` to Verifies.
- `docs/reports/2026-09-07-m5-pilot-retrospective.md`: correct the
  `INV-021` evidence-binding mis-citation to `INV-007`/`INV-008`.
- `.omp/agents/verify.md`: candidate-only blocking decision criterion.
- `docs/delivery/watchtower-operations.md`: merge-gate obligation to fix
  `NON-BLOCKING` PR-prose findings before merging.
- `docs/delivery/task-cards/README.md`: this card's index entry.
- `src/orc_werk/cli/main.py`: `_warn_git_candidate_divergence`,
  `_warn_verdict_inheritance`, and their dispatch-pass wiring.
- `tests/scenarios/test_cli_candidate_boundaries.py`.

## Out of scope

- Any new `orc record --finding` structured-disposition CLI feature
  (`NON-BLOCKING` stays a free-text prefix convention, per `EXT-REVIEW-
  FINDINGS-V1`'s separate structured-extension path, which already exists
  and is untouched).
- Any supersession verb, budget waiver, or rebinding affordance for #289
  (operator ruling: attempt cost and frozen identity are preserved
  exactly; an exhausted run needs a new run).
- The reducer's own abandon-legality predicate (`AbandonLegality`,
  `src/orc_werk/core/reducer.py`) -- unchanged; owned by `fix-288-abandon-
  reason`.
- Any change to `_warn_candidate_divergence` (the scripted-config
  divergence warning) or to candidate/fingerprint comparison semantics
  themselves (`PORT-CAND-003`).

## Acceptance

- `SCN-010` documents issue #289's externally-invalidated-candidate case
  as a legal `DEC-ABANDON-ATTEMPT` basis alongside issue #95's, with
  identical mechanics.
- The retrospective's `INV-021` mis-citation reads `INV-007`/`INV-008`.
- `.omp/agents/verify.md` and `docs/delivery/watchtower-operations.md`
  state candidate-only blocking and the watchtower's pre-merge prose-fix
  obligation consistently.
- A real git-backed dispatch: a frozen candidate at `ASSURING`, then a
  real git commit moves HEAD -- the next dispatch warns with the live and
  bound identities named, and neither the eventual verdict nor the
  attempt/budget bookkeeping changes because of the warning.
- The same dispatch pass that mechanically inherits a settled verdict for
  a re-observed candidate (unchanged worktree) names the inherited
  attempt/verdict explicitly on stderr.
- A scripted candidate with a different `candidate_id` that happens to
  share fingerprint with an earlier settled one never triggers the
  inheritance warning -- it is an ordinary fresh assurance request.
- `tests/scenarios/test_cli_candidate_boundaries.py` exercises all of the
  above against real `git` and passes.
