---
id: SCN-018
type: scenario
status: current
authority: normative
description: Config-declared observer commands fire, fire-and-forget, on facts newly appended by the current dispatch pass (issue #193).
---

# SCN-018 — Observer hooks

## Purpose

Issue #193 asks for an easy, agent-authorable way to react to orc's own
delivery state — a notification when a run blocks, a custom report on
verdict, a tracker update on settlement — without touching the kernel or
waiting for a first-class adapter. This scenario specifies **observer
hooks**: config-declared commands the CLI composition layer spawns after
specific canonical Facts are journaled.

Observer hooks are the notification half of the story #193 splits in two;
the behavior-modification half (a generic subprocess adapter that can
steer state) is explicitly a separate, unfiled card and out of scope here.

Observer hooks generalize the Beads mirror's write-only-observer posture
(`INV-014`, `docs/adapters/beads/mapping.md`) from one built-in adapter to
an arbitrary, operator-authored command, and they are the push-model
notification story ADR-0005 leaves open: orc never pull-observes another
process, and it does not become one either — a hook is spawned and
released, never watched for its own outcome. They complement `SCN-017`'s
wait mode: `--wait` is how a caller *pulls* the next resting point by
re-dispatching; observer hooks are how orc *pushes* a fire-and-forget
notice of that same resting point to a caller's own script, at the moment
dispatch already has the news.

Observer hooks add **no kernel semantics**. No new Fact, Decision, Effect,
transition-table row, or `STATE-DELIVERY` clause exists for firing a hook;
the sole normative definition is CLI-level, same architectural slot as the
Beads mirror (`docs/adapters/beads/mapping.md`'s "Direct CLI invocations"
section) and the command assurance script (`SCN-015`). The config schema
and the firing mechanism are CLI-owned, not core (`CLAUDE.md` rule 8): the
canonical `journal`/`fold` path is unaware observers exist.

**Naming ruling.** Issue #193's working title "observer hooks" maps to the
`observers` config key: `observers` is the ruled name, chosen for its
observer-pattern lineage (a pure, write-only observer of transitions,
`INV-014`) and to avoid collision with generic "hook" terminology in
adopter tooling. Nothing shipped under the old name, so there is no
compatibility surface — this is a pre-implementation naming decision,
recorded here.

## Given

- A CLI dispatch config carries a top-level `observers` key alongside the
  existing `plan`/`candidate`/`assurance` keys:

  ```json
  {
    "observers": {
      "on_settle": {"command": ["./scripts/notify-settle.sh"]},
      "on_verdict": {"command": ["./scripts/notify-verdict.sh"], "timeout_seconds": 10},
      "on_blocked": {"command": ["./scripts/notify-blocked.sh"]}
    }
  }
  ```

  Each of `on_settle`, `on_verdict`, `on_blocked` is optional and
  independent; an operator may configure any subset.
- Each `observers.<trigger>` object accepts an optional `timeout_seconds`
  key: a non-negative number, in seconds, defaulting to `30` — the bounded
  maximum lifetime of each observer process spawned for that trigger
  (enforced per the fire-and-forget section below). `command` and
  `timeout_seconds` are the only keys of an observer entry.
- `command` is a non-empty argv-array of strings, never a shell string.
  There is no inline-script-text, `args`-appended-to-command, or
  environment key — matching command assurance's `script`/`cwd`-only
  config shape (`SCN-015`, `docs/adapters/command/mapping.md`'s "Config
  and candidate combination").
- The first element of `command` resolves (relative paths resolve against
  the dispatch config's `cwd`, matching command assurance) to a path
  **inside** that `cwd` by path containment, not textual prefix matching —
  the identical containment rule `SCN-015`'s "Containment and seat checks"
  section states for the command assurance script. An operator-authored,
  PR-reviewed, repo-versioned script referenced by config, never an
  ad hoc string constructed or injected at dispatch time.
- Work A is mid-run with a prior dispatch pass already having journaled
  history (so this pass replays existing Facts before appending new ones).

## When

1. Caller runs an ordinary `orc dispatch` pass (with or without `--wait`,
   `SCN-017`) against the config above.
2. The pass's observation sweep finds Work A's execution has settled
   `completed`, journals `FACT-EXEC-SETTLED(completed)`, and — later in the
   same run, a subsequent pass — an assurance verdict settles and
   `FACT-ASSURE-SETTLED` is journaled, then (a different Work, or a later
   attempt of the same Work exhausting its retry budget) `FACT-WORK-BLOCKED`
   is journaled.

## Then

### Trigger mapping

1. `on_settle` fires once per pass for each `FACT-EXEC-SETTLED` newly
   appended that pass, regardless of outcome (`completed` or `failed`) —
   the settlement fact itself is the trigger, not a specific outcome value.
2. `on_verdict` fires once per pass for each `FACT-ASSURE-SETTLED` newly
   appended that pass, regardless of verdict (`accepted`, `rejected`, or
   `inconclusive`).
3. `on_blocked` fires once per pass for each `FACT-WORK-BLOCKED` newly
   appended that pass.
4. A pass that appends none of these three Fact kinds spawns nothing: an
   ordinary re-dispatch of a still-pending run with no new settlement,
   verdict, or block is observer-invisible, exactly as it is journal-
   invisible (`SCN-017` step 1).
5. Verdict inheritance (`STATE-DELIVERY` mechanical fact sequencing item 8)
   journals no new `FACT-ASSURE-SETTLED` for a re-observed candidate — so
   an inherited verdict does not re-fire `on_verdict`. Only a fresh
   settlement Fact, actually appended this pass, is a trigger.
6. **Firing lifecycle.** Observers for a pass's newly-appended facts are
   spawned after the pass completes its journal appends and before
   dispatch exits: one invocation per triggering fact, spawned in the
   triggering facts' `seq` order. There is no ordering guarantee across
   triggers beyond that `seq` order, and no guarantee about the relative
   completion order of the spawned processes themselves (they are not
   waited on, step 9).

### Fact delivery: JSON on stdin, never argv or environment

7. The triggering fact — the journaled fact envelope exactly as it now
   exists in the journal (kind, data, attribution, `seq`, and any other
   envelope fields the journal adapter carries) — is serialized as one
   portable JSON document and written to the spawned process's standard
   input, then standard input is closed. No fact data, run id, or work id
   is ever placed in argv or an environment variable — the identical
   discipline command assurance's "Trust boundary and invocation" section
   states for candidate data, and `orc refs --resolve`'s hostile-input
   posture for journal-derived content in general.
8. The command runs as the configured argv list with `shell=False`; no
   shell interpolation of any fact field is possible because no fact field
   ever reaches a shell.

### Fire-and-forget: non-blocking, pure egress

9. Dispatch spawns the observer process and does not wait on it beyond
   confirming the spawn itself succeeded — a short, bounded step, not a
   wait for the observer's own exit. The dispatch pass's remaining work
   (further passes, output, exit code) proceeds without depending on
   whether or when the observer process exits.
10. The observer's exit status, stdout, and stderr are never inspected for
    effect on the run: they cannot set state, cannot be journaled as a
    fact, cannot influence a Decision, and cannot change dispatch's own
    exit code or stdout — pure egress, the same write-only posture the
    Beads mirror already establishes for its own effect on the kernel
    (`INV-014`, `docs/adapters/beads/mapping.md`'s "Degraded mirror"
    section: a mirror failure is stderr-only and never alters dispatch's
    exit code or stdout; observer hooks make the identical promise).
11. A hook whose command spawn itself fails (missing or non-executable
    script) is a one-line stderr warning per
    dispatch pass, per triggering fact — never a raised error, never a
    changed exit code. The run is unaffected; dispatch proceeds exactly as
    if the observer had not been configured.
12. **Bounded lifetime by delegated supervision** (semantics, not
    implementation). Each observer runs in its own session/process group,
    and its bounded lifetime — the entry's `timeout_seconds`, default 30 —
    is enforced without dispatch waiting: dispatch blocks only for the
    spawn (step 9) and delegates timeout enforcement to the spawned
    supervision itself, which travels with the observer's process group.
    Dispatch exiting does not orphan the enforcement; an observer that
    outlives its bound is killed — the whole process group — by that
    supervision, never by a later dispatch pass. The kill semantics
    (new session/process group at spawn so the whole group can be reaped)
    mirror command assurance's process-group discipline
    (`docs/adapters/command/mapping.md`'s "Exit-status mapping" timeout
    row, `SCN-015`); the non-waiting delegation is the clause that is new
    here — command assurance waits for its verdict, an observer is never
    waited on.

### Replay safety and the at-most-once contract

13. Hooks fire only for facts **newly appended by the current process's
    fold/append step this pass** — never for facts already present in the
    journal before this pass began, and never again on any later replay
    or reconstruction of the same history. A dispatch pass that replays
    existing journal history to rebuild in-memory state (every pass does
    this, `INV-020`) does not re-fire observers for history it is merely
    reconstructing; only the genuinely new tail this pass itself appends
    is eligible.
14. Consequence, stated honestly as the v1 contract: delivery is
    **at-most-once**. A crash between a fact's append and the
    corresponding observer's spawn loses that notification permanently —
    the fact is durably journaled (it happened), but nothing re-fires the
    hook for it on any later pass, because a later pass's replay of that
    same fact is exactly the history-reconstruction case step 13 excludes.
15. **At-least-once (journaled hook effects, retried until confirmed
    delivery) is explicitly rejected for v1.** Making hook delivery durable
    would require either journaling a hook-dispatch Effect (a provider-
    vocabulary leak into the canonical journal that `INV-014` exists to
    prevent — the same rejection the Beads mirror's "Degraded mirror"
    section already reasons through for its own would-be journal
    extension) or some other in-kernel bookkeeping of "which hooks have
    fired for which fact" that the kernel would need to survive replay
    determinism (`CLAUDE.md` rule 11: self-healing/durable behavior comes
    from explicit journal replay and idempotent effects, not
    implementation-language or ad hoc plugin machinery bolted onto the
    fold). At-most-once, CLI-local, unjournaled firing is the v1 contract;
    an operator who needs guaranteed delivery composes their own durable
    consumer (e.g. an `on_blocked` script that itself journals to a
    reliable queue) rather than orc guaranteeing it for them.

## Must not be confused with a plugin system or a supervisor

Nothing here makes orc a scheduler, event bus, or plugin host. An observer
cannot steer a run (no kernel semantics, per Purpose), cannot be composed
into chains or pipelines by orc itself, and its presence or absence never
changes what the journal contains. `SCN-017`'s "must not be confused with
a supervisor" caveat applies identically: dispatch holds no observer state
beyond the spawning pass and owns no observer lifecycle beyond the spawn
step itself (the bounded-lifetime enforcement travels with the spawned
process group, step 12 — it is never a later dispatch pass's job), and a
hook that never runs (because the process crashed first, step 14) is
indistinguishable from a hook that was never configured — the run's own
correctness never depends on which occurred.

## Containment and seat checks

- A `command` whose resolved first element is outside `cwd` is rejected
  before spawn with the same containment failure command assurance uses
  for its own script path (`SCN-015`).
- `command` must be a non-empty list of strings; a bare string (implying
  shell interpretation) is rejected — argv-array form only, never
  shell-interpolated, ever.
- `timeout_seconds`, when present, must be a non-negative number; anything
  else (negative, non-numeric) is rejected. Absent, it is 30.
- No observer configuration can cause a fact to be journaled, a state to
  change, or dispatch's exit code/stdout to differ from the identical
  dispatch with no `observers` key configured at all.

## Mutation check

Treating observer exit status/stdout/stderr as anything other than opaque
(letting it set state, appear in the journal, or change dispatch's exit
code/stdout), placing fact data in argv or environment instead of stdin,
accepting a bare shell string for `command`, allowing a `command` path to
escape `cwd`, blocking a dispatch pass on an observer's actual completion,
enforcing an observer's `timeout_seconds` from a later dispatch pass
instead of the spawned supervision, re-firing an observer for a replayed
(not newly appended) fact, or
journaling anything about a hook's dispatch or outcome makes this scenario
fail.

## Verifies

- `INV-014` — provider/operator vocabulary (the observer's own behavior,
  output, and exit status) stays outside core domain logic; the kernel
  never knows observers exist.
- `INV-020` — idempotent, deterministic replay: hooks firing only on
  newly-appended facts and never on replay keeps replay record-for-record
  identical whether or not any observer is configured, and keeps no
  wall-clock- or process-identity-derived state entering the journal.
- `CONTRACT-EXTENSIONS` — observer configuration and firing stay CLI-owned
  composition, never a core/canonical schema; nothing here is a registered
  extension because nothing here touches the journal.
- `SCN-015` — the containment, argv-list/no-shell, and process-group kill
  semantics observer hooks reuse from command assurance; the non-waiting
  delegation of that enforcement to the spawned group (step 12) is this
  scenario's own new clause.
- `SCN-017` — the complementary push/pull halves of the same "tell the
  caller the resting point moved" story; observer hooks add no kernel
  semantics, exactly as `SCN-017`'s wait mode adds none.
- `ADR-0005` — observer hooks are push-shaped (a CLI-local egress action
  taken after the kernel already recorded an observation), not a new
  pull-observation surface; they read no other process's lifecycle.
