# Changelog

Consumer-facing changes to orc, per released version. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow 0.x semver
(minor = new capability, patch = fixes only). Breaking changes are called out
explicitly in a **Breaking** subsection — absence of that subsection means the
release is fully backward compatible for existing configs and journals.

Release discipline: every version bump lands with (1) its entry here, (2) an
annotated tag `vX.Y.Z` on the bump's merge commit, and (3) a GitHub release
carrying the entry as its notes — so consumers pinning by tag or watching
releases see what changed without reading the git log. `orc version` reports
the running version; finding reports should include it.

## [0.5.0] — 2026-09-02

### Breaking
- **`acp` `ExecutionPort` adapter and no-mistakes `AssurancePort` adapter
  REMOVED** (`ADR-0005`, #214, #217): orc goes all-in on push recording —
  executors are always external and push observations in; orc never
  pull-observes another process's lifecycle. Removed with the adapters:
  `execution.ttl` and the acp-exclusive execution config keys (`agent`,
  `cwd`, `thought_level`, `model`, `approve_all`). A config naming the
  removed `"acp"` or `"no-mistakes"` adapter now fails with the canonical
  `ERR-VALIDATION`, carrying migration guidance in its `next` hint.
  `CONF-EXEC-005` and `SCN-016` are superseded in place (annotated, not
  deleted — past journals and docs referencing them stay interpretable);
  the `acp-settlement/v1` extension is superseded. **Escape hatch:** pin
  `v0.4.1`, the last release carrying the adapters. **Migration:** run
  executors externally and record observations in — `orc record`,
  merge-only config edits, `orc dispatch --wait` as the wake — per
  `PLAYBOOK-AGENT-CLI`; the `command` assurance adapter (`SCN-015`, #194)
  is the in-repo verify-seat replacement for the no-mistakes adapter's
  role. See `docs/decisions/ADR-0005-push-recording-not-pull-observation.md`
  for the full ruling. Anchor issue: **#214**.

### Added / Changed
- **`orc dispatch --wait`** (`SCN-017`, #210, #213): `--wait
  [--timeout SECONDS] [--poll-interval SECONDS]` internalizes the
  re-dispatch poll loop until the run's pending fingerprint moves or the
  run goes terminal, then exits `3`/`0`/`1` exactly as an equivalent
  non-`--wait` dispatch would. An unchanged fingerprint after `--timeout`
  seconds exits a new code, `4`. Waiting journals nothing beyond what its
  internal ordinary passes would have.
- **Pending wording now names settlement observation, not just operator
  input** (#210, #212): exit `3`'s message no longer implies only a human
  can supply the missing outcome — an external executor's pushed
  observation, picked up on re-dispatch, resolves it too.
- **`ADR-0005` accepted** (#214, #215): the operator ruling that motivates
  this release's Breaking section — recorded as the canonical decision
  document.

## [0.4.1] — 2026-09-01

No breaking changes. Existing configs and journals need no migration.

### Fixed
- **acp queue-owner no longer dies mid-run; vanished workers are surfaced**
  (#206, `SCN-016`, `CONF-EXEC-005`): the acpx queue-owner ran with the 300s
  idle default, so a long/idle turn could kill the executor mid-run and the
  adapter reported `EXECUTING` forever. Two changes: (1) a new optional
  `execution.ttl` config key (non-negative integer, default `0` = keep-alive)
  emitted as the top-level `--ttl` flag, so the worker no longer dies at idle;
  (2) when a worker does vanish, the adapter now settles the attempt **failed**
  under a strict four-condition corroboration — the turn was prompted, `status`
  reports `no-session`, the stream shows real turn activity that then stopped,
  and no terminal result exists — recording the evidence in `acp-settlement/v1`.
  A vanished worker with an *empty* stream stays `RUNNING` (indistinguishable
  from a session still starting up — the #157 ambiguity rule), so that
  recovery-verb gap is tracked separately in #203; the keep-alive leak from
  `ttl=0` is tracked in #207.

## [0.4.0] — 2026-08-31

No breaking changes. Existing configs and journals need no migration.

### Added
- **`command` assurance adapter** (#194, `SCN-015`, `CONF-ASSURE-006/007`): an
  operator-authored, in-repo script can be the verify seat. Set
  `assurance.adapter = "command"` with a `script` (resolved inside `cwd`), and
  orc runs it against the bound candidate — exit 0 → accepted, exit 1 →
  rejected, any other exit / signal / timeout → inconclusive (never guessed).
  The script receives the candidate identity as JSON on stdin (never argv or
  shell), and its stdout can only *enrich* evidence, never override the verdict;
  malformed output is dropped and the drop recorded. Requires `candidate.adapter
  = "git"`. This is the lightweight path to a script-driven reviewer without a
  bespoke adapter. `PORT-ASSURANCE` was unchanged.
- **`executor-identity/v1` is now a registered extension** (docs/extensions/):
  the seat-identity payload the CLI emits (`model`, `session_ref`, `seat_ref`,
  `role`) has a normative schema instead of being a bare convention. Still
  observational — the kernel never branches on it.

### Fixed / Docs
- **Documentation debt from 0.2.0/0.3.0 repaid** (consolidation pass): the
  third legal `DEC-ABANDON-ATTEMPT` shape from #191 (the null-candidate rest)
  now appears consistently in `PROTOCOL-DECISIONS`, the CLI-usage playbook, and
  the orchestrator docstring; `orc record` is documented in the CLI-usage
  playbook and the packaged onboarding skill (bumped to v3); `docs/INDEX.md`
  refreshed; a few dead symbols removed. No behavior change.

## [0.3.0] — 2026-08-31

No breaking changes. Existing configs and journals need no migration.

### Added
- **`orc record` verb** (#192): record an assurance verdict without hand-editing
  the run's backing config. Validates and merge-appends the entry — acp attempts
  carry only the `assurance` key, scripted entries keep their outcome/candidate —
  then prints the exact resume command as its `next:` affordance. It records only;
  advancing the dispatch stays the dispatch party's act (one-party-dispatch
  discipline). First-class flags for `--derived-identity` (composes with the
  0.2.0 stale-candidate check), `--finding` (rides `review-findings/v1`), and
  `--model`/`--session-ref`/`--seat-ref` (rides `executor-identity/v1`). Refuses,
  never corrupts: unknown run/work, a work not awaiting a verdict, or an already
  recorded verdict each get a canonical error. The config is written atomically.

### Fixed
- **Null candidate identification no longer wedges a run** (#191,
  `SCN-014`): when the candidate adapter observes no subject on a settled
  execution (e.g. identification raced ahead of the executor's commit), the
  observation is non-binding and every subsequent dispatch re-derives — the run
  heals on its own once the commit exists. As an escape hatch when a subject never
  appears, `--abandon-work` is now legal from that specific shape (settled-completed
  with no bound candidate) and lands at the resting state without auto-starting the
  next attempt. Candidate identity remains adapter-derived; no hand-authored path
  was added.

## [0.2.0] — 2026-08-31

No breaking changes. Existing configs and journals need no migration.

### Added
- **`derived_identity` on scripted assurance entries** (#180,
  `CONF-ASSURE-005`, `SCN-013`): a verifier can assert its self-derived
  candidate identity; the CLI compares it (subset-equality) against the bound
  candidate and rejects a stale-candidate verdict with `ERR-CONFLICT` before
  anything is journaled. Optional — absent means prior behavior, byte for
  byte. Configs that *use* the key require orc ≥ 0.2.0 (older CLIs reject it
  as unknown).
- **orc-ledger skill versioning** (#171): the packaged skill carries a
  frontmatter version and a content-hash changelog registry; `orc onboard`
  auto-upgrades untouched older installs and never clobbers operator-modified
  copies. Onboard also gained `--agents-block {slim,full}` and
  `--ledger {local,committed}` with a self-contained adopter surface
  (#166, #167).
- **`scripts/watch_pr.py`** (#170): merge-frontier classifier (conflicts >
  threads > CI > gate) with verdict-staleness checking.

### Fixed
- **Profile composition** is now honest end-to-end: profiles are partial
  overlays composed under the documented precedence (explicit `--config` over
  persisted run config over profile), `orc validate` composes the profile
  (#169, #175), and overriding a section's adapter drops inherited keys
  exclusive to the previously selected adapter instead of failing validation
  (#174) — a repo profiled for acp can dispatch scripted runs again.
- **acp settlement requires terminal quiescence** (#181): an `end_turn`
  emitted during a provider retry no longer settles the attempt as completed;
  post-result activity means still-running, and suppression evidence rides
  `acp-settlement/v1`.
- **Candidate binding is race-hardened** (#164): the git adapter binds a
  quiescent head (two stable reads, no index.lock), and the race marker is
  provenance, never identity.
- **`--abandon-work` stops at the resting state** (#165) and dispatch warns on
  candidate divergence (#163).
- **Honest onboard reports** (#179): auto-upgrade and mode-mismatch notes no
  longer claim `--force` or "operator-modified" untruthfully.

### Docs
- Verify/ship seat provenance guidance: identity payloads carry a per-seat
  `seat_ref` so seats sharing one session remain distinguishable from the
  journal alone (#182). Engineering-method playbook extended with ten
  operating/method pulls (#168).

## [0.1.0] — 2026-08-30

First versioned release. Everything earlier is unversioned M0–M4 development
history (delivery kernel, journal/replay model, acp + git + beads adapters,
scripted adapters, onboarding, reports).

### Added
- **`orc version`** (#162): honest install identity — package version plus
  git sha (`+dirty` when applicable) for checkouts, degrading legibly for
  wheels. The finding issue template asks reporters to include it.
- **`CANCELLED` terminal state and `orc cancel`**: operator-only cancellation
  from any non-terminal state, journaled as `FACT-WORK-CANCELLED`.
- **Verify-seat surface**: `orc validate` (profile-composed config
  pre-flight), `orc verdict` (read the latest assurance), and a
  proof-of-ingestion echo on dispatch.
- **Registered extensions**: `assurance-context/v1` (verify-seat audit base),
  `acp-settlement/v1` (settlement diagnostics),
  `git-candidate-identification/v1` (observation provenance).

### Fixed
- **acp false-fail eliminated** (#157): a "dead" daemon report is corroborated
  (nonzero exit or `pidAlive: false`) before an attempt is failed; ambiguous
  liveness maps to still-running.
