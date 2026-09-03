---
id: REPORT-2026-09-03-XATU-ADOPTION-FIELD
type: report
status: current
authority: informative
description: Second-repo adoption field report — operating orc 0.4.1 through 0.7.0 as a supervised multi-lane watchtower; incidents, costs, and what earned its keep.
---

# Adoption field report — supervised multi-lane watchtower (orc 0.4.1 → 0.7.0)

Evidence from the `xatu-delivery-companion` adoption (`TASK-M2-004`'s second-repo
adoption, adopted 2026-08-30). The deployment is a single operator running a
"watchtower" agent that decomposes work into seats, dispatches many concurrent
coding lanes, verifies adversarially, and merges. Adoption ladder position:
**multi-agent ledger** (agents record their own observations), local ledger,
Beads mirror, no autonomous execution.

This report is evidence, not contract. It deliberately does **not** restate
`PRODUCT-ADOPTION` (when to adopt, rungs, install), `PLAYBOOK-AGENT-CLI` (seat
discipline), or `docs/cli/README.md` (surface). It records what an adopter hit
that those documents could not tell us in advance, with what each cost, so
durable conclusions can be promoted per `docs/reports/README.md`.

Incident claims are ours and are stated as observations. Version-specific CLI
claims were re-verified against the installed 0.7.0 before writing.

## 1. Incidents, ordered by cost

### 1.1 Upgraded across 0.5.0 with pending runs — 23 runs stranded

We upgraded 0.4.1 → 0.6.0 without settling in-flight runs first. Because
0.5.0 removed the `acp` `ExecutionPort` (`ADR-0005`) and configs naming it now
fail `ERR-VALIDATION`, **both `dispatch` and `cancel` refuse such a config** —
so every pending acp run became unreachable through any verb simultaneously.

Recovery: pin back to `v0.4.1`, `orc cancel` all 23 with honest reasons, then
upgrade again.

The 0.5.0 release note *does* say to settle or cancel first. We read it
carefully only after the upgrade. Two things would have helped an adopter who
does the same:

- The refusal's `next:` guidance names the migration but not the recovery path
  (*pin back to the last version that still validates this config, close it
  there, then upgrade*). A stranded operator is exactly the reader who needs
  the recovery, not the rationale.
- **Suggested promotion:** an explicit pre-upgrade check — even documented
  prose in the release process — of the form "no non-terminal runs remain"
  before a breaking adapter removal.

### 1.2 `orc` installed as a shell alias is invisible to scripts

`PRODUCT-ADOPTION` presents the alias form as the permanent zero-install
fallback, which is genuinely useful. The consequence for automation is not
called out: a shell alias is not on `PATH`, so `command -v orc` fails and
Node's `spawnSync('orc')` returns `status: null` with `ENOENT`.

Our watchtower scripts guarded on exactly those, so every orc-dependent script
either hard-failed or — worse — **silently skipped**. A test whose job was to
validate generated dispatch configs never ran, and a config generator that
emitted the removed acp shape shipped through a fully green build. The
regression was caught later by an independent verify seat, not by the gate.

Mitigation on our side: resolve the module form
(`PYTHONPATH=<src> python3 -m orc_werk.cli`) as a fallback, and make the
unresolvable case loud rather than skip-quiet.

- **Suggested promotion:** a sentence in `PRODUCT-ADOPTION`'s install section
  noting that the alias form is invisible to non-shell callers, and that
  automation should probe the module form too. `orc onboard` already reports
  "orc on PATH vs module form" honestly (`TASK-M3D-001`) — that verification
  output is the natural place to warn an adopter who is about to script against
  a name their scripts cannot see.

### 1.3 Reaping a workspace before settling manufactured a false `failed`

We reaped a lane's worktree and its executor session, then re-dispatched. The
adapter observed the now-destroyed session and journaled
`FACT-EXEC-SETTLED` with `outcome: "failed"` — for work whose PR had **already
merged cleanly**. The false failure consumed retry budget across two further
attempts (both `ERR-TEMPORARY`, because the worktree was gone) and the run
terminated `BLOCKED` with `retry-budget-exhausted`: a permanent, wrong record
of successful work.

The settlement's own extensions are the interesting part:

```json
"acp-settlement/v1": {
  "suppression":     {"resultRecord": 100, "laterRecord": 101,
                      "laterRecordClass": "session_info_update",
                      "stopReason": "end_turn"},
  "unobservability": {"lastAgentExitCode": null, "lastAgentExitSignal": "SIGTERM"}
}
```

The session transcript contains exactly one terminal result — a clean
`stopReason: "end_turn"` — followed by a single trailing `session_info_update`.
Reported with the event log as a question on issue #210: whether the
suppression rule should distinguish *activity indicating non-terminality*
(retry, backoff) from benign trailing metadata, and whether post-hoc `SIGTERM`
unobservability should be able to downgrade an already-observed terminal
`end_turn` to `failed`.

This is **historical** — 0.5.0 removed the adapter — and is recorded here only
because the same suppression/unobservability classification may outlive it.

- **Operating rule we adopted:** settle first, reap second. "The process is
  gone" is not the same fact as "the work failed."

### 1.4 Dispatch returns; nothing tells you the executor finished

Understood correctly, this is the design (`ADR-0005`): orc never pull-observes.
Understood late, it costs work. Five finished lanes sat unnoticed, plus one that
had committed but never pushed, until the operator said the silence felt wrong.

This drove the `--wait` request (issue #210) and, ultimately, observer hooks.
Both landed and both help. Two adopter notes:

- Whatever wake mechanism you arm, **prove it fires**. We built three watchers
  that did not: a broken `find` predicate whose stderr was swallowed, an unquoted
  shell variable that did not word-split under `zsh`, and a `nohup … &` that
  detached from the notification path. Each failed silently and each reported
  "all lanes idle" indefinitely.
- Config-declared observers beat a remembered waiter, because the config
  survives the operator forgetting.

### 1.5 Profile merge forced fully self-contained configs

Already filed upstream (#174, #175) and recorded here only as adoption impact: a
profile value overrode an explicit `--config`, nested objects replaced rather
than composed, and the deep merge had no unset. A dispatch was blocked until
`.orc/profile.json` was emptied to `{}`.

Every run's config in this deployment is therefore fully self-contained, and
profile defaults are unused pending those issues.

### 1.6 A correction we owe the record

We reported on #210 that "acp does NOT auto-settle; the PR is the real signal."
**That was wrong**, and the maintainer probe disproving it was correct. Our
measurement raced "a PR appears" against "orc settles" — but a PR opens
mid-turn while orc settles at the turn boundary, so the loop could only ever
return the answer it returned. The journal shows adapter-written
`FACT-EXEC-SETTLED` on re-dispatch, exactly as described.

Recorded here because the same false conclusion appeared in our own repo's docs
for a day, and because "your measurement can only return one answer" is a
failure mode other adopters will meet.

## 2. What earned its keep

- **Re-dispatch as the universal verb.** Resume, poll, and crash-recovery being
  one idempotent command means "I don't know what state this is in" has a
  trivial answer instead of an investigation. This is the single most
  operationally valuable property of the CLI.
- **The `next:` affordance.** Printing the exact legal next command derived from
  the state machine removes a whole class of invented procedure from agents that
  would otherwise guess. Agents follow it reliably.
- **Candidate-bound assurance** (`INV-003`, `INV-005`–`INV-010`). Verifiers
  deriving candidate identity themselves, rather than copying the shipper's
  value, has repeatedly been the thing that made "verified" mean something. On
  our PRs, adversarial verification against a self-derived candidate rejected a
  substantial majority on first pass — for defects tests and CI had passed over.
- **The journal outranking memory.** "If a doc or your recollection disagrees
  with the journal, the journal wins" saved us from re-doing landed work more
  than once, most sharply when a summary and the ledger disagreed about whether
  a lane had shipped.
- **`orc config-schema` as the honest reference.** Every time our own docs and
  the CLI's self-description disagreed, the CLI was right. We now treat it as
  the source and our docs as the derivative.

## 3. Adoption decisions we had to make, and what we chose

Offered as a worked example, not a recommendation for other deployments.

| Decision | Chose | Why |
|---|---|---|
| Ledger placement (`--ledger`) | local | Keeps journal writes out of product history. Cost accepted knowingly: fresh clones and worktrees carry no ledger, and cross-machine reconstruction falls back to PR threads. |
| Wake mechanism | observers, `--wait` second | Config-declared beats remembered. |
| Verify seat model | different family from the builder | Independence is the point; same-model review finds measurably less. Not an orc concern, but the discipline orc's seat separation exists to support. |
| Candidate adapter | `git` wherever work is in a repo | Derived identity beats hand-recorded identity. |
| Mirror | Beads, write-only projection | Explicitly not an agent-facing tracker; two agent-facing trackers would mean two competing sources of truth. |

One non-obvious mechanic worth surfacing for adopters: with `candidate.adapter:
"git"`, the attempt entry carries only `assurance` and `outcome` and **never**
`candidate` — a config-declared candidate there would be silently ignored, so
orc refuses it. Verified by running both shapes:

```
git candidate adapter      ->  ["assurance", "outcome"]
non-git candidate adapter  ->  ["assurance", "candidate", "outcome"]
```

`orc config-schema` documents this; it is easy to miss on first read and
produces a confusing failure when missed.

## 4. Suggested promotions

Per `docs/reports/README.md`, the durable conclusions worth considering for
normative homes:

1. **Pre-upgrade settlement check** before any breaking adapter removal, and
   recovery-path guidance (pin back → close → upgrade) in the refusal's `next:`
   (from 1.1).
2. **Alias-invisibility note** in `PRODUCT-ADOPTION`'s install section and/or
   `orc onboard`'s verification output (from 1.2).
3. **"Settle before reaping"** as an operating rule wherever executor lifecycle
   is discussed — it generalizes past the removed adapter, since any external
   executor's evidence can be destroyed before observation (from 1.3).
4. **"Prove your wake mechanism fires"** alongside the `--wait`/observers
   documentation (from 1.4).

Items 1 and 2 are the two that cost us the most and were the most avoidable
with a sentence of documentation.
