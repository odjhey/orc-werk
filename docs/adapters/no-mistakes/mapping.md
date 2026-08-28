---
id: ADAPTER-NO-MISTAKES-MAPPING
type: adapter-mapping
status: current
authority: informative
description: no-mistakes-to-AssurancePort mapping for NoMistakesAssurance (TASK-M2-001).
---

# no-mistakes mapping

Implemented by `src/orc_werk/adapters/no_mistakes/assurance.py`
(`NoMistakesAssurance`), driving the `no-mistakes` CLI's agent interface
(`no-mistakes axi`). All `no-mistakes`/`axi` vocabulary -- CLI flags, TOON
field names, pipeline step/gate shapes, run-id format -- stays in this
module and this document, per `INV-014` and `docs/adapters/README.md`.

## Judge-only ruling (watchtower, normative for this adapter)

This adapter is a **READ-ONLY JUDGE of the exact observed candidate**. It
NEVER passes `--yes` to `axi run`, and NEVER calls `axi respond`/`axi sync`
-- any operation that could let `no-mistakes` fix findings or auto-resolve
a gate. A candidate `no-mistakes` mutated (a fix commit) or pushed is a
DIFFERENT candidate than the one this adapter was asked to assure (`P-004`,
`INV-007` through `INV-010`).

**Never-push is mechanical, not incidental (PR #80 fix round, finding B).**
Omitting `--yes` is NOT sufficient to prevent pushing: `--yes` only
governs gate auto-resolution, and a CLEAN candidate that trips no gates
runs the full pipeline INCLUDING the push step (this task's own first
recon transcript showed review -> test -> document -> lint -> **push**
completing, reaching the scratch repo's `origin` remote). Every `axi run`
spawn therefore passes **`--skip push`** (`_SKIPPED_STEPS` in
`assurance.py`) -- verified empirically against the real CLI (read-only
recon, a scratch repo with a real local `origin` remote, never orc-werk's
own repo): a clean pipeline under `--skip push` completed `outcome:
passed` with the `push` step reported `skipped`,
`branch_sync.pipeline.pushed_head` empty, `push_generation: 0`, the
remote's `observed_head` empty, and the local branch head untouched
(`clean: true`); a pipeline-internal commit the `document` step made
stayed confined to `no-mistakes`'s internal gate copy (`current_head`
diverged inside the gate only) and never reached the branch or remote.
Asserted structurally by
`test_every_spawn_passes_skip_push_mechanical_never_push`
(`tests/conformance/test_no_mistakes_assurance_unit.py`) against the
stub's record of the exact `--skip` value each spawn carried.

**Fail-closed note (step rename).** The `push` step name is pinned to the
probed CLI version's own canonical step list (`axi logs --help`: `intent,
rebase, review, test, document, lint, push, pr, ci`). If a future
`no-mistakes` release renames the push step, `--skip push` silently stops
matching anything -- the never-push guarantee would regress without
failing loudly, the same silent-drift failure mode as the TOON parser's
(see "TOON parsing"). The mitigation is the same version re-probe
discipline: before upgrading `no-mistakes` in an environment using this
adapter, re-check `axi logs --help`'s step list and re-run this adapter's
test suite (the known-issues row in `docs/playbooks/cli-usage.md` covers
both hazards).

Concretely: when the pipeline reaches a gate (`awaiting_approval`), this
adapter never advances it. It reads the parked findings and renders its
OWN canonical verdict from them (see "Verdict mapping" below), then leaves
the underlying `no-mistakes` run parked. A human operator -- not this
adapter -- resolves that parked run later (`no-mistakes axi
respond`/`axi abort`), independently of the verdict this adapter already
recorded. See "Limitations" for the operational consequence (a stale
parked run can block a later retry's `repo_path`).

This ruling was evaluated against the judge-only-impossible stop condition
(task card: "If the no-mistakes surface makes judge-only impossible for
some flow, STOP and report") and found NOT to trigger it: `axi status`
gives a genuinely read-only view of a parked gate's findings, sufficient
to render an honest verdict without ever resolving the gate. The
consequence recorded above (parked runs are cleanup the adapter itself
never performs) is a real operational cost, but not an impossibility --
see "Ambiguities" in the PR body for the explicit ruling record.

## Empirical recon (this task)

`no-mistakes@` (installed at `/Users/odz/.local/bin/no-mistakes` at
implementation time) was probed against two throwaway scratch git repos
(never against orc-werk's own repo, per the task brief), one clean and one
seeded with an obvious secret/dead-code bug, driving real `axi run
--intent ...` pipelines (native `claude` agent, no `--yes`) to completion
and to a parked gate respectively:

- `no-mistakes axi status [--run <id>]` is a genuinely non-blocking,
  instant snapshot -- confirmed by polling it repeatedly (every ~15s)
  while a separate, detached `axi run` process drove the pipeline forward
  in the background; each poll returned immediately with the run's
  current state, never blocking on pipeline progress itself. This is the
  crucial empirical fact this adapter's whole design rests on: `axi
  status` genuinely is a safe, cheap, repeatable inspect operation.
- `axi run --intent <goal>` (without `--yes`) blocks the CALLING process
  until the first gate, CI-ready point, or final outcome -- confirmed: a
  clean two-line change ran review -> test -> document -> lint -> push (no
  GitHub remote configured in the scratch repo, so `pr`/`ci` steps
  self-skipped) end-to-end in ~95s with zero findings, terminal
  `run.status: completed`, top-level `outcome: passed`. A seeded-bug
  change instead reached `review` in ~44s and parked there
  (`run.status` stays `running`; a top-level `gate:` block appears with
  `status: awaiting_approval`) with two real findings (a hardcoded-secret
  `error` and a dead-code `warning`) -- it never advanced further without
  a response, confirming the pipeline genuinely waits rather than timing
  out or auto-resolving.
- No `--format json` (or any other machine-structured output) flag exists
  on `no-mistakes`, `axi`, `axi status`, or `axi run` -- confirmed by
  reading every `--help` text on this machine. TOON is genuinely the only
  machine-readable surface (see "TOON parsing" below).
- `no-mistakes axi abort --run <id>` cancels a parked run and reports
  `run.status: cancelled` on the next `axi status` -- used only by this
  task's own recon cleanup, never by the adapter itself (judge-only
  ruling).
- A repo that has never run `no-mistakes init` fails every `axi`/`status`
  command with a PLAIN-TEXT (not TOON) `repo not initialized (run
  'no-mistakes init' first)` message and exit `1` -- this adapter
  recognizes this shape specifically (see "Canonical error translation").

## Poll model: `request()` never blocks; `inspect()` is the sole settlement authority

Mirrors the acp `AcpExecution` adapter's design principle
(`docs/adapters/acp/mapping.md`), adapted for a CLI that offers no
`--no-wait`-equivalent acknowledgement flag:

- `request()` spawns `no-mistakes axi run --intent <text> --skip push`
  **detached** (`subprocess.Popen`, `start_new_session=True`, never
  `--yes`, always `--skip push` -- the mechanical never-push guarantee,
  see "Judge-only ruling" -- never waited on for pipeline completion). It then does a **small bounded
  poll** of `axi status` (default 10s total / 0.25s interval, both
  overridable via `NoMistakesAssurance(spawn_poll_timeout_s=...,
  spawn_poll_interval_s=...)`) purely to observe the new run's id
  appearing -- not to wait on any pipeline progress. This is a
  deliberate, bounded tradeoff: `acpx`'s `--no-wait` returns a
  synchronous, sub-second JSON acknowledgement (`{"action":
  "prompt_queued", ...}`) with nothing further to poll for; `no-mistakes`
  offers no equivalent, so this adapter substitutes a bounded wait for
  "has the daemon registered a queryable run yet" -- structurally
  different from, and strictly weaker than, acpx's synchronous ack (see
  "Limitations").
- `inspect()` is always re-derived from `no-mistakes axi status --run
  <id>` (durable, provider-owned state) -- never from in-process memory as
  the correctness path. An in-process settled-observation cache exists
  only as a fast path (mirrors `ScriptedAssurance`/`AcpExecution`); a
  fresh process re-inspecting the same `assurance_id` reaches the
  identical verdict by re-querying `axi status --run <id>` (`INV-020`),
  exercised directly by
  `test_fresh_adapter_instance_reaches_same_settlement`
  (`tests/conformance/test_no_mistakes_assurance_unit.py`).

## `assurance_id` shape (durable, self-describing)

```text
no-mistakes:<candidate.fingerprint>:<native_run_id>:<repo_path>
```

`candidate.fingerprint` is always `fp-<24hex>` (no colon); `native_run_id`
is `no-mistakes`'s own fixed-width ULID-shaped run id (no colon observed);
`repo_path` is the remainder of the string (a `maxsplit=3` parse is
therefore unambiguous even if `repo_path` itself contains `:`) -- mirrors
`AcpExecution`'s `execution_id` shape/rationale exactly (fixed-width
tokens first, free-form path last).

Both durable facts a fresh process needs are embedded directly, rather
than requiring a separate lookup:

- **`candidate.fingerprint`** is bound once, at `request()` time, to the
  exact `Candidate` this run was requested against (`INV-007`) -- this
  adapter's only obligation toward evidence provenance is faithfully
  reporting the fingerprint it actually evaluated, which embedding it
  durably in `assurance_id` satisfies unconditionally (no in-process
  memory required to report it correctly later).
- **`native_run_id`** lets `inspect()` always query the EXACT run via
  `axi status --run <id>`, never `no-mistakes`'s own ambiguous "active or
  most recent" default -- this is what makes a fresh process's
  `inspect()` immune to a newer, unrelated run having since started in
  the same `repo_path`.

## Cross-process `request()` idempotency (best-effort, unlike acp)

**Structural limitation, honestly recorded rather than solved**: unlike
`acpx`'s `-s <session-name>` (a caller-supplied, deterministic identity
hook that makes `AcpExecution`'s cross-process idempotency airtight,
`docs/adapters/acp/mapping.md` "Idempotency behavior"), `no-mistakes axi
run` accepts no caller-supplied run identity -- every run id is opaque and
provider-generated. This adapter therefore cannot deterministically
re-derive "the same run" from a bare `idempotency_key` alone in a fresh
process the way `AcpExecution` can.

What `request()` actually does, before ever spawning a new run: query
`axi status` (bare, no `--run`) for `repo_path`. If it shows an ACTIVE
(non-terminal: not `completed`/`cancelled`/`aborted`/`failed`) run:

- if the candidate carries a git-shaped `subject_identity['head_sha']`
  (the `GitDiffCandidate` shape this adapter is normally paired with) AND
  it does not match the active run's observed head
  (`branch_sync.pipeline.submitted_head`/`branch_sync.local.head`), this
  is a DIFFERENT candidate's run still owning the branch --
  `request()` raises `ERR-UNSAFE-STATE` rather than guess (see "Stale
  parked run" in Limitations) or spawn a conflicting second run;
- otherwise (heads match, or no `head_sha` signal is available at all --
  e.g. a non-git-shaped candidate, exercised by the shared
  `AssurancePortConformance` mixin's `ScriptedCandidate`-backed fixtures)
  the active run is ADOPTED: its native id becomes this request's
  `native_run_id`, no new `axi run` spawn. This best-effort adoption
  assumes at most one Work drives one `repo_path` at a time -- the same
  "one Work per one configured worktree" assumption
  `docs/adapters/git/mapping.md`/`AcpExecution` already state for their
  own real-adapter pairings.

Exercised by `test_active_run_is_adopted_not_respawned_across_instances`
and the CLI wiring smoke test's "re-dispatch while pipeline is still
running spawns nothing new" assertion (`tests/scenarios/
test_cli_no_mistakes_wiring.py`).

Only a TERMINAL existing run (or none at all) triggers a fresh spawn.

## Verdict mapping (explicit and total)

| Observed `no-mistakes` state | Canonical verdict | Rationale |
|---|---|---|
| `run.status == "completed"`, top-level `outcome: passed` | `accepted` | Terminal, no gate ever parked. |
| `run.status == "completed"`, top-level `outcome: failed` | `rejected` | Terminal failure (e.g. tests failed) with no gate. |
| `run.status == "completed"`, `outcome` missing or an unrecognized value | `inconclusive` | Never guessed toward `accepted` on an unrecognized terminal shape. |
| A top-level `gate:` block is present (`status: awaiting_approval`, any step), with 1+ findings | `rejected` | `no-mistakes`'s OWN review policy already declined to let this exact candidate proceed automatically -- `EXT-REVIEW-FINDINGS-V1-SEMANTICS`'s disposition framing ("may the candidate proceed under the producing review policy") answers no, regardless of individual finding severity. This adapter never resolves the gate itself (judge-only ruling) -- see "Findings mapping" below for how `review-findings/v1` is populated. |
| A top-level `gate:` block is present with 0 findings | `inconclusive` | Genuinely ambiguous (nothing to explain the park); never guessed toward rejected or accepted. |
| `run.status in {cancelled, aborted, failed}` and no `gate:`/`outcome:` | `inconclusive` | A terminal-without-a-verdict shape (e.g. an operator ran `axi abort` on a stale run) -- honestly reported, never fabricated as a candidate judgment. |
| `run.status == "running"`, no `gate:` block | not settled (`state: running`) | Still in flight. |
| No run observed yet matching this exact `assurance_id`'s `native_run_id` | not settled (`state: requested`) | Nothing durable to report yet -- never fabricated. |

Full table exercised by `tests/conformance/test_no_mistakes_assurance_unit.py`'s `NoMistakesAssuranceVerdictMappingTest`.

### Findings mapping (`review-findings/v1`, `CAP-ASSURE-STRUCTURED-FINDINGS`)

Each row of a parked gate's `findings[N]{id,severity,file,action,description}` table becomes one `EXT-REVIEW-FINDINGS-V1-SCHEMA` finding:

| `review-findings/v1` field | Derivation | Honesty note |
|---|---|---|
| `id` | `"<no-mistakes finding id>-<row index>"` | Namespaced with the row index since `no-mistakes` finding ids are short slugs (e.g. `hardcoded-secret`) that are not guaranteed unique within one gate. |
| `severity` | `error` -> `high`; `warning` -> `medium`; `info` -> `info`; anything else -> `medium` | `no-mistakes`'s severity vocabulary is not `EXT-REVIEW-FINDINGS-V1-SCHEMA`'s; this is a small, documented, best-effort lookup table (`_SEVERITY_MAP` in `assurance.py`), never claimed exhaustive. |
| `disposition` | `error` severity -> `blocking`; anything else -> `non-blocking` | Per-finding disposition; the overall gate VERDICT is `rejected` regardless (see table above) -- disposition here describes the individual finding, not the verdict. |
| `category` | Substring-matched against a small hint table (`_CATEGORY_HINTS`: `secret`/`credential` -> `security`, `perf` -> `performance`, `concurren`/`race` -> `concurrency`, `test` -> `testing`, `style`/`lint` -> `style`, `doc` -> `docs`, `compat` -> `compatibility`, `contract` -> `contract`, `maintain`/`dead`/`unused` -> `maintainability`, `data` -> `data-integrity`); default `correctness` | `no-mistakes` finding ids are an open, provider-owned vocabulary this adapter does not control -- this heuristic is intentionally small and non-exhaustive, never claimed authoritative (see "Limitations"). |
| `confidence` | Always `medium` | `no-mistakes` does not emit a confidence signal for review findings; `medium` is a documented neutral default, never fabricated as `high`. |
| `status` | Always `open` | This adapter never fixes/resolves findings (judge-only ruling), so every observed finding is, from its perspective, still open. |
| `location.path` | The finding's `file` column, when non-empty | No line numbers are available from this table shape (see "Limitations" -- `axi logs --full` might carry them but parsing that reliably is out of scope). |
| `evidence` | One `{"kind": "explanation", "summary": <description>, "ref": <no-mistakes finding id>}` entry | `no-mistakes`'s own generated review text is the strongest available support this adapter has; never fabricated as a test/contract reference it does not have. |

## `evidence_refs` shape (externally resolvable, never prose)

Every settled observation's `evidence_refs` carries exactly one structured
reference (never a narrative string):

```python
{
    "no_mistakes_run_id": "<the exact no-mistakes run id>",
    "repo_path": "<the configured repo_path>",
    "command": "no-mistakes axi status --run <run id>",
    "branch": "<observed branch, when known>",
    # only present when settled from a parked gate:
    "step": "<gate step, e.g. 'review'>",
    "logs_command": "no-mistakes axi logs --run <run id> --step <step> --full",
}
```

Every field is independently, externally resolvable by anyone with
`no-mistakes` installed and access to `repo_path` -- literally the exact
command to run, not a description of what happened.

## Requirements / config shape (adapter-owned, opaque to the core)

`requirements` (`PORT-ASSURE-001`, opaque per that port's own doc):

```python
{"intent": "<required, non-empty --intent text for a NEW pipeline run>"}
```

Mirrors `AcpExecution`'s `execution_request['prompt']` exactly, including
the same CLI-composition pattern: `orc_werk.app.Orchestrator` always calls
`self.assurance.request(candidate=..., requirements={}, ...)` (confirmed
by reading `orchestrator.py` -- neither `app` nor `core` threads a
per-work request payload through it), so `src/orc_werk/cli/config.py`'s
`_IntentRequirementsAssurance` decorator fills in `requirements['intent']
= <the run's intent text>` before it reaches `NoMistakesAssurance`, the
same composition-not-modification approach `_IntentPromptExecution` uses
for `AcpExecution`.

CLI dispatch-config wiring (`src/orc_werk/cli/config.py`'s "Real-port
selection" section, `TASK-M2-001` addition):

```json
{
  "assurance": {"adapter": "no-mistakes", "repo_path": "/abs/worktree"},
  "candidate": {"adapter": "git", "repo_path": "/abs/worktree"}
}
```

- `assurance.adapter`: `"scripted"` (default, the pre-existing
  operator-recorded-verdict path) or `"no-mistakes"`. `"no-mistakes"`
  selects `NoMistakesAssurance`, keyed exactly to that constructor's one
  real parameter (`repo_path`) -- no `capabilities`/`no_mistakes_bin`/poll
  timing keys are exposed at the CLI-config layer (none of the existing
  real-port config blocks expose every constructor parameter either, per
  `CLAUDE.md` rule 3's "don't invent unneeded keys" spirit; a future task
  can add them if a real operational need appears).
- **Constraint**: `assurance.adapter == "no-mistakes"` REQUIRES
  `candidate.adapter == "git"` -- rejected otherwise
  (`_validate_assurance_candidate_combo`), mirroring the acp adapter's
  `execution-requires-git` precedent exactly: `no-mistakes` reviews real
  git state at a configured `repo_path`; a config-scripted candidate's
  `subject_identity` would not correspond to anything `no-mistakes`
  actually reviewed, so a settled verdict could never be honestly bound to
  it (`INV-007`). Unlike the acp precedent, this does NOT also require
  `execution.adapter == "acp"` -- `execution` may stay `"scripted"` while
  `candidate`/`assurance` are real (useful for exercising real,
  automatic assurance against whatever is actually in a git worktree,
  without needing a live agent to also drive execution); exercised by
  `tests/scenarios/test_cli_no_mistakes_wiring.py`.
- **Attempts-merge semantics**: when `assurance.adapter == "no-mistakes"`,
  an `attempts[work_id]` entry may NOT carry `assurance` at all -- a real
  `AssurancePort` derives its own verdict automatically; a
  config-declared one would be silently ignored, exactly the same
  rationale `candidate` already follows when `candidate.adapter ==
  "git"`. `outcome`/`states`/`artifact_refs` remain allowed when
  `execution.adapter` stays `"scripted"` (see above).

## Capability honesty

| Capability | Advertised | Proving basis |
|---|---|---|
| `CAP-ASSURE-CANDIDATE-BOUND` | Yes | `request()` binds `candidate.fingerprint` durably into `assurance_id` at request time; every settled observation reports exactly that fingerprint (`INV-007`); exercised by `test_capability_honesty_candidate_bound_advertised_and_exercised`. |
| `CAP-ASSURE-STRUCTURED-VERDICT` | Yes | `accepted`/`rejected`/`inconclusive` are structurally distinct code paths (verdict-mapping table above), never derived from parsing free text. |
| `CAP-ASSURE-STRUCTURED-FINDINGS` (`review-findings/v1`) | Yes, when a parked gate has findings to map | `_settle_from_gate` produces real `EXT-REVIEW-FINDINGS-V1-SCHEMA` findings from observed gate data (see "Findings mapping"); when no findings are available (an `accepted` run, or an `inconclusive` cancelled run) `extensions` is simply empty -- never fabricated. |
| `CAP-ASSURE-MAY-MUTATE-CANDIDATE` | **No -- withheld unconditionally** | The judge-only ruling means this adapter never lets `no-mistakes` create fix commits or push; constructing an instance that requests this capability raises `ValueError` at construction time (`CONTRACT-CAPABILITIES` capability-durability rule), mirroring `AcpExecution`'s unconditional withholding of `CAP-EXEC-RESUME-EXACT`. |

## Canonical error translation

| `no-mistakes` condition | Canonical error |
|---|---|
| `no-mistakes` binary not found on `PATH`, or fails to exec | `ERR-PROVIDER-UNAVAILABLE` |
| stdout/stderr contains `"not initialized"` (the plain-text, non-TOON `repo not initialized (run 'no-mistakes init' first)` shape, confirmed empirically) | `ERR-PROVIDER-UNAVAILABLE` |
| `axi status --run <id>` exits non-zero with stdout/stderr containing `"not found"`/`"no run"` | Not an error -- treated as nothing durable observed yet (`state: requested`), the same honest-absence posture `AcpExecution` takes for a missing `stopReason`. |
| Any other non-zero exit from `axi status` | `ERR-TEMPORARY` (default posture: may succeed on retry, mirroring `AcpExecution`'s default) |
| A different, non-terminal run already owns `repo_path` and its observed head does not match the requested candidate's `head_sha` | `ERR-UNSAFE-STATE` (this adapter never resolves another run's branch ownership itself -- judge-only ruling) |
| `axi run` spawn succeeds but no run id appears within the bounded spawn-wait | `ERR-TEMPORARY` (see "Limitations" -- this also covers an `axi run` invocation that failed immediately, since this adapter never observes a detached process's own exit code) |
| `requirements['intent']` missing/empty/non-string | `ERR-VALIDATION` |
| Malformed/unrecognizable `assurance_id` on `inspect()` | `ERR-NOT-FOUND` |

## Idempotency behavior

- `request()`: same `idempotency_key` -> same cached `AssuranceRun`, no
  repeat `axi status`/`axi run` subprocess calls at all (in-process cache
  checked first, the shared mixin's idempotency test). A genuinely new
  `idempotency_key` re-checks `axi status` for an already-active run
  before ever spawning (see "Cross-process request() idempotency" above)
  -- best-effort across processes, unlike `AcpExecution`'s airtight
  guarantee, for the structural reason recorded there.
- `inspect()`: pure re-derivation from `axi status --run <id>`, safe to
  call any number of times from any process; a settled observation is
  additionally snapshotted in-process (fast path only, `CONF-ASSURE-002`
  immutability) but the durable answer never depends on that cache being
  warm.

## TOON parsing

`no-mistakes axi`/`axi status`/`axi run` offer no `--format json` (or any
other machine-structured output) flag -- confirmed by reading every
`--help` text on this machine (see "Empirical recon" above). TOON is
genuinely the only surface, so `orc_werk.adapters.no_mistakes.toon.
parse_toon` is a small, purpose-built, tolerant parser for exactly the
shapes this adapter reads (nested `key: value` blocks, `key[N]{col,...}:`
record tables) -- not a general TOON-format implementation. Its known
fragility (reverse-engineered from one CLI version's output, no
schema/version guard, silently tolerates/skips unrecognized lines rather
than erroring) is recorded in the module's own docstring and flagged as a
known-issues row in `docs/playbooks/cli-usage.md`.

## Lossy mappings

- **No line numbers in findings.** `axi status`'s gate `findings` table
  carries `file` but no `start_line`/`end_line` -- `review-findings/v1`'s
  `location` therefore only ever carries `path`, never line numbers. `axi
  logs --step <step> --full` might carry finer-grained detail, but
  reliably parsing arbitrary log prose for line numbers was judged too
  fragile to attempt (the exact category of "ambiguous prose parsing"
  `docs/adapters/no-mistakes/capabilities.md`'s draft already flagged as
  disqualifying).
- **No confidence signal.** Always reported as `medium` (see "Findings
  mapping").
- **No native `agentSessionId`-equivalent identity to resume against.**
  `PORT-ASSURANCE` has no resume concept, so this is moot for this port,
  recorded here only for symmetry with the acp mapping doc's own
  "Lossy mappings" section.
- **Caller-injected `extensions` passthrough is not supported.**
  `inspect()`'s `extensions` are always this adapter's own derived
  `review-findings/v1` (or empty) -- there is no channel for a caller to
  hand it arbitrary opaque data at `request()` time and have it echoed
  back unchanged (exactly `AcpExecution`'s same documented limitation for
  its own `extensions`). This is why
  `test_inspect_transports_scripted_extensions_losslessly` is overridden
  with a documented skip in this adapter's conformance test.

## Limitations

- **Bounded spawn-wait is a strictly weaker signal than acpx's
  `--no-wait` ack.** `acpx`'s `--no-wait` returns a synchronous JSON
  acknowledgement in ~0.2s regardless of turn length -- a real,
  positive confirmation the submission was accepted. `no-mistakes axi
  run` offers no equivalent: this adapter's bounded poll can only ever
  observe "a run id eventually appeared" or "it didn't within the
  timeout" -- an invocation that fails immediately (bad flags, no agent
  configured) is indistinguishable from one that is merely slow to
  register, since the detached process's own exit code/stderr is never
  read. Both surface as `ERR-TEMPORARY` after the timeout.
- **Cross-process `request()` idempotency is best-effort, not airtight**
  (see "Cross-process request() idempotency" above) -- a structural
  consequence of `no-mistakes` assigning opaque run ids with no
  caller-supplied naming hook, unlike `acpx`'s `-s <session-name>`.
- **Stale parked run blocks a retry's `repo_path`.** If a candidate's run
  parks at a gate and this adapter settles `rejected`, the underlying
  `no-mistakes` run itself is left parked (judge-only ruling: this
  adapter never calls `axi respond`/`axi abort`). Per real `no-mistakes`
  behavior observed during recon, a parked run's `branch_sync.safety`
  reads `blocked_pipeline_owned` with the note "a validation run is
  active on this branch; do not make local follow-up commits until it
  finishes." A subsequent `DEC-RETRY` that produces a new candidate
  (new commit) on the same branch/`repo_path` will therefore hit this
  adapter's `ERR-UNSAFE-STATE` guard (see "Cross-process `request()`
  idempotency") rather than silently misbehaving -- but resolving it
  requires a human operator to run `no-mistakes axi abort` (or
  `axi respond`) out-of-band; this adapter deliberately does not
  auto-abort a stale run itself, even one it already rendered a verdict
  on, since that is still a mutating action outside a pure judge's
  remit under the judge-only ruling as scoped for this task. This is the
  single most consequential open question for a future task that wants
  unattended multi-attempt retries through this adapter.
- **`review-findings/v1` category/severity mapping is a best-effort
  heuristic**, not derived from any `no-mistakes`-native vocabulary (see
  "Findings mapping").
- **TOON parsing has no schema/version guard** (see "TOON parsing").
- **The `--skip push` step-name pin has no version guard either** -- a
  future `no-mistakes` release renaming the `push` step would silently
  regress the mechanical never-push guarantee (see "Judge-only ruling"'s
  fail-closed note for the full hazard and the version re-probe
  mitigation).
