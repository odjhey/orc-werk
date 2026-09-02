---
id: REPORT-2026-08-28-ACPX-PI-SPIKE
type: report
status: archived
authority: informative
description: M1b spike report — acpx driving Pi as the PORT-EXECUTION target (crash-mid-turn observability, native agentSessionId presence).
---

> **Archived** (operator ruling ADR-0005, issue #214, ruling A4). The `acp` `ExecutionPort` adapter this spike investigated was removed in 0.5.0. Retained as historical/archived context; informative, not normative.

# M1b spike report — `acpx pi` as the `PORT-EXECUTION` target

## Provenance

- Produced by a spike crew tasked against `TASK-M1-005`'s two open spike questions (crash-mid-turn observability, and Pi ACP adapter session-id maturity).
- Accepted in the delivery ledger, run `task-m1b-spike`.
- Report content sha256: `3ee42c90d15f8909abfbfe5513cd02d2cb958046d7930a5fe8082e334ef64e1b`.
- Exercised against `acpx@0.13.1` (Node runtime via Volta, node `24.14.0`) driving `pi-acp@0.0.31`.
- Findings below are reproduced as accepted, with only light formatting applied for `docs/reports/` house style; no claims, numbers, or conclusions were altered from the accepted report.

## Spike setup

- acpx: `0.13.1` (Node runtime via Volta, node 24.14.0)
- agent: `pi` → resolved adapter command `npx pi-acp@^0.0.31`, agentInfo `{"name":"pi-acp","title":"pi ACP adapter","version":"0.0.31"}`
- All sessions run with `--cwd /private/tmp/claude-501/-Users-odz-proj-orc-werk/87be9426-f7d1-46b5-9854-0bfb78dba727/scratchpad/acpx-spike` (never the orc-werk repo)
- Session names: `spike-e1`, `spike-e4a`, `spike-e4b`, `spike-e5`, `spike-e6` — all closed at end of spike (`acpx pi sessions close <name>`); the operator's pre-existing `test-pi-acpx`/`test-ensure` sessions (scoped to `/Users/odz/proj/orc-werk`) were left untouched.
- Upstream docs consulted (WebFetch of `github.com/openclaw/acpx` docs/*.md): `sessions.md`, `session-control.md`, `exit-codes.md`, `output-formats.md`.

---

## Verdicts

### SPIKE 1a — turn-result persistence

**RULED / CONFIRMED.** A completed turn's final content and `stopReason` are durably recoverable through both `acpx pi sessions history` (rendered) and the raw `~/.acpx/sessions/<id>.stream.ndjson` event log (wire-level JSON-RPC, including the terminating `{"id":N,"result":{"stopReason":"end_turn"}}` line). This holds even when read from a process that did not submit the turn.

### SPIKE 1b — crash-mid-turn observability

**RULED / CONFIRMED for the queue-owner-survives branch**, which is acpx's actual architecture and the common case: `acpx pi <prompt>` (no `--no-wait`) detaches a long-lived `__queue-owner` daemon process (`acpx ... __queue-owner`, itself parenting `npm exec pi-acp` → `node pi-acp` → `pi --mode rpc`) that is independent of the CLI/foreground process the caller invoked. Killing the *foreground submitter* (`timeout 2 acpx pi -s <name> '<prompt>'`, client killed via SIGTERM/SIGKILL after 2s, well before the model finished) does **not** kill the queue owner. Verified twice (`spike-e4a`, `spike-e4b`): in both runs the submitting process was reaped at 2s (`exit 124` from `timeout`), yet 30–70s later the session's stream file and `sessions history` showed the completed turn with `stopReason:"end_turn"` and the full generated text, with `lastAgentExitCode/ExitSignal/DisconnectReason` all still `null` (the agent process never actually exited — it was just sitting inside its TTL window, default 300s).

**Not exercised (out of scope per the operator's ruling in the task card):** the *queue-owner-also-dies* branch — i.e. true unobservability. The task card's ruling (2026-08-28) already settles that branch normatively (settle as `failed` on a deterministic unobservability signal, never on timeout), so this spike did not attempt to kill `__queue-owner` mid-turn to reproduce it. What this spike adds empirically: killing the submitter alone is **not** sufficient to produce that branch, because acpx's process model means the daemon, not the CLI invocation, owns turn completion. An adapter implementation that assumes "my subprocess died ⇒ outcome unobservable" would be wrong for acpx/Pi's actual process model — it needs to reconnect (`status`/`history`/stream-tail) before concluding unobservability.

### SPIKE 2 — native `agentSessionId` presence

**RULED / NEGATIVE.** No `agentSessionId` field, and no other provider-native session id, was found anywhere:
- `sessions show --format json` (`acpx.session.v1`) only ever populated `acpxRecordId` and `acpSessionId`, and in every session observed **both fields held the identical acpx-generated id** (a ULID/UUIDv7-shaped string, e.g. `01a0479c-ff14-7db9-a6e2-55a97cd1d4b5`) — there is no separate agent-side id being tracked at all for Pi.
- The raw `.stream.ndjson` file's only `_meta` payloads across the whole session lifetime were `_meta.piAcp.startupInfo` (always `null` in these runs) and `_meta.piAcp.{queueDepth,running}` — no id-bearing `_meta` content, ever.
- The wire trace shows acpx calling `session/load` with **its own** generated id as `sessionId` on the very first turn (no `session/new` and no `session/resume` call appears anywhere in any captured stream, including after a real process kill — see below); Pi's ACP adapter accepts that id and does not return a different one. `agentCapabilities.loadSession: true` is advertised; there is no explicit resume capability distinct from load.

This directly fails proving-condition (1) in the task card's "future proving condition for advertising `CAP-EXEC-RESUME-EXACT`" ("an id-comparison guard — a native `agentSessionId` is present in the ACP session `_meta`"). **`CAP-EXEC-RESUME-EXACT` cannot be honestly advertised for the Pi adapter as of `pi-acp@0.0.31` / `acpx@0.13.1`** — there is no native id to compare against. This confirms the task card's existing withholding of that capability was correct, and closes the open spike (b): Pi ACP adapter maturity is real (loadSession/context-preservation works, see SPIKE 2b below) but its session-id fidelity is exactly what the card worried about — non-existent, not merely "less established."

**SPIKE 2b (bonus, not explicitly asked for but load-bearing for the same maturity question):** tested whether `session/load` actually restores conversation context after a *real* process death, not just within-TTL reconnect. Sequence: prompt "reply with exactly: ping" → prompt "what did I ask you before?" (correctly answered "You asked me to reply with exactly: ping", queue owner still alive, same PID) → **force-killed the queue-owner daemon itself** (`kill -9` on the `__queue-owner` PID, confirmed all child processes for that session also gone) → re-prompted "what did I ask you before?" on the same session name. Result: a fresh queue owner spawned (`agent starting`, new PID), called `session/load` (never `session/resume`) with the *same* acpx-generated id, and `acpxRecordId`/`acpSessionId` were unchanged after reconnect (no re-keying). acpx's own local transcript (`messages` in `sessions show`, and `sessions history`) shows all 6 turns intact with no gap. The model's literal reply to the third "what did I ask you before?" was the somewhat unhelpful "You asked, 'what did I ask you before?'" — this reads as the model treating its own immediately-preceding turn as "what I asked before" (an artifact of asking the identical question twice in a row), not evidence of lost context: acpx's server-side history and the id are both intact and correct. **Conclusion: `CAP-EXEC-RESUME-BEST-EFFORT` is solid for Pi — real crash + reconnect preserves transcript and session identity — but there remains no native id to prove exactness.**

---

## Capability-mapping deltas vs the TASK-M1-005 card's assumptions

| Card assumption | Spike finding | Delta |
|---|---|---|
| Card frames spike (b) — Pi session-id fidelity — as genuinely open/uncertain | Confirmed negative: zero native id ever surfaces, in show JSON or in `_meta` on the wire | Not a delta in outcome (card already withholds `CAP-EXEC-RESUME-EXACT`), but it upgrades from "open question" to "settled: never available for Pi under the current `pi-acp` adapter" — worth a normative note in `docs/adapters/acp/mapping.md` rather than leaving it as a live spike |
| "`acpx status` values of `idle`/`dead` describe host/process state, never canonical settlement" (existing footgun in card) | Confirmed, and **stronger than stated**: `status` can also read **`running`** long after a turn has already completed (`stopReason` already written to the stream) — observed for 70+ seconds post-completion on both crash-mid-turn sessions, because the queue owner just idles inside its TTL window. `running` is not "a turn is in flight," it is "the queue-owner process is alive." | The mapping doc's footgun language should be widened from "idle/dead" to all three states — `running` is equally unsafe as a settlement signal, arguably more dangerous since it looks like the good/positive case |
| Card doesn't specify what `session/load` is called with, or whether `session/resume`/`session/new` are exercised in normal operation | Every observed reconnect (including post-real-crash) used `session/load` directly with acpx's own id; `session/resume` and `session/new` were never invoked in any captured stream, even immediately after `sessions ensure` created a brand-new record | Adapter implementers should not expect to see/handle `session/resume` responses for Pi — the resume fallback ladder described in acpx's own docs (`resume` → `load` → `new`) collapses to just `load` for this adapter |
| Card doesn't note `acpxRecordId == acpSessionId` for Pi | Confirmed identical in every session tested | Low-risk, but adapter code should not assume these two fields will ever diverge for Pi — don't build logic that depends on them differing |
| Card's footgun list doesn't mention CLI usage-error exit code inconsistency | `acpx pi --bad-flag` (subcommand-level parse error) exits **1**, not the documented **2**; only a *top-level* parse error (`acpx --bad-flag`, or `acpx --agent` with a missing argument) reliably exits 2 | New footgun — see exit-code table below |
| Card doesn't note that `sessions show`/`sessions history` do not accept a `--format` flag of their own | `acpx pi sessions show <name> --format json` → `error: unknown option '--format'`; the flag must be placed **before** the subcommand: `acpx --format json pi sessions show <name>` | New footgun — flag placement matters and is easy to get backwards |
| Card frames Pi's `thought_level` as a config option worth checking for headless controllability | `acpx pi set thought_level off -s <name>` works non-interactively, exit 0, confirmed applied via `sessions show` (`config_options[].currentValue`); default observed was already `low` (not `off`/`minimal`) | Confirms the ground-rule guidance ("prefer low/off") is actionable per-session; the adapter can/should pin `thought_level` deterministically per session rather than trusting the agent's default |

---

## Confirmed/new footguns (for `docs/adapters/acp/mapping.md`)

Already-known footguns from the card, all reconfirmed:
1. Always pass explicit `-s <name>` — confirmed; omitting it and pointing at a nonexistent session name produces exit 4, not a silent default.
2. `sessions ensure`, never `sessions new`, for start — confirmed idempotent: two `ensure` calls with the same `-s` name returned the identical `acpxRecordId`/`acpSessionId` (`01a0479c-ff14-7db9-a6e2-55a97cd1d4b5` both times), first call `(created)`, second `(existing)`.
3. `cancel` exit 0 does not prove a cancellation happened — confirmed: cancel-when-idle printed `nothing to cancel`, exit 0, identical exit code to a real cancel that produced `stopReason:"cancelled"`. The adapter must distinguish these by inspecting `stopReason` (or the presence/absence of an in-flight turn beforehand), never by exit code alone.
4. `acpx status` idle/dead ≠ settlement — confirmed, **and extended**: `running` is equally unreliable (see table above). Settlement must come only from `result.stopReason` in the stream/history, never from any `status`/`sessions show` process-state field.
5. `--approve-all` is a security stance — not exercised in this spike (prompts were tool-free per ground rules); flagged as still-open verification, not contradicted.

New footguns found this spike:
6. **Flag placement is order-sensitive and fails silently-ish**: format/output flags (`--format`, `--json-strict`, etc.) are **top-level** `acpx` options, not subcommand options. `acpx pi sessions show <name> --format json` errors (`unknown option`); the working form is `acpx --format json pi sessions show <name>`. An adapter that naively appends `--format json` to every acpx invocation regardless of subcommand position will break on `sessions show`/`sessions history`/etc.
7. **Exit-code usage-error inconsistency**: subcommand-level flag-parse errors (`acpx pi --bad-flag ...`) exit **1** (the same code used for agent/protocol/runtime errors), not the documented **2**. Only top-level parse errors reliably exit 2. An adapter that branches on exit code to decide "my invocation was malformed (fix and retry safely)" vs "the agent/protocol failed (do not blindly retry)" cannot trust exit 1 alone to mean the latter — it must also inspect stderr for the `error: unknown option`/usage-banner shape.
8. **`acpxRecordId` and `acpSessionId` are always identical for Pi** — don't write adapter logic (or tests) that assumes these two `acpx.session.v1` fields can diverge; for this adapter they never have across ~10 sessions/turns observed.
9. **No `agentSessionId` ever appears for Pi** — not "sometimes present," but observed absent in 100% of show-JSON and stream-file inspections across create, single-turn, multi-turn, cancel, and real-crash-reconnect scenarios. Any adapter code path written defensively "in case `agentSessionId` shows up" is dead code for the current `pi-acp` version and should not be used to gate behavior.
10. **`session/resume` is never called** by acpx for Pi, even immediately after a hard kill of the queue-owner daemon; only `session/load`. Do not write adapter/mapping-doc language implying acpx exercises the full `resume → load → new` ladder against Pi — for this adapter it is just `load`.
11. **`lastAgentExitCode`/`lastAgentExitSignal`/`lastAgentDisconnectReason` stay `null` while the queue owner is alive inside its TTL**, including immediately after a turn completes. These fields only tell you about the *previous* daemon process's exit, not the current turn's outcome — reinforces footgun 4/#4 above: never use them as a settlement proxy either.

---

## Exit-code table (as documented vs as observed)

| Code | Documented meaning (`docs/exit-codes.md`) | Observed in this spike |
|---|---|---|
| 0 | Success | `sessions ensure` (create + idempotent re-run), completed prompt (text and `--format json --json-strict`), `cancel` on a real in-flight turn (`stopReason:"cancelled"`), `cancel` with nothing running (`nothing to cancel`), `sessions close` |
| 1 | Agent / protocol / runtime error | Also observed for a **subcommand-level** bad-flag usage error (`acpx pi --nonexistent-flag`) — see footgun 7 |
| 2 | CLI usage error (bad flags, conflicting flags, malformed `--agent`) | Confirmed only for **top-level** parse errors: `acpx --bogus-flag`, `acpx --agent` (missing required argument) |
| 3 | Timeout (`--timeout` exceeded) | Not directly exercised (would require inducing a real agent-side hang); `timeout 2 acpx ...` (shell-level SIGTERM) instead produced shell exit 124, not acpx's own exit 3 — those are different mechanisms and should not be conflated |
| 4 | No session found (prompt requires an explicit `sessions new`/`ensure`) | Confirmed: `acpx pi -s spike-doesnotexist "hello"` → `⚠ No acpx session found ... Create one: acpx pi sessions new --name spike-doesnotexist`, exit 4 |
| 5 | Permission denied (every request denied/cancelled, none approved) | Not exercised — all spike prompts were deliberately tool-free/permission-free per ground rules |
| 130 | Interrupted (SIGINT/SIGTERM) | Not directly confirmed as acpx's own code; the `timeout 2` kill produced the shell's 124, since the client process likely doesn't get to run its own signal handler/exit path before `timeout` reports its own status. Worth a follow-up: send `SIGINT` directly (not via `timeout`) to check whether acpx itself reports 130 |

---

## Recommended adapter subprocess pattern

All commands assume the flag-placement rule from footgun 6 (global/output flags before the agent subcommand) and the exit-code caveats from footgun 7 (treat exit 1 *and* exit 2 as "possible usage error," always inspect stderr shape, not just the code).

**Start (idempotent, every attempt including retries):**
```
acpx --format json --json-strict pi sessions ensure -s <session-name>
```
Session name deterministically derived from the `(delivery_run_id, work_id, attempt_number, effect_id)` tuple per the card. Do not branch on `(created)` vs `(existing)` for correctness — both are success.

**Send (structured, single turn):**
```
acpx --format json --json-strict pi -s <session-name> "<prompt text>"
```
or, for large/multi-line prompts, `-f <path>`/`-f -` (stdin) rather than shell-quoting. Consume stdout as NDJSON; the turn's canonical outcome is the terminal `{"id":N,"result":{"stopReason":...}}` line, never the process exit code alone (exit 0 is necessary but not sufficient — see permission-denied-looks-like-success footgun already in the card).

**Inspect (settlement recovery / reconciliation, safe to run from any process, including after the submitter died):**
```
acpx --format json pi sessions show <session-name>      # acpx.session.v1 record: id fields, agentCapabilities, config_options, lastAgent* fields
acpx --format json pi sessions history <session-name> --limit <n>   # rendered transcript, cheap
```
and, if history is ever insufficient (e.g. need the raw `stopReason` enum value or full JSON-RPC envelope), tail the file at `sessions show`'s `eventLog.active_path` directly — it is a stable, independently-readable NDJSON file that a *different* process (e.g. a recovering orchestrator after restart) can consume without going through acpx at all.

**Cancel (cooperative):**
```
acpx pi cancel -s <session-name>
```
Exit 0 either way; the adapter must re-check `sessions show`/`sessions history`/stream-tail afterward for `stopReason:"cancelled"` to confirm an actual cancellation occurred (footgun 3).

**Determining unobservability (per the card's abandonment ruling):** before settling `failed` on "submitter died," the adapter must first attempt reconnect via `sessions show`/`sessions history`/stream-tail (all three are viable from a fresh process with no live queue owner) — this spike demonstrated that in the common case the queue-owner daemon is still alive and holds the answer. Only settle `failed`-for-unobservability if, after that reconnect attempt, no recorded result exists for the turn (e.g. `sessions show` reports the daemon dead — `lastAgentExitCode` populated / `status` `dead` — with no matching `stopReason` in history for the outstanding turn). This is a deterministic check, not a timeout.

**Cleanup (out of the hot path, operational hygiene only):**
```
acpx pi sessions close <session-name>
acpx pi sessions prune --older-than <n>
```

---

## Open questions

1. **Exit 3 / exit 130 not directly triggered by acpx itself** in this spike (only shell-level `timeout`'s 124 was observed for a killed client). Recommend a follow-up spike using `--timeout <n>` against a prompt engineered to exceed it, and a direct `SIGINT` (not via `timeout`) to the acpx client process, to confirm acpx's own exit-3/130 paths match the documented table.
2. **True queue-owner death mid-turn** (both submitter *and* daemon gone before the result is written) was deliberately not induced here — it's already normatively settled by the task card's ruling, and reliably inducing it (racing a kill against the daemon's own turn-completion write) is fiddly to do deterministically. If the adapter's abandonment-detection code path ever needs a regression test, it will need a stub-`acpx` harness (as the card already calls for) rather than a live-agent timing race.
3. **Exit 5 (permission denied)** not exercised — ground rules deliberately kept prompts tool-free. The existing card footgun about permission-denied-looks-like-success remains a documented risk, not independently re-verified by this spike.
4. Segment rotation (`eventLog.max_segments`/`max_segment_bytes`) was visible in the schema (5 segments × 64MiB) but never exercised — all spike sessions stayed well under a single segment. Long-running production sessions should be checked separately for rotation/read behavior across segment boundaries.
