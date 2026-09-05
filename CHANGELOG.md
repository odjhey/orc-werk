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

## [Unreleased]

No breaking changes. No migration: every journal written before this release
folds under an assurance budget of `1`, which reproduces its previous
behavior exactly, and assurance 1's `FX-START-ASSURANCE` idempotency key is
unchanged.

### Added
- **Bounded assurance re-request on `inconclusive`** (`ADR-0006`, #264):
  an `inconclusive` assurance settlement no longer ends the Work outright.
  It now spends a second, separate budget — `max_assurance_attempts`
  (`INV-021`, default `2`, journaled at run creation and single-authority
  thereafter like `max_attempts`). Within budget the kernel re-requests
  assurance of the *same* candidate under a new assurance identity; only
  exhausting the budget resolves to `BLOCKED` with the unchanged reason
  `assurance-inconclusive`. An assurance re-request never consumes the ship
  seat's retry budget (`INV-018`): a verifier that cannot decide costs
  assurance budget, never execution attempts.
- **`orc record --verdict inconclusive`** — the verify seat's honest verdict
  when it evaluated the candidate and cannot decide, or could not evaluate
  it at all. The verdict fills the slot for the run's current assurance
  number.
- **`--max-assurance-attempts` flag and `max_assurance_attempts` config key**
  — layered exactly like `--max-attempts`/`max_attempts`, persisted at
  creation, and match-or-refuse on resume (`ERR-VALIDATION` naming both the
  journaled and the requested value).
- **Attempt-entry `assurances` array** — the ordered sibling of `assurance`,
  consumed in order by `assurance_number` (element `0` *is* `assurance`;
  supplying both is `ERR-VALIDATION`). `orc record` writes and, when needed,
  migrates into it, so an incremental run never hand-authors it.
- `orc status`, `show`, `report`, `verdict`, and the `next:` affordances now
  name the assurance index and render every assurance of an attempt, so a
  re-request reads as a re-request rather than as a lost verdict.

### Changed
- `FX-START-ASSURANCE`'s `INV-020` key gains an `assurance_number` component
  for the second and later assurances of a candidate (`…|<fingerprint>|2`).
  The first assurance keeps the pre-decision key form verbatim.
- `orc validate`'s per-attempt assurance echo now names the assurance number.

## [0.9.0] — 2026-09-04

No breaking changes. No migration.

### Added
- **`--json` on `orc status` and the bare index** (#53, PR #257): versioned
  machine documents (`orc-status/v1`, `orc-index/v1`) carrying the
  projection, journaled refs with resolve commands, and structured `next`
  affordances sharing one helper with the text render so the two surfaces
  cannot drift. Exit codes unchanged; byte-stable output; canonical errors
  stay on stderr. Verified by a seat driving a full delivery lifecycle
  through JSON alone.
- **Landing as runnable resolve affordances** (#65, PR #258): a derived
  `landing` row appears in `refs`/`show`/`report`/JSON wherever a run's
  refs carry `gh-pr:N` — resolve command `gh pr view N --json
  state,mergedAt,mergeCommit`. Per the reference-first doctrine nothing is
  stored: the forge owns the merge, the ledger points, the viewer
  resolves. `gh` enters the `--resolve` allowlist in the narrowest vetted
  shape (`pr view` with `--json` required; web/repo/jq/template flags
  refused). Closes the oldest open dogfood finding.
- **Coverage hygiene** (PR #259): locking failure-matrix and
  context-manager tests (`adapters/locking.py` measured 100% line and
  branch), a deterministic pagination unit lane (100%), honest SCN/CONF
  traceability citations (each verified to assert its clause; one
  genuinely missing CONF-JOURNAL-004 test added), and true-coverage
  accounting for subprocess-driven CLI tests documented in tests/README —
  real overall coverage is 92.7% line / 84.5% branch; earlier lower
  figures were measurement artifact.

### Changed / Fixed
- **`review-findings/v1` admits string entries** (#249, PR #255): the
  free-text findings every verify seat records are now schema-conformant,
  retroactively including the ledger's history; the structured object form
  remains for richer producers. The #227 dev-gate's expected-failure
  marker is gone — the suite runs with zero expected failures.
- **String findings render** (#256, PR #258): `orc show`/`history` display
  string findings instead of silently skipping them.

## [0.8.0] — 2026-09-03

No breaking changes. Existing configs and journals need no migration; a
permanent `.state.lock` file now appears in each run directory (by design —
its existence carries no meaning and it is never deleted).

### Added
- **`CONTRACT-STORAGE-CONCURRENCY`** (PR #251, operator ruling): the
  file-backed CLI concurrency contract — locking, lock scope and ordering,
  atomic snapshot replacement, append-only discipline, durability levels,
  canonical lock identity, failure behavior, and a required multi-process
  test battery — adopted verbatim with three orc amendments (per-run
  `.state.lock` group identity; a timestamp carve-out preserving replay
  determinism; the one-dispatcher-per-run rule demoted from correctness
  precondition to seat semantics). New canonical error `ERR-BUSY`. New
  scenario `SCN-019`.
- **The storage layer now honors it** (PR #252): OS advisory locking
  (`fcntl`) around every journal append and config read-modify-write,
  lock-before-read on both record paths, `_persist_effective_config`
  upgraded from a bare write to locked atomic replacement, the
  `profile.json` writer covered, bounded lock timeouts surfacing
  structured `ERR-BUSY` (never an unlocked fallback), and the `SCN-019`
  eight-item battery running in separate OS processes — including
  SIGKILL-while-holding-lock recovery and unlocked-storm mutation checks
  proving the tests detect lost updates. Correctness under concurrent CLI
  processes no longer depends on the one-dispatcher convention (§13).

### Changed
- Journal appends re-derive `seq` under the lock instead of trusting a
  per-instance cache (the cache was unsafe under independent concurrent
  appenders); measured cost ~1.2ms per append on a 500-record journal,
  noise at typical sizes, trade documented in the journal module.

## [0.7.3] — 2026-09-03

### Fixed
- **Journal-only verbs tolerate invalid persisted configs** (#236, PR #246):
  `orc cancel` and `orc dispatch --abandon-work` now act on a run whose
  persisted config fails validation (a loud one-line warning, then the
  journal-only operation proceeds). Pending legacy runs are no longer
  stranded by a breaking adapter removal — the pin-back recovery dance is
  obsolete. `dispatch`'s own refusal of invalid configs is unchanged.
- **Null-candidate identification heals instead of crashing** (#244, PR
  #247): a `FX-IDENTIFY-CANDIDATE` that journaled `candidate: null` (e.g.
  the worktree was deleted before settlement) crashed every subsequent
  verb with an `AttributeError`; the defect was a None-unsafe read dating
  to PR #189, not the `SCN-014` machinery, which is reaffirmed unchanged.
  Now: no crash, a `next:` line names the cause and the fix ("ensure
  `candidate.repo_path` exists and re-dispatch — re-derivation is
  automatic"), already-damaged journals replay cleanly, and restoring the
  path lets the run settle truthfully.
- **SCN-017/SCN-018 timing tests are deterministic under load** (#232, PR
  #245): event-bound assertions with generous early-exit deadlines replace
  wall-clock margins; proven 20/20 green under a triple-suite host
  saturation. The flake class that caused one spurious review rejection is
  closed.

### Added
- **Producer-side extension dev-gate** (#227, PR #248, operator ruling:
  dev-gate only): the test suite now validates extension payloads emitted
  by orc's own code paths against their registered schemas, with a
  registry-coverage guard that fails loudly when a newly registered
  extension lacks a validator. Runtime opacity (`CONF-EXT-006`) is
  untouched. The gate found a real mismatch on its first run — tracked as
  #249 (`--finding` strings vs the structured `review-findings/v1`
  schema), carried as an expected failure until reconciled.

## [0.7.2] — 2026-09-03

### Fixed
- **Replay divergence on flag-supplied retry budgets** (#240, PR #242): a
  `--max-attempts` given only as a dispatch flag was journaled into
  `FX-CREATE-WORK` but never persisted, so a bare `--run-id` resume evaluated
  retry policy under the default budget — journaling a `DEC-RETRY` the run's
  own recorded budget forbids and permanently wedging the read verbs
  (`status`/`history`/`record` raised `ERR-CONFLICT` on the run's own journal
  while `dispatch` kept advancing). Now, per the `SCN-008` amendment: the
  **journaled budget is the single authority for every verb**; an explicit
  differing `--max-attempts`/config value on resume is refused with
  `ERR-VALIDATION` naming both values; a flag-supplied budget persists into
  the run's `config.json` at creation; and every mutating pass asserts its own
  journal replays cleanly before exiting, so any future divergence fails
  loudly at the source instead of wedging. Journals already wedged by the old
  behavior are documented as unrecoverable legacy (the #52/#77 precedent).

## [0.7.1] — 2026-09-03

Documentation-only release; no code changes (`src/` and `tests/` are
byte-identical to 0.7.0). Cut so adopting projects can pin a tagged version
that carries the onboarding surface.

### Added
- **`PLAYBOOK-AGENT-ONBOARDING`** (`docs/playbooks/agent-onboarding.md`,
  #239, closes #238): the single file an operator points an agent at —
  "onboard this project to use orc (+ergo), see this file". Imperative,
  sandbox-verified end to end: install with loud failure (including the
  shell-alias invisibility trap), `orc onboard`, the ten-step delivery loop
  with a git candidate config, updating the adopting repo's own agent docs,
  optional ergo wiring via observers, and a done-when checklist.
  `PRODUCT-ADOPTION` and `PLAYBOOK-ERGO-COEXISTENCE` now point to it.
- **`PLAYBOOK-ERGO-COEXISTENCE`** (`docs/playbooks/ergo-coexistence.md`,
  #235): running ergo (agent backlog) and orc side by side — division of
  authority, observer wiring as the sole writer of terminal ergo states,
  run-id conventions.
- **Second-repo adoption field report** (`docs/reports/2026-09-03-xatu-adoption-field-report.md`,
  #237): five incidents with costs from operating 0.4.1 → 0.7.0, merged with
  maintainer verification amendments; its promotions are tracked (#236 landed
  as an issue; #238 closed by the onboarding guide).

## [0.7.0] — 2026-09-03

No breaking changes. Existing configs and journals need no migration.
Journals recorded under 0.6.0 that carry the short-lived
`execution-session/v1` evidence-refs shape (see Changed, below) are
tolerated as historical passthrough — no migration is offered or needed.

### Added
- **`--journal` (and every journal-dir-resolving verb) refuses a journal
  dir that is itself a run directory** (closes #220, #228): pointing
  `--journal`/`ORC_JOURNAL_DIR`/the default `./.orc` at a directory that
  is itself a run's own directory (one containing `journal.jsonl` or
  `config.json` at its root) previously let `dispatch` silently nest a
  duplicate run underneath it — forking the run's history — and let read
  verbs misresolve the run's own sidecar files as phantom run ids,
  sometimes crashing outright. The guard now lives once at the shared
  `resolve_journal_dir` choke point, so every verb that resolves a
  journal dir refuses identically, with `next:` guidance pointing at the
  parent directory and bare `orc` for orientation.
- **`FACT-EXEC-SETTLED` carries optional canonical `artifact_refs`**
  (#224, #231): declared on `PROTOCOL-FACTS` mirroring
  `FACT-ASSURE-SETTLED`'s `evidence_refs` phrasing; the orchestrator
  folds `ExecutionObservation.artifact_refs` into the fact when non-empty,
  and `orc show`/`orc refs`/`orc report` surface it alongside the existing
  evidence-refs treatment.
- **orc-ledger skill v4 teaches `orc record --outcome`** as the ship-seat
  recording sugar (#230), matching the verdict path's existing verb
  documentation.
- **`orc dispatch --wait` and observer hooks get dogfood concern-tag
  coverage** (#233): `dogfood/README.md` gains `wait`/`observers` concern
  tags, with new seeded corpus scenarios `DFS-014` (`--wait`'s movement/
  timeout/validation exits) and `DFS-015` (observer hooks' fire-once/
  replay-safety/hung-observer/escaping-command behaviors).

### Changed
- **`orc record --outcome`'s `--evidence-ref` now rides the canonical
  attempt-entry `artifact_refs` field instead of an `execution-session/v1`
  extension payload** (issue #224, #227, #231, `ADR-0005`). The short-lived
  0.6.0 emission constructed `extensions["execution-session/v1"] =
  {"evidence_refs": [...]}` — but that extension's registered schema
  requires `provider`/`native_session_id` and never declared
  `evidence_refs`, making the 0.6.0 shape schema-nonconforming from the
  day it shipped (issue #224's schema-hygiene finding). `--evidence-ref`
  now writes the attempt entry's canonical `artifact_refs` key instead,
  transported losslessly into `FACT-EXEC-SETTLED.artifact_refs`, mirroring
  the verdict path's `evidence_refs` → `FACT-ASSURE-SETTLED` precedent
  exactly. The verb's flag surface (`--evidence-ref`, repeatable) is
  unchanged and no config/journal migration is needed or offered; 0.6.0
  journals that already carry the old `execution-session/v1` payload keep
  it as opaque, tolerated historical passthrough per `CONF-EXT`'s
  unknown-field tolerance (`docs/extensions/execution-session/README.md`).

### Fixed / Docs
- `SCN-018` step 11's containment wording corrected — the parenthetical
  had listed "resolution outside `cwd`" alongside warn-only spawn
  failures, contradicting the Containment section's eager pre-spawn
  `ERR-VALIDATION` rejection for that case (matches the merged #225
  implementation); a stale exit-code-3 docstring ("pending operator
  input", pre-#212 wording) updated to "pending settlement"; three
  historical-precedent comments in the Beads mirror adapter reworded so
  they read as history, not live dependencies (#229).
- Dogfood-sweep friction repayment, all doc/corpus gaps with zero product
  bugs found (#233): `orc record`'s docs and the verify-seat protocol now
  say plainly that `--derived-identity` is checked shape-only at record
  time, with the real comparison against the bound candidate's identity
  (and any `ERR-CONFLICT`) surfacing only at the next dispatch; the
  Observer hooks docs gain a callout that relative `command[0]` resolves
  against the dispatching process's cwd, not the repo root, so a script
  that worked at authoring time can silently degrade to the
  missing-script warning on a later `--run-id-only` resume or `--wait`
  from elsewhere; `DFS-008`'s corpus now uses the current per-run journal
  layout and corrects a stale "identical stdout" claim (the normative
  assertion is the journal line count, not byte-identical stdout).

## [0.6.0] — 2026-09-02

No breaking changes. Existing configs and journals need no migration.

### Added
- **`orc dispatch --wait` tolerates transient config races** (`SCN-017`
  amendment, #216, PR #222): a `--wait` pass whose config load/validate
  raises `ERR-VALIDATION` mid-wait is now treated as transient — a
  recorder's non-atomic write can be observed torn mid-write — and is
  skipped and retried after the poll interval, capped at 3 consecutive
  failures before surfacing the ordinary canonical error (exit `2`,
  byte-identical to a non-`--wait` dispatch of the same bad config). A
  failure on the wait's very first internal pass is never treated as
  transient — fail-fast on invocation start is unchanged. Also fixes the
  flake this amendment traces to at its source: the test's own delayed
  settlement writer now writes atomically (write-temp + `os.replace`,
  matching `orc record`'s writer) instead of a direct write.
- **`orc record --outcome completed|failed`** (PR #223): the ship-seat
  sibling of the `#192` verdict path — records an execution outcome into
  the run's backing config by the same merge-only, validate-first, atomic
  write, record-only, never advances the run. Mutually exclusive with
  `--verdict` (`ERR-VALIDATION` when both or neither given); mirrors the
  verdict path's refusal taxonomy (`ERR-NOT-FOUND` for unknown run/work,
  `ERR-CONFLICT` for not-awaiting or already-recorded). `--evidence-ref`
  rides `execution-session/v1`; `--model`/`--session-ref`/`--seat-ref`
  become `executor-identity/v1` with `role: "ship"` (the verdict path's
  `role: "verify"` is undisturbed).
- **Observer hooks** (`SCN-018`, #193, PRs #219 and #225): config-declared
  `observers.{on_settle,on_verdict,on_blocked}` fire fire-and-forget,
  at-most-once, replay-safe on facts newly appended by the current
  dispatch pass. Each entry is an argv-only command (no shell) run
  contained inside `cwd`, given the triggering fact as JSON on stdin;
  optional `timeout_seconds` (default 30) is enforced by a small stdlib
  supervisor that spawns the observer in its own session/process group,
  so dispatch blocks only for the spawn and exiting orphans nothing —
  enforcement travels with the observer's own delegated supervision, not
  with dispatch's process lifetime. Generalizes the Beads mirror's
  write-only posture (`INV-014`) and reuses `SCN-015`'s argv-list/
  no-shell/containment/process-group-timeout discipline. CLI-composition
  layer only — `src/orc_werk/core` and `src/orc_werk/app` are untouched.

### Changed / Fixed
- **Abandon-legality predicate single-sourced in core** (#200): the
  three-way `FACT-ATTEMPT-ABANDONED` legality check (candidate-
  observation conflict / awaiting-candidate settled execution /
  unsettleable current assurance) now lives once in
  `core.reducer.abandon_legality`; the reducer's replay-time check and
  the orchestrator's `abandon_attempt` preflight both call it instead of
  each re-deriving the condition independently. Pure dedup, no legality
  change.
- **Null-candidate re-derivation journals append-on-change only** (#198):
  `FX-IDENTIFY-CANDIDATE` re-derivation now journals only when the
  observation changes (first-ever null, or null → subject), matching the
  pending-assurance re-poll's no-op-until-change behavior — no more
  per-dispatch null growth. The port is still re-invoked every dispatch
  (re-identification is never suppressed by an existing record, per
  `SCN-014`'s mutation check).
- **Refs docstrings updated to historical-provider wording** (#221): two
  stale docstring references to the removed acp adapter reworded per
  `ADR-0005`. Comment/docstring only — zero functional diff.

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
