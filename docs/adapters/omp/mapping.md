---
id: ADAPTER-OMP-MAPPING
type: adapter-mapping
status: current
authority: informative
description: OMP-concept-to-canonical-concept mapping, and the executor-identity/v1 field mapping OMP-run ship/verify seats use.
---

# OMP mapping

OMP implements no `PORT-EXECUTION`/`PORT-ASSURANCE` operation, so there is
no operation-by-operation table like a real Port adapter's mapping
document. What follows instead is the concept-level correspondence an OMP
seat relies on, and the one canonical surface OMP-run seats actually
touch: the `executor-identity/v1` extension.

## Concept mapping

### Agent definition ↔ seat

An `.omp/agents/<role>.md` file (or `~/.omp/agent/agents/*.md` for a
user-level definition) is OMP's encoding of one seat's role boundary:
frontmatter `model` names the model family/tier the seat runs on (`ADR-
0007`'s `V7` ruling: ship and verify MUST name different provider
families), `tools` bounds its effect surface, and `output` is its result
contract. This is a direct mapping for the *role* concept
(`PLAYBOOK-WATCHTOWER`'s seat table) but not an identity mapping: one
agent *definition* can back many concurrent agent *instances* (subagent
spawns), exactly as one seat *role* in the playbook can be occupied by
many sessions over a run's lifetime. Nothing in an agent definition itself
identifies a specific occupant of the seat for one candidate — that is
what `executor-identity/v1`'s `seat_ref` is for (below).

### Subagent spawn ↔ execution attempt / assurance attempt

A non-isolated `task` spawn (`ADR-0007`'s isolation ruling, option B: the
ship agent creates its own `.worktrees/<branch>` with plain `git` rather
than using OMP `isolated` merge-on-completion) is the OMP-native unit that
occupies one seat for one Work's execution or assurance attempt. This
mapping is **observational, not structural**: OMP's spawn lifecycle
(`running` → `idle` → `parked`/revived, per `task.agentIdleTtlMs`) has no
counterpart in the canonical attempt lifecycle (`FACT-EXEC-STARTED` →
`FACT-EXEC-SETTLED`), and nothing ties an `agent://<id>` or session file to
a `work_id`/`execution_id` except the seat's own `orc record` invocation.
One spawn parked and later revived by a `hub` message is still one seat
recording once, idempotently, for one attempt — the park/revive cycle is
invisible to the ledger and MUST NOT be read as multiple attempts.

### Structured output schema ↔ settlement shape

An OMP agent's `output`/`outputSchema` (`schemaMode: strict`) is OMP's own
result contract for the agent's final `yield` — for example, ship's
`{run_id, work_id, branch, pr, head_sha, gate, not_covered[],
ambiguities[], recorded}` (`TASK-M5-004`). This is **not** the same
artifact as `FACT-EXEC-SETTLED`/`FACT-ASSURE-SETTLED`: the schema
rejection only guards the shape of the agent's yielded JSON. It proves
nothing about whether the agent's body actually called `orc record` with
matching values, or at all, before yielding. Per the 2026-09-07 operator
ruling this gap is closed by the orc ledger's own state machine for the
paths that reach `ACCEPTED`/`BLOCKED` through bound assurance — those
paths never settle unless `orc record` actually ran, whatever an agent's
`yield` claims; the cancellation path is a disclosed, unenforced escape
from that rung (issue #293) — not by a `TASK-M5-005` `tool_call` hook: a
hook can read
the calling agent's own role structurally (`session_init.agent`,
`capabilities.md`'s role-identity finding) but cannot reliably verify
that a prior `bash` call was a genuine `orc record` invocation rather
than a command-text match against a spoofed stub — exactly the guard
`task-m5-005`'s rejected attempt 1 defeated with a command-local `PATH`.
See `capabilities.md`'s named limitation on this gap.

### Session/transcript ↔ evidence ref

An OMP session file (`~/.omp/agent/sessions/<encoded-cwd>/
<timestamp>_<sessionId>.jsonl`) and its `history://<id>` rendering are
OMP's durable transcript. Per `ADR-0007`'s Consequences (a named
deviation from treating it as portable evidence): **this path is
machine-local**, not a portable ledger evidence ref. It is never the
durable carrier of a verdict or settlement — the ledger and the forge PR
(`gh-pr:<n>`, `head:<sha>`) remain the durable, portable evidence
(`PLAYBOOK-AGENT-CLI` §8's reference-first narrative doctrine). A
`session_ref` in an `executor-identity/v1` payload is provenance
pointing at this transcript for a reader with local access to the same
machine; it is not itself resolvable by a stranger the way `gh-pr:<n>` is.

### What OMP can never produce: `execution-session/v1`

`execution-session/v1` (`EXT-EXECUTION-SESSION-V1`) requires an
adapter-managed `PORT-EXECUTION` implementation to journal session/resume/
transcript provenance automatically. OMP is not such an adapter (see
`README.md`), so an OMP-run seat can never legitimately emit
`execution-session/v1` — only `executor-identity/v1`, the external-
executor path `ADR-0005` already established for every non-adapter-driven
seat regardless of harness.

## `executor-identity/v1` field mapping

This is the mapping `PLAYBOOK-AGENT-CLI`'s former §2 prose described in
harness-independent terms; here it is the OMP-specific instance, per
`ADR-0007`'s current→target row: "`session_ref`/`seat_ref` derived from
the OMP session/agent identity; `role` from the agent name."

| Extension field | OMP source | Direct/synthesized |
|---|---|---|
| `model` | The model actually serving the request for that agent instance (visible via `/model` or the session's own `model_change` entries) | **Synthesized, agent-supplied.** Nothing mechanically copies this into the `orc record --model` flag; the agent's own body passes it as free text. It commonly diverges from the agent *definition*'s configured default when a retry/fallback chain substituted another model — this is a legitimate, separately-logged event (`docs/delivery/seat-reliability.md`), not a mapping defect. |
| `session_ref` | The OMP orchestrating session (a human-legible label the agent chooses, e.g. `"omp:watchtower"`, not the raw session-file id) | **Synthesized, agent-supplied.** No hook or extension in this repository's `e102e1e` baseline reads OMP's own session header `id` and injects it; the agent body picks a label at `orc record` time. Distinct seats sharing one orchestrating session (issue #182) still need distinct `seat_ref` values — `session_ref` alone never distinguishes them. |
| `seat_ref` | A per-seat identifier the recording agent chooses, conventionally `<role>-<work_id>-<sha7-of-candidate-head>` | **Synthesized, agent-supplied**, but conventionally stable and reproducible: two record attempts for the same seat/candidate pairing naturally produce the same value without coordination. |
| `role` | The agent definition's own `name` (`ship`/`verify`) | **Agent-supplied, not mechanically verified by this recording path.** A hook/extension *can* learn the running agent's name structurally (`ctx.sessionManager.getEntries()` → `session_init.agent`, `TASK-M5-001`'s corrected role-identity finding, `capabilities.md`), but nothing in this repository's `e102e1e` baseline wires that read into populating this field automatically — `role` is correct here only because each agent definition's own body is written to always pass its own literal role string to `orc record`. |

None of these four fields is read from OMP by any mechanism in this
repository's `e102e1e` baseline —
every one is text the recording agent supplies to `orc record`'s
`--model`/`--session-ref`/`--seat-ref` flags (or the equivalent
config-entry `extensions` payload) exactly as `PLAYBOOK-AGENT-CLI` already
required before OMP existed. What OMP changes is *which convention* an
agent follows (its own frontmatter `model:`, a `seat-<role>-<sha7>`
naming discipline) — never a new mechanical extraction path. A future
`TASK-M5-005`-style hook that reads OMP's own role/session identity and
auto-populates these fields would upgrade this row from agent-supplied to
adapter-derived; no such mechanism exists in this repository's `e102e1e` baseline.

### Impossible mappings

- OMP has no concept corresponding to canonical assurance/execution
  identity (`Candidate`, `AssuranceRun`) at all — a spawn's `agent://<id>`
  is never itself a candidate or assurance identity, and nothing maps one
  to the other except the recording agent's own `orc record` call.
- OMP cannot express `execution-session/v1` (see above).

### Canonical error translation

None. OMP contributes no new error-translation surface: an OMP-run seat
calling `orc record` hits the exact same `ERR-VALIDATION`/`ERR-CONFLICT`/
exit-code contract any other invoker of the CLI would (`PLAYBOOK-CLI-
USAGE`). There is no OMP-specific failure mode this mapping introduces.

### Idempotency behavior

Inherited unchanged from the `orc record` verb itself
(`PLAYBOOK-AGENT-CLI` §5): repeating the same seat's recording call is a
merge-only, idempotent config update regardless of which harness invoked
it. The one OMP-specific wrinkle is at the harness level, not the ledger
level: a single logical seat's OMP subagent may be parked and revived
(`task.agentIdleTtlMs`) one or more times before it records — that
lifecycle churn is invisible to, and has no effect on, the recording
call's idempotency.

## Merge-frontier discovery: `scripts/watch_pr.py`

`ADR-0007` keeps `scripts/watch_pr.py` unchanged as a policy lever, not
ceremony this migration retires (`ADR-0007`'s "`scripts/watch_pr.py` is
kept" section). It was untouched by the `TASK-M5-002` playbook shrink;
only its own Conventions line in `PLAYBOOK-WATCHTOWER` was *deleted*, not
moved, because that shrink was scoped to the convention *prose*, never
the tool. Restoring its discoverability here (issue #282) documents the
installed script as it exists, grounded in its own `--help` output and
`classify()`/`classify_verdict()` source on this repo's current `master`
— it changes nothing about the tool itself.

`watch_pr.py [PR...] [--repo OWNER/NAME] [--watch] [--interval SECS]
[--verified-sha SHA]` is a read-only GitHub PR merge-frontier watcher: no
invocation mutates GitHub or the local repository. `classify()` evaluates
top to bottom, first match wins — the blocker order is:

1. `MERGED`/`CLOSED` — terminal.
2. `CONFLICTS` — the branch has merge conflicts.
3. `UNRESOLVED-THREADS` — one or more unresolved review threads.
4. `CI-FAILING` — the status-check rollup contains a failed check.
5. `MERGE-GATE` — draft, or changes requested.
6. `CI-PENDING` — status checks still running, or the platform has not
   yet computed a merge state.
7. `NEEDS-UPDATE-BRANCH` — the branch is behind base (`gh pr
   update-branch` is the fix).
8. `READY` — the platform reports the PR mergeable.

`--verified-sha SHA` binds the watcher to the sha an assurance verdict
judged, per `PLAYBOOK-WATCHTOWER`'s "a verdict is stale the moment the
head moves" rule: `classify_verdict()` compares `git patch-id --stable`
between the verified sha and the PR's current head (both diffed against
`master`) and reports the ordinary classification unmodified if the shas
match exactly, `REBASED` folded into that classification's own reason
(verdict carries — content is identical despite a different sha),
`STALE-VERDICT` overriding it (content drift — re-verify), or
`INDETERMINATE` overriding it if either commit is not locally reachable.
Full exit-code-to-classification mapping is the script's own module
docstring (`EXIT_CODES`), not restated here to avoid a second copy
drifting from the source.

## Related

- `ADR-0007`, `ADR-0005`
- `EXT-EXECUTOR-IDENTITY-V1`, `EXT-EXECUTION-SESSION-V1`
- `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`)
- `docs/delivery/watchtower-operations.md` (`PLAYBOOK-WATCHTOWER`) —
  merge pipeline step 5, `scripts/watch_pr.py`'s own home
- `docs/delivery/seat-reliability.md`
