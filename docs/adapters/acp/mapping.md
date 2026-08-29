---
id: ADAPTER-ACP-MAPPING
type: adapter-mapping
status: current
authority: informative
description: acpx-to-ExecutionPort mapping for AcpExecution (TASK-M1-005).
---

# ACP/acpx mapping

Implemented by `src/orc_werk/adapters/acp/execution.py` (`AcpExecution`), driving Pi (`acpx pi`) as the first configured agent. All content here is adapter/provider vocabulary per `INV-014` and `docs/adapters/README.md` — none of it belongs in `docs/contracts/` or `src/orc_werk/core`.

## Version pins

- `acpx@0.13.1` (Node runtime via Volta, node `24.14.0` at implementation time) — `AcpExecution.ACPX_VERSION_PIN`.
- `pi-acp@0.0.31` (resolved via `npx pi-acp@^0.0.31`) — `AcpExecution.PI_ACP_VERSION_PIN`.
- Node is an accepted M1b-only, adapter-local dependency (operator-confirmed, `docs/delivery/task-cards/TASK-M1-005-acp-adapter.md`'s ruling section). `src/orc_werk/core` remains stdlib-only and unaffected — this adapter lives entirely under `src/orc_werk/adapters/acp/`.
- These pins are informative (recorded for reproducibility/debugging), not enforced at runtime: the adapter shells out to whatever `acpx` is on `PATH`.

## Design decisions

### Poll model: `start()` never blocks; `inspect()` is the sole settlement authority

`start()` submits the prompt with `acpx ... pi -s <name> --no-wait "<prompt>"` and returns immediately once `acpx` acknowledges `{"action":"prompt_queued",...}` (confirmed empirically: this call returns in ~0.2s regardless of turn length, queuing the prompt onto the session's `__queue-owner` daemon). It never waits for the turn to complete.

This is a deliberate choice over the spike's alternative "recommended pattern" (foreground `pi -s <name> "<prompt>"`, blocking until the terminal NDJSON line). The orchestrator's poll model (`PORT-EXEC-001` returns a stable ref; `PORT-EXEC-002` is polled separately, potentially from a different process after a restart) wants `start()` to be cheap and non-blocking:

- A blocking `start()` ties up the calling (orchestrator) process for the duration of a potentially long-running turn, with no way to journal `FACT-EXEC-STARTED` and move on to other Work in the meantime.
- The spike already proved that "my submitting process died" does not mean "the turn is unobservable" — the `__queue-owner` daemon outlives the CLI invocation that queued the prompt. `--no-wait` makes this the *only* code path: there is no separate "I was foreground and still connected" fast path to keep in sync with the crash-recovery path. `inspect()` always reconnects via `sessions show` + the raw stream, whether it is the tenth poll in the same process or the first poll after an orchestrator restart.
- This matches `STATE-DELIVERY` mechanical fact sequencing item 7 (absence of a settlement observation is not a settlement): `start()` succeeding just means the attempt started; the Work rests at `EXECUTING` until `inspect()` observes a real outcome.

### Settlement source: `stopReason` in the raw stream, never `status`/`sessions show`'s liveness fields

Per the card and the spike, `inspect()` never derives settlement from `acpx status`/`sessions show`'s process-liveness fields (`status`, `lastAgentExitCode` when used as a *positive* signal, `pid`, etc.) — those describe the daemon/host, not turn outcome, and `running` was proven to persist 70+s after a turn actually completed.

**Confirmed empirically during this task** (beyond what the spike already established) and a **new footgun**: `sessions history` and `sessions read` — the "cheap, rendered" option the spike suggested trying first — render `{role, timestamp, textPreview}` entries only. Across every probe run in this task (fresh sessions, single-turn, `--no-wait`, multi-turn), **`stopReason` never appears in `history`/`read` output at all**, not even indirectly. The raw event-log stream (`sessions show`'s `eventLog.active_path`) is therefore not a fallback for when history is "insufficient" — it is the *only* source `AcpExecution` has for this field. `AcpExecution.inspect()` always reads the stream directly; it does not call `sessions history` at all.

The stream-scan (`_scan_stream_terminal_results`) looks for any line shaped `{"id": <int>, "result": {"stopReason": "..."}}` — this incidentally also skips `session/load`'s result line (id `1`, no `stopReason` key) and any `session/update` notifications (no `id` key), so it needs no id-range assumption.

### Multi-turn correlation (`send`, `CAP-EXEC-SEND`)

A session can carry multiple turns (`start()` submits the first; `send()` appends follow-ups to the same session). The stream is append-only, so "the last terminal-result line in the file" is only the *current* turn's result when no newer, not-yet-materialized turn is outstanding — otherwise it would misreport a stale prior turn's result as if it were the latest.

`AcpExecution` tracks, **in-process only**, how many turns it itself has submitted per `execution_id` (`_submitted_turns`). When that count is known (the same instance did every `start()`/`send()`), `inspect()` requires at least that many terminal-result lines before considering the *specific* (Nth) one settled. When it is *not* known — a fresh instance in a different process, which is exactly the crash-recovery case the card cares about — `inspect()` falls back to "at least one terminal result exists, use the last one." This fallback is correct for that case by construction: Execution↔session identity is 1:1, and a lost-process scenario has exactly one outstanding turn (the process that died was the sole submitter of it).

**Known limitation, documented rather than solved**: if a *different* process calls `send()` on a session that already has turns in flight from elsewhere (multiple concurrent submitters to one session), a fresh `inspect()` cannot distinguish "my new turn hasn't settled yet" from "an earlier turn already settled" — it will report the latest recorded result, which may not be the turn the caller most recently submitted. This is out of scope for M1b (one orchestrator, one submitter per session in practice) and is not exercised by the conformance/unit tests; a future task that needs durable cross-process turn correlation would need `acpx`-side request-id tracking that does not currently exist for Pi (see Open questions in the spike report).

### Unobservability determination

Exactly the spike's "Determining unobservability" procedure, implemented in `AcpExecution._daemon_confirmed_dead`:

1. Reconnect first: `sessions show <name>` is always called before any unobservability conclusion — this is also the same call `inspect()` uses for the ordinary settled/running determination, so there is no separate "recovery mode."
2. Settle `failed` **only** when both of these hold: no terminal `stopReason` has been recorded for the outstanding turn (per the correlation rule above), **and** the daemon is confirmed dead — `sessions show`'s `lastAgentExitCode` is a real `int` (not absent, not `null`), **or** `acpx pi status -s <name>` reports `status == "dead"` literally.
3. **Never a timeout.** There is no wall-clock/retry-count path to `failed` anywhere in `inspect()`.

**Deliberately excluded from the "dead" determination**: `acpx pi status`'s `"no-session"` value. Empirically (this task's own probing, not just the spike), a brand-new session returns `"no-session"` from `pi status` in the narrow window before its queue owner has actually spawned — treating that as "dead" would misclassify a perfectly healthy, just-started turn as unobservable. Only a literal `"dead"` status counts. This is a conservative choice (favor reporting `running` over a false `failed`) consistent with the ruling's "never a timeout" spirit: when genuinely ambiguous, wait for another observation rather than guess.

The true "daemon died with a turn genuinely outstanding" branch is not reproducible against live `acpx` on demand (the spike's own open question #2) — it is regression-tested exclusively via the stub-`acpx` harness (`tests/conformance/support_acpx_stub.py`, `AcpxStubWorld.mark_daemon_dead`), per the task card's acceptance item.

### Session naming and `execution_id` shape

`session_name = "orcw-" + sha256(idempotency_key)[:24]` (`session_name_for_idempotency_key`, exported so a test harness can predict names without duplicating the hash scheme) — deterministic, CLI-safe, never randomness/wall-clock time (`INV-020`, `CONF-EXEC-001`).

`execution_id = f"acpx-{agent}:{session_name}:{work_id}"` — `work_id` is embedded in plaintext (not hashed) specifically so `resume()`/`inspect()`/`send()`/`cancel()` can recover both the session name *and* the originating `work_id` from `execution_id` alone, with zero adapter-instance state, in a fresh process. `session_name` is always a fixed-width hex string (never contains `:`), so `execution_id.split(":", 2)` unambiguously recovers `(agent, session_name, work_id)` even if `work_id` itself contains `:`.

### `attempt_number` is best-effort, in-process only

`Execution.attempt_number` (returned by `start()`/`resume()`) is tracked via a simple per-`work_id` in-process counter — the same shape `ScriptedExecution` uses, needed only to satisfy `CONF-EXEC-002`'s "a genuinely new idempotency key advances attempt_number" expectation. This is honest bookkeeping, not durable state: per `INV-018`, the canonical source of truth for `attempt_number` is the orchestrator's own journal (count of execution-start records), which the current `orc_werk.app.orchestrator` does not read back from the adapter's returned `Execution` at all (confirmed by inspection: only `execution.id` is consumed). A `resume()` call on a fresh adapter instance that never observed the original `start()` returns `attempt_number=1` as a documented placeholder.

## Operation mapping

| Canonical concept/operation | Provider concept | Mapping |
|---|---|---|
| `PORT-EXEC-001 start` | `acpx <flags> <agent> sessions ensure -s <name>`, then `acpx <flags> <agent> sessions show <name>` (cross-process idempotency check and model discovery), then — only if not already prompted — `acpx <flags> --json-strict <agent> -s <name> --no-wait "<prompt>"` | `ensure` (never `new`) for idempotent create-or-attach; the `show` call's `lastPromptAt`/`messages` decide whether to skip straight to returning the stable ref (see "`start()` is idempotent across processes" below) or proceed. When proceeding, a requested `model` must exactly match an `acpx.available_models` id or resolve to exactly one case-insensitive substring match; zero or multiple matches fail closed with `ERR-VALIDATION` listing every advertised id. The resolved id is pinned via `acpx <agent> set model <resolved-id> -s <name>` before the prompt; failure to set it aborts start. `thought_level` is pinned separately before the prompt. Returns `Execution(id=execution_id, work_id, attempt_number)` either way. |
| `PORT-EXEC-002 inspect` | `acpx <flags> <agent> sessions show <name>` + raw `eventLog.active_path` stream scan; `acpx <flags> <agent> status -s <name>` only when checking for daemon death | `stopReason` absent anywhere in the stream and daemon alive/ambiguous → `state=running`; `stopReason` present (for the correlated turn) → `state=settled`, `outcome` per the stopReason table below; no `stopReason` and daemon confirmed dead → `state=settled, outcome=failed` (unobservability). |
| `PORT-EXEC-003 send` (`CAP-EXEC-SEND`) | `acpx <flags> --json-strict <agent> -s <name> --no-wait "<prompt>"` | Same non-blocking submit as `start()`'s prompt step, same session. `message['prompt']` preferred; `message['text']` accepted as an alias (generic-caller compatibility — `PORT-EXEC-003`'s doc exemplar uses `{"text": ...}`). |
| `PORT-EXEC-004 cancel` (`CAP-EXEC-CANCEL`) | `acpx <flags> <agent> cancel -s <name>` | Cooperative; always followed by an internal `inspect()` post-verification call (footgun: exit 0 alone does not prove a cancellation happened). |
| `PORT-EXEC-005 resume` | `acpx <flags> <agent> sessions show <name>` (existence check only) | `capability=CAP-EXEC-RESUME-BEST-EFFORT`: confirms the session record still exists, returns the same `execution_id`. `capability=CAP-EXEC-RESUME-EXACT`: always `ERR-UNSUPPORTED-CAPABILITY` — never advertised (see Capability honesty). |

### `stopReason` → canonical `outcome`

| `stopReason` (observed in the raw stream `result.stopReason`) | Canonical `outcome` |
|---|---|
| `end_turn` | `completed` |
| `cancelled` | `cancelled` |
| anything else (unmapped/unknown value, including refusal-shaped stop reasons) | `failed` |

The catch-all-to-`failed` mapping is deliberate, not an oversight: it is the mechanism that satisfies the footgun "permission-denied runs can exit looking successful ... MUST map to canonical failure, not success" — this adapter never special-cases a stopReason as `completed` unless it is exactly `end_turn`.

## `execution_request` / `message` shape (adapter-owned, opaque to the core)

```python
# start()
{"prompt": "<required, non-empty>", "model": "<optional opaque model id>"}
# send()
{"prompt": "<required, non-empty>"}  # or {"text": "..."} as an alias
```

`PORT-EXEC-001`/`PORT-EXEC-003` declare these mappings opaque to the core; this shape is this adapter's own invention, recorded here per `docs/adapters/README.md`'s mapping-doc requirement, not a canonical contract.

## `execution-session/v1` provenance

Emitted on every settled `inspect()` observation's `extensions`:

- `provider`: `"acpx-<agent>"` (e.g. `"acpx-pi"`) — opaque per `INV-014`; swapping `agent="claude"` changes only this string, no adapter code.
- `native_session_id`: `sessions show`'s `acpxRecordId` (equivalently `acpSessionId` — confirmed identical in every session observed in this task, matching the spike's finding; the adapter never assumes they diverge). There is no native `agentSessionId` to prefer instead — confirmed absent in every probe this task ran, consistent with the spike's SPIKE 2 finding for `pi-acp@0.0.31`.
- `resume.strength`: always `"best-effort"` — `acpx` never calls `session/resume` for Pi, only `session/load` (spike SPIKE 2b, and this task's own wire-trace probing reproduced the identical pattern: `id:1 session/load` on every session, first turn or reconnect, never `session/new`/`session/resume`). `resume.ref` is the `session_name` — the exact string `resume()`'s own implementation needs.
- `transcript_ref`: `eventLog.active_path` — the stable, independently-readable stream file path. Ref-only, never dereferenced/inlined by this adapter (`EXT-EXECUTION-SESSION-V1-SEMANTICS`'s "never inlined" rule).
- `profile.model`: `sessions show`'s `acpx.current_model_id`, when present.
- `profile.effort`: the adapter's own pinned `thought_level` value (e.g. `"low"`), when pinning is enabled.
- Unobservability-determined `failed` settlements add no adapter-local marker to this payload. In particular, the former `_orcw_unobservable` key was removed by issue #45 because nothing outside this adapter's own test consumed it and settlement metadata does not belong inside the session-provenance extension.

## Capability honesty

| Capability | Advertised | Proving basis |
|---|---|---|
| `CAP-EXEC-SEND` | Yes | `send()` submits a real follow-up turn on the same session; exercised by conformance. |
| `CAP-EXEC-CANCEL` | Yes | `cancel()` + mandatory post-verification via `inspect()`; exercised by conformance and the dedicated cancel unit tests. |
| `CAP-EXEC-RESUME-BEST-EFFORT` | Yes | `resume()` confirms session existence and returns the stable ref; the spike's real daemon-kill-and-reconnect test (SPIKE 2b) already proved `session/load` preserves transcript and identity for Pi. |
| `CAP-EXEC-STRUCTURED-LIFECYCLE` | Yes | `--format json --json-strict` NDJSON throughout; `AcpExecution` never parses free text to determine outcome. |
| `CAP-EXEC-RESUME-EXACT` | **No — withheld unconditionally** | `AcpExecution.__init__` raises `ValueError` if constructed with this capability requested, per the `CONTRACT-CAPABILITIES` capability-durability rule. |

**Withholding `CAP-EXEC-RESUME-EXACT` — the proving condition and why it fails today.** The task card records the future proving condition: (1) a native `agentSessionId` id-comparison guard, and (2) durable `execution-session/v1` provenance. This adapter satisfies (2) (see above) but not (1): no native `agentSessionId` — or any provider-native id distinct from acpx's own generated id — was found anywhere in this task's own probing (`sessions show` JSON, the raw stream's `_meta` payloads), reproducing the spike's SPIKE 2 finding exactly. There is no id to compare against, so proving-condition (1) is unmeetable for `pi-acp@0.0.31`, not merely unproven. Should a future `pi-acp` version add a real `agentSessionId`, this becomes a version-gated re-evaluation, not a code change to how withholding works.

## Lossy mappings

- **Caller-injected `artifact_refs`/`extensions` passthrough is not supported.** `PORT-EXEC-002`'s `extensions` on a settled observation are always this adapter's own derived `execution-session/v1` provenance — there is no channel for a caller to hand the adapter arbitrary opaque data at `start()`/`send()` time and have it echoed back unchanged on `inspect()`. (This is the reason `tests/conformance/test_acp_execution_conformance.py` documents a skip for the shared mixin's `test_inspect_transports_scripted_artifact_refs_and_extensions_losslessly` — that test is inherently a scripted-test-double behavior, not something a real provider-driving adapter can offer.)
- **`artifact_refs` on `ExecutionObservation` is always empty.** `acpx pi` over ACP does not surface artifact references distinct from the transcript itself; there is nothing honest to put there.
- **No subagent/tool-call visibility.** Unchanged from `PORT-EXECUTION`'s explicit non-semantics — this adapter does not attempt to surface anything beyond `stopReason` and session provenance.
- **`sessions history`/`sessions read` are unused entirely.** Despite being the spike's suggested "cheap" first check, they carry no `stopReason` (see Design decisions above); using them would add a subprocess call with no informational value for this adapter's purposes.

## Synthesized fields

- `execution_id`, `session_name` — synthesized deterministically from the idempotency key and `work_id` (Design decisions above); acpx has no equivalent concept until `sessions ensure` actually creates a record.
- `attempt_number` — synthesized, in-process, best-effort (Design decisions above).

## Impossible mappings

- `CAP-EXEC-RESUME-EXACT` (see Capability honesty).
- A durable, cross-process "which turn did I most recently submit" correlation beyond "the latest recorded result" (see Design decisions, multi-turn correlation limitation).

## Canonical error translation

| `acpx` condition | Canonical error |
|---|---|
| `acpx` binary not found on `PATH`, or fails to exec | `ERR-PROVIDER-UNAVAILABLE` |
| Non-zero exit whose stderr matches the usage-error shape (`error: unknown option`/usage banner) at **either** exit `1` or exit `2` (footgun: subcommand-level usage errors exit `1`, not the documented `2` — exit code alone is never trusted) | `ERR-UNSAFE-STATE` (unknown whether the malformed invocation had side effects, so not safely retryable as-is) |
| Exit `4` ("no session found") | `ERR-NOT-FOUND` |
| Any other non-zero exit | `ERR-TEMPORARY` (default posture: may succeed on retry) |
| `--format json` invocation produced non-JSON stdout | `ERR-UNSAFE-STATE` |
| `execution_request['prompt']` (or `send()`'s `message['prompt']`/`['text']`) missing/empty/non-string | `ERR-VALIDATION` |
| `resume_request['capability']` missing/unknown, or names a strength this instance does not advertise | `ERR-VALIDATION` / `ERR-UNSUPPORTED-CAPABILITY` respectively (`PORT-EXEC-005`'s ambiguity rule; `INV-013`) |
| Malformed/unrecognizable `execution_id` on `inspect`/`send`/`cancel`/`resume` | `ERR-NOT-FOUND` |

## Idempotency behavior

- `start()`: same idempotency key → same cached `Execution`, no repeat `acpx` subprocess calls at all (in-process cache checked first). A genuinely new idempotency key for the same `work_id` runs `sessions ensure` again — which is itself idempotent at the `acpx` layer (`(created)`/`(existing)`, confirmed identical `acpxRecordId` across repeated `ensure` calls in this task's own probing) — against a *new*, deterministically different session name (new attempt = new execution identity, per `INV-004` and the task card's abandonment ruling).
- `send()`/`cancel()`: not separately idempotency-keyed by this adapter (`PORT-EXEC-003`/`004` do not carry an idempotency key parameter); `cancel()`'s own idempotency is `acpx`'s cooperative-cancel behavior (exit 0 whether or not there was anything to cancel), which is why post-verification is mandatory rather than optional.

### `start()` is idempotent across processes (issue #57)

The in-process cache above is only a fast path, not the correctness mechanism: `Orchestrator._reconcile_ports` replays every historical `FX-START-EXECUTION` effect by calling `ExecutionPort.start()` again — with the *same* idempotency key — on **every** fresh `orc dispatch` process, including an ordinary re-poll of a still-running attempt, not just genuine crash recovery. A fresh `AcpExecution` instance has an empty cache, so before this fix it unconditionally re-ran `sessions ensure` and resubmitted the prompt every time, queuing a duplicate turn per poll.

**Fix**: after `sessions ensure`, `start()` calls `sessions show` and consults the session's own durable record via `_session_already_prompted(show)` *before* touching the prompt at all. Because `session_name` is a deterministic 1:1 function of the idempotency key (`session_name_for_idempotency_key`), "this session has ever seen a prompt" is exactly "this attempt's submit step already ran once, in this process or a prior one" — there is no other submitter that could have produced that signal for this session.

**Durable signal chosen, and why**: `sessions show`'s `lastPromptAt` (non-null after the first prompt, `null` before) as the primary signal, with `messages` (non-empty after the first prompt, `[]` before) as an independent corroborating check — either being truthy is sufficient. Both were confirmed by direct probing against real `acpx@0.13.1`/`pi-acp@0.0.31` (not merely the stub): a freshly-`ensure`d session shows `lastPromptAt: null, messages: []`; immediately after `-s <name> --no-wait "<prompt>"` returns `{"action":"prompt_queued",...}` — *before* the turn settles — the very next `sessions show` already reports a set `lastPromptAt` and a `messages` entry for the submitted turn. This is a **submission** signal, not a completion signal: it is set exactly once, at queue time, and never cleared or updated again for that turn, which is what makes it safe to treat as "do not resubmit" regardless of whether the turn is still running or has already settled — `inspect()`'s `stopReason` scan remains the sole settlement authority either way (edge cases (a) and (b) below are identical from `start()`'s point of view). Checked as presence only, per `CONF-EXEC-001`'s no-wall-clock spirit: `start()` never parses or compares the `lastPromptAt` *value*, only whether the field is set.

**Edge cases** (`docs/reports/2026-08-28-acpx-pi-spike.md`-style probing, this task):

| Case | Durable state after `sessions ensure` | `start()` behavior |
|---|---|---|
| (a) Session exists, prompt already submitted, still running | `lastPromptAt` set, no terminal `stopReason` yet in the stream | No resubmit; returns the same stable `Execution` ref. `inspect()` will report `running` until it observes settlement. |
| (b) Session exists, turn already completed | `lastPromptAt` set, terminal `stopReason` recorded in the stream | No resubmit; returns the same ref. `inspect()` settles from the stream, as always. |
| (c) Session created fresh by this call | `lastPromptAt` null, `messages` empty | Validates `execution_request['prompt']`, submits once, records `_submitted_turns` for this instance. |
| (d) Session exists (a prior process ran `sessions ensure`) but crashed before ever submitting | `lastPromptAt` null, `messages` empty — indistinguishable from (c) | Submits once — this is the legitimate replay case per the task card's crash-recovery ruling; distinguished from (a)/(b) purely by the durable null/empty signal, never by in-process memory (which would be empty in both (a)-through-(d) for a fresh process regardless). |

**Failure modes of this signal, recorded honestly**:

- **Field-name drift across `acpx` versions.** `lastPromptAt` and `messages` are this adapter's own probed-and-pinned choice for `acpx@0.13.1`/`pi-acp@0.0.31` (`ACPX_VERSION_PIN`/`PI_ACP_VERSION_PIN`); an upgrade that renames or removes either field without a compatible replacement would make `_session_already_prompted` silently fall back to "never already prompted," i.e. **regress to the pre-fix resubmission behavior**, not fail loudly. There is no schema-version guard on `sessions show`'s JSON today (`acpx.session.v1`'s `schema` field is read nowhere in this adapter) to detect this at runtime; a version bump to either pin should re-probe this shape before merging, the same discipline the rest of this mapping doc already asks for.
- **Multiple submitters to one session** (the pre-existing "Known limitation" in the multi-turn correlation section above): if a caller other than `start()` — e.g. a concurrent `send()` from a different process — queues a prompt onto this session between `sessions ensure` and this check, `start()` would see `lastPromptAt` set and (correctly, by this adapter's design) treat it as "already started," even though the actual submitter was a `send()`, not this `start()` call. Out of scope for M1b's one-orchestrator-one-submitter-per-session model, same as the existing multi-turn limitation.
- **Stub vs. real timing**: the stub (`tests/conformance/support_acpx_stub.py`) sets its own `last_prompt_at`/`messages` fields synchronously inside the same fake-CLI-process call that increments `turns_submitted`, so the stub-harness tests below cannot exercise a real async gap between "prompt accepted for queuing" and "durably recorded" the way live `acpx`'s daemon architecture could in principle produce one; live-`acpx` probing (this task) did not observe such a gap (the very next `sessions show` after `--no-wait` returns already reflects the new state), but it was not adversarially stressed (e.g. `sessions show` called concurrently with the queuing subprocess).

## Footguns (operational hazards — code and reviewers must not relearn these)

From the task card, all honored by this implementation:

1. Always pass explicit `-s <session-name>` — never an implicit/default session. (`_base_argv`/every subcommand call.)
2. `sessions ensure`, never `sessions new`, for session start, on every attempt including retries.
3. A `cancel` call that exits `0` may mean "nothing to cancel" — `cancel()` always post-verifies via `inspect()`.
4. Permission-denied runs can exit looking successful (process exit 0) while no actual work occurred — the `stopReason`-only outcome mapping (catch-all → `failed`) is the structural fix; this adapter does not treat any non-`end_turn` stopReason as success regardless of exit code.
5. `--approve-all` is a documented security stance, not a default. This adapter's default is fail-closed (`--non-interactive-permissions deny`); `--approve-all` is opt-in only via `AcpExecution(approve_all=True)` at construction time — never a per-request override, and never silently enabled.
6. `acpx status` values of `idle`/`dead`/**`running`** (widened per the spike) describe host/process state, never canonical settlement — settlement comes only from `result.stopReason` in the raw stream.

From the spike, all honored:

7. Global/output flags (`--format`, `--json-strict`, `--cwd`, `--approve-all`/`--non-interactive-permissions`) precede the agent subcommand (`_base_argv` always builds them before appending the agent token).
8. Exit `1` **and** `2` are both treated as possible usage errors; stderr shape (`error: unknown option`/usage banner) is always inspected, never exit code alone (`_AcpxInvocationError.looks_like_usage_error`).
9. `thought_level` is pinned explicitly (default `"low"`) on every `start()`, via `acpx <agent> set thought_level <value> -s <name>` — never left to the agent's own default. Its `set` failures remain a soft no-op. Model pins are different: the requested value is first resolved against `sessions show`'s advertised ids, ambiguity or absence fails closed, and failure of `set model <resolved-id>` aborts `start()` so the session default can never silently substitute for a requested model.

New, confirmed by this task's own probing (folded into the mapping doc per the card's rule 6/7):

10. `sessions history`/`sessions read` never carry `stopReason` in any observed shape — not a fallback source, the raw stream is the only source (see Design decisions).
11. `acpxRecordId` and `acpSessionId` (or `acpxSessionId`, depending on which subcommand's output you read — `ensure`/`set` use `acpxSessionId`, `show` uses `acpSessionId`; same value, inconsistent field name across subcommands) are always identical for Pi; this adapter never assumes they could diverge.
12. `acpx pi status`'s `"no-session"` value must **not** be treated as "daemon dead" — it is also returned for a session that has not yet spawned a queue owner (e.g. immediately after `ensure`, before any prompt). Only a literal `"dead"` status counts toward the unobservability determination.
13. `sessions ensure`'s and `sessions show`'s JSON output must be requested with `--format json` placed before the agent subcommand, exactly like every other invocation — confirmed by reproducing the spike's flag-placement footgun directly (`acpx pi sessions show <name> --format json` → `unknown option`).

## Provider swap (`P-001` demonstration)

`AcpExecution(agent="claude")` drives Claude Code through the identical code path — no method in this file branches on the configured agent string except to build the CLI argv/labels. This is untested live in this task (out of scope — Pi is the only agent exercised, per the card), but the design constraint ("adapter is agent-agnostic at the protocol layer... swapping the configured agent MUST require no adapter code change") is structurally satisfied: every `acpx` invocation goes through `_base_argv()`, which inserts `self._agent` as the only agent-specific token.

## Crew-report durable-ownership question — resolved by removal

This section originally recorded that this task did not resolve the standing `crew-report/v1` durable-ownership question: `AcpExecution` does not journal execution reports itself — the app/orchestrator layer is the only component that translates this adapter's observations into journaled facts — and that remained a deferred-decision ledger entry. The question is now resolved, not by this adapter, but by the reference-first narrative doctrine (operator ruling, issue #100 part 2, amending issue #65): `crew-report/v1` is removed entirely (`EXT-CREW-REPORT-V1`, superseded), and this adapter already journals the reference-first replacement natively — its own `execution-session/v1` session/resume/transcript provenance on `FACT-EXEC-SETTLED` (see "Provider swap" above and `docs/extensions/execution-session/`), surfaced read-only via `orc refs`. No further adapter change was needed to close this gate; `AcpExecution` still does not, and does not need to, journal execution reports itself.
