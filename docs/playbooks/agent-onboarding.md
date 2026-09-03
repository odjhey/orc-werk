---
id: PLAYBOOK-AGENT-ONBOARDING
type: playbook
status: current
authority: informative
description: One executable entry point for an agent onboarding an adopting repository to orc (+ optionally ergo) — start here, follow top to bottom, verify every gate.
---

# Agent onboarding: orc (+ ergo)

You are an agent that has just been told "onboard this project to use orc(+ergo), see this one file." This document is that file. Follow it top to bottom in the target repository. Every phase ends with a verification gate — do not proceed past a failed gate. Links go deeper; you do not need to open them to finish onboarding, only to understand *why* a step exists.

Voice note: every instruction below is something you run and check, not background reading. Where this document would otherwise restate a canonical rule, it cites the stable ID and moves on — the command sequences and config snippets are the part you execute verbatim.

## Part 0 — orientation

**orc** is a delivery ledger and seat protocol: it durably records what was dispatched, attempted, and settled for a unit of delegated work, and it separates an executor's claim of "done" from an independently recorded verdict (`INV-003`). Since `ADR-0005`, orc never pull-observes another process's lifecycle — every executor (you, a CI job, another agent) stays external and **pushes** its observation in via `orc record` or an equivalent config edit; orc only reacts to what was pushed. **ergo** is an optional backlog-planning layer that sits in front of orc: it owns "what should be done" (decomposition, ready/claim, dependency ordering) while orc owns "what was actually done, and who vouched for it" (`PLAYBOOK-ERGO-COEXISTENCE`).

For the human-facing "why" behind each tool, one link each — read only if you need the rationale, not to finish onboarding:

- `PRODUCT-ADOPTION` (`docs/product/adoption.md`) — when to adopt orc, the adoption ladder, prerequisites.
- `PLAYBOOK-ERGO-COEXISTENCE` (`docs/playbooks/ergo-coexistence.md`) — why orc and ergo coexist cleanly and what authority each owns.
- The field report (`docs/reports/2026-09-03-xatu-adoption-field-report.md`) — a real second-repo adoption, its incidents, and what earned its keep. Part A below folds its most costly lessons directly into the steps; read the report itself only for the full narrative.

## Part A — orc (always)

### A1. Install and verify orc is resolvable

Two install forms exist. Prefer a real console script; fall back to the module form; **never let an unresolvable `orc` fail silently**.

```bash
# Preferred: install the package so `orc` lands on PATH.
pip install <path-to-a-checkout-or-git-source>
orc version

# Zero-install fallback: no pip step, run the module directly from a checkout.
PYTHONPATH=<path-to-checkout>/src python3 -m orc_werk.cli version
```

**Fold in issue #238 before you rely on either form from automation.** A shell alias (`alias orc='PYTHONPATH=... python3 -m orc_werk.cli'`) is genuinely useful interactively, but it is **invisible to any non-interactive/non-shell caller**: `command -v orc` fails and Node's `spawnSync('orc', ...)` returns `status: null` with `error.code === 'ENOENT'`, because an alias lives only in the interactive shell session that defined it and is never inherited by a spawned child process. Verified directly:

```bash
alias orc='PYTHONPATH=/path/to/checkout/src python3 -m orc_werk.cli'
bash -c 'command -v orc; echo "exit=$?"'     # exit=1 — invisible from a fresh subshell
bash -c 'orc version'                         # bash: orc: command not found (exit 127)
```

If you are writing automation (a script, a generator, a CI step, another agent's tool call) that needs to detect or invoke `orc`, do not rely on `command -v orc` or a bare `orc` spawn succeeding. Probe the module form as a fallback (`python3 -m orc_werk.cli version` with `PYTHONPATH` set in the child's environment, not assumed from a parent shell's alias) and **make the unresolvable case loud** — a hard failure with a clear message, never a silently skipped step. This was the field report's most expensive incident (§1.2): a presence-guard that silently skipped let a broken config generator ship through a green build.

**Verification gate:** one of these must print an identity line (`orc <version> (source <path>, ...)`), not an error:

```bash
orc version                                            # PATH form
PYTHONPATH=<checkout>/src python3 -m orc_werk.cli version   # module-form fallback
```

### A2. Scaffold the adopting repo — `orc onboard`

`orc onboard --path .` (run from the adopting repo's root, or pass `--path <dir>`) mechanizes the adoption scaffold (`TASK-M3D-001`): it adds a `.orc/` `.gitignore` entry, installs the `orc-ledger` project skill under `.agents/skills/orc-ledger/` and links it resolvably under `.claude/skills/orc-ledger`, writes a slim `## Delivery ledger (orc)` block into `AGENTS.md` (mode/locality/skill-pointer only), and prints an honest install-verification report. It is idempotent — re-running it upgrades a stale unmodified copy and skip-with-notes an operator-modified one unless `--force`.

```bash
orc onboard --path .
```

Decide ledger placement up front — one honest sentence per option (worked example: the field report's §3 table):

- **`--ledger local`** (default): adds `.orc/` to `.gitignore`. Journal writes never enter product history, but a fresh clone or worktree starts with no ledger and cross-machine reconstruction falls back to PR/issue threads.
- **`--ledger committed`**: leaves `.gitignore` unchanged (warns if an existing entry conflicts). Every clone sees the full delivery history, but every recorded observation is a commit in your product repo's history forever.

**Verification gate:**

```bash
ls .claude/skills/orc-ledger          # resolves (symlink or dir) — skill is discoverable
grep -n "Delivery ledger (orc)" AGENTS.md   # the agents-block landed
```

### A3. The day-to-day loop

Full protocol detail (role separation, mechanics, exit codes, the independent-derivation rule) lives in `PLAYBOOK-AGENT-CLI` — read it before recording your first observation as a ship or verify seat.

Use the `git` candidate adapter for any work that lives in a repository — derived identity beats hand-recorded identity (the field report's own adoption decision, §3), and with it candidate identification is automatic on re-dispatch: no hand-authored candidate step exists anywhere in the loop. Minimal config:

```json
{ "candidate": {"adapter": "git", "repo_path": "<absolute path to the repo the work lands in>"} }
```

The loop, with that config — every step is exactly the command shown, in order:

```
1.  orc dispatch "<intent>" --run-id <id> --config cfg.json      # creates/claims Work, starts execution
2.  exit 3 (pending, awaiting execution-outcome) is healthy — not an error
3.  the external executor (you, another agent, a CI job) does the work
4.  orc record <id> --work <work-id> --outcome completed|failed [--evidence-ref ...]   # ship seat pushes its observation in;
                                                                 # this verb NEVER sets candidate identity
5.  orc dispatch --run-id <id>                                   # re-dispatch: picks up the settlement AND the git adapter identifies
                                                                 # the candidate itself (head sha, diff digest) — moves to ASSURING
6.  exit 3 again (pending, awaiting assurance-verdict) is healthy; the output names the bound candidate head
7.  a DIFFERENT agent independently derives the candidate identity itself (git rev-parse HEAD, run by the verifier) and records:
    orc record <id> --work <work-id> --verdict accepted|rejected --derived-identity '{"head_sha": "<self-derived sha>"}'
8.  orc dispatch --run-id <id>                                   # re-dispatch: binds the verdict ("derived_identity corroborated"),
                                                                 # accepts/completes
9.  exit 0 — Work ACCEPTED
10. every step's output ends with a `next:` block naming the exact legal next command — trust it over inventing your own procedure
```

One note for the non-git case only: with a *scripted* candidate config (no `candidate.adapter: "git"`), `record --outcome` still never sets candidate identity, so after step 5 the run rests at `EXECUTING` until you hand-author the attempt entry's `candidate` payload in the run's persisted config (`orc config-schema` prints the attempt-entry shape) — the git adapter is what makes that extra step disappear.

Re-dispatching the identical command is always safe (idempotent by effect key, `INV-020`) — it is the crash-recovery move, not just the happy path.

Two operating rules from the field report's promotions, stated as rules because they cost real budget to learn the hard way:

- **Settle before reaping.** An external executor's evidence (its worktree, its session) can be destroyed before its observation is recorded. "The process/worktree is gone" is not the same fact as "the work failed" — if you tear down an executor's workspace before recording its outcome, you can manufacture a false `failed` that consumes retry budget and blocks a run whose work actually succeeded. Record the settlement first; reap second.
- **Prove your wake mechanism fires.** Whatever you arm — `orc dispatch --wait` or config-declared observers — trigger one on purpose and watch it land before you rely on it silently. Verified directly: launch `--wait` in the background, record a settlement from another shell, and confirm the wait unblocks before its timeout instead of waiting the full duration:

```bash
orc dispatch --run-id <id> --wait --timeout 20 --poll-interval 1 &
sleep 3
orc record <id> --work <work-id> --outcome completed
wait   # the backgrounded --wait exits 3 (next pending state) well before the 20s timeout
```

A watcher that fails silently (a broken predicate, an unquoted variable, a detached background process) reports "all quiet" forever — indistinguishable from genuinely nothing happening. Prove it fires now, not the first time it matters.

### A4. Update the adopting repo's own agent docs

```bash
orc onboard --print-agents-block
```

prints the slim `## Delivery ledger (orc)` block without writing anything (A2 already wrote it via plain `orc onboard`; use `--print-agents-block` to preview it, regenerate it after an upgrade, or copy it into a second agent-instructions file). Place it in the repo's `CLAUDE.md`/`AGENTS.md` per that repo's own conventions (a dedicated section, a top-level pointer, whatever the existing document structure expects). Then add one more line, by hand, that this document does not generate for you:

> Delivery ledger onboarding lives at `docs/playbooks/agent-onboarding.md` in the orc-werk repo (or wherever this adopting repo vendors/references it) — read it before re-onboarding or extending this setup.

**Verification gate:** the adopting repo's agent-instructions file now contains both the generated block and your added pointer line; a fresh session opening that file has everything it needs to find this playbook without being told separately.

## Part B — + ergo (optional)

Only do this section if the project wants a backlog-planning layer on top of orc. Skip straight to Part C otherwise.

### B1. Check ergo availability

```bash
command -v ergo || echo "ergo not on PATH"
```

Install per [ergo's own README](https://github.com/sandover/ergo) (brew or `go install` — this document does not restate that instructions, they change independently of orc). Then:

```bash
ergo init
```

If your harness supports project skills, install ergo's backlog-planning skill per its own docs — planning agents use that skill; seat agents (ship/verify) keep using the `orc-ledger` skill A2 installed. Do not mix the two skills into one agent's context (see B3).

**Sandbox note (this playbook's own verification):** no `ergo` binary was available while writing/verifying this document. A minimal shim implementing `init`/`add`/`list --ready`/`result`/`done`/`fail`/`cancel`/`show` against a local JSON state file stood in for it, matching the surface `PLAYBOOK-ERGO-COEXISTENCE`'s wiring actually calls. The wiring below was verified end-to-end against that shim, not the real binary — if the real ergo's CLI surface has since diverged for these specific subcommands, re-verify before trusting this section unmodified.

### B2. The coexistence wiring

**Convention: `run_id` == the ergo task id.** This is what lets the observer below map a settled orc run back to exactly one ergo task with no separate lookup table.

```bash
orc dispatch "<ergo task title + body>" --run-id <ergo-task-id> --config dispatch-config.json
```

Observers config (`SCN-018`) — put this in the run's config or the repo's `.orc/profile.json` so every run inherits it:

```json
{
  "observers": {
    "on_verdict": {"command": ["./scripts/ergo-on-verdict.sh"], "timeout_seconds": 15},
    "on_blocked": {"command": ["./scripts/ergo-on-blocked.sh"], "timeout_seconds": 15}
  }
}
```

The two scripts (adapted from, and kept consistent with, `PLAYBOOK-ERGO-COEXISTENCE`'s own wiring — the triggering fact's envelope arrives as JSON on stdin; `delivery_run_id` is top-level, `verdict`/`reason` live under `data`):

```bash
#!/usr/bin/env bash
# scripts/ergo-on-verdict.sh -- sole writer of terminal ergo states (accept path).
set -euo pipefail
fact=$(cat)
run=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("delivery_run_id") or d.get("run_id",""))' <<<"$fact")
verdict=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("verdict") or d.get("data",{}).get("verdict",""))' <<<"$fact")
task="$run"   # run_id == ergo task id, per convention above
if [ "$verdict" = "accepted" ]; then
  ergo result "$task" "accepted via orc run $run" || true
  ergo done "$task" || true
else
  ergo result "$task" "verdict=$verdict via orc run $run -- see orc report $run" || true
fi
```

```bash
#!/usr/bin/env bash
# scripts/ergo-on-blocked.sh -- maps a blocked orc run to ergo fail.
set -euo pipefail
fact=$(cat)
run=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("delivery_run_id") or d.get("run_id",""))' <<<"$fact")
reason=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("data",{}).get("reason",""))' <<<"$fact")
ergo result "$run" "blocked via orc run $run: $reason" || true
ergo fail "$run" || true
```

**Verified end-to-end in this sandbox:** dispatch → ship seat records outcome → re-dispatch → hand-author scripted candidate identity → re-dispatch (ASSURING) → verify seat records `--verdict accepted` with `--derived-identity` → re-dispatch. On that final re-dispatch (the pass that journals `FACT-ASSURE-SETTLED`), `on_verdict` fired and the shim's task state flipped:

```json
{"demo-onboard-ergo": {"status": "done", "title": "Sandbox coexistence demo task",
                        "result": "accepted via orc run demo-onboard-ergo"}}
```

`status: "done"` with the orc run id embedded in `result` — exactly the pair this section exists to wire.

### B3. Coexistence conventions (state these as agent rules)

One line each; `PLAYBOOK-ERGO-COEXISTENCE` carries the rationale for all four.

1. **Dependencies live in ergo only.** Never encode the same dependency edges in both an orc plan and ergo — one orc run is one task (single work) unless a task is genuinely a mini-DAG.
2. **Phase the skills.** Planning agents load ergo's backlog-planning skill; seat agents (ship/verify) load the `orc-ledger` skill. Holding an ergo claim does not make an agent a verify seat — seats are orc's.
3. **Terminal ergo states come only from the observer.** No agent or human hand-marks an ergo task `done`/`fail` — that is the one way to break the whole arrangement.
4. **Wake stays orc-side.** Use `orc dispatch --wait` or the observers above for delivery polling; ergo's `list --ready` is for planning views only.

### B4. Agent-docs addendum for ergo

Append to the same agent-instructions file A4 updated:

> This repo also runs ergo for backlog planning. Planning uses ergo's own skill; delivery uses the `orc-ledger` skill. Never hand-mark an ergo task `done`/`fail` — only `scripts/ergo-on-verdict.sh`/`scripts/ergo-on-blocked.sh` (fired by orc's `on_verdict`/`on_blocked` observers) do that. See `docs/playbooks/agent-onboarding.md` and `PLAYBOOK-ERGO-COEXISTENCE` for the full wiring.

## Part C — done-when

Self-assert every line before declaring onboarding complete:

- [ ] `orc version` (PATH form) or the module-form fallback prints an identity line — resolvable, and loud if it were not (A1).
- [ ] `.claude/skills/orc-ledger` resolves and `AGENTS.md` (or the repo's equivalent) contains the generated `## Delivery ledger (orc)` block (A2).
- [ ] One throwaway run, using A3's git-candidate config, was driven `dispatch → record --outcome → dispatch (candidate binds automatically) → record --verdict (different seat, self-derived identity) → dispatch` to `ACCEPTED` (exit 0) — the loop in A3 actually works in this repo, not just on paper. Then cleaned up if you don't want it in the real ledger: an `ACCEPTED` run is removed by deleting its run directory (`<journal-dir>/<run-id>/`); `orc cancel <run> --work <work> --reason "..."` is only for closing a throwaway you abandon while it is still pending (`ACCEPTED` is terminal — cancel is rejected from there).
- [ ] If Part B was done: one ergo task was driven ready → claim → an orc run → `done` written only by the observer, with the orc run id visible in the ergo task's result.
- [ ] The adopting repo's own agent-instructions file was updated per A4 (and B4, if ergo is in play) — a fresh session opening it finds the pointer back to this document.

## Related

- `PRODUCT-ADOPTION`
- `PLAYBOOK-ERGO-COEXISTENCE`
- `PLAYBOOK-AGENT-CLI`
- `PLAYBOOK-CLI-USAGE`
- `ADR-0005`
- `docs/reports/2026-09-03-xatu-adoption-field-report.md`
- `docs/cli/README.md`
