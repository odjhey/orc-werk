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
