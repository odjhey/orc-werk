---
id: DFS-015
type: scenario
status: current
authority: informative
description: Observer hooks (SCN-018) fire-and-forget notification -- fires once on settlement, never on re-dispatch, bounded by timeout_seconds, and config-load-time rejection of an escaping command path.
---

# DFS-015: observer hooks

## Concern tags

`observers`

## Intent

`SCN-018` (issue #193) spawns operator-authored commands as fire-and-forget
notifications after specific Facts are journaled -- never a way to steer
the run. This scenario checks the four behaviors a human configuring an
observer actually depends on: the fact JSON really arrives on stdin exactly
once per newly-journaled trigger; an idempotent re-dispatch of an
already-terminal run fires nothing (mirroring `DFS-008`'s idempotency bar,
now for observers); a hung observer cannot slow down `dispatch` itself,
because `timeout_seconds` is enforced by a supervisor that travels with the
spawned process; and a `command[0]` that would resolve outside the
dispatching process's cwd is rejected at config-load time, before any
journal write -- never spawned and never silently ignored.

## Setup

Three config variants in this directory, all built on the same single-work
accepted-first-attempt shape as `DFS-001`:

- `config.json` -- `observers.on_settle.command` points at this directory's
  `notify-settle.sh` fixture (relative path, resolves against the
  dispatching process's cwd -- see `docs/cli/README.md`'s Observer hooks
  cwd footgun callout).
- `config-hung.json` -- same, but the observer is `hang.sh` (sleeps 300s)
  with `timeout_seconds: 1`.
- `config-escape.json` -- `observers.on_settle.command` is `["../outside-
  escape.sh"]`, a path that resolves outside the cwd `orc dispatch` is
  invoked from.

Both shell fixtures write their log line to `$DFS015_LOG` (falling back to
a same-directory default), so the scenario commands export `DFS015_LOG`
pointing into `$DOGFOOD_SCRATCH` -- the fixtures never write inside the
repo checkout.

## Commands

```sh
JOURNAL_DIR="$DOGFOOD_SCRATCH/DFS-015"
mkdir -p "$JOURNAL_DIR"

# Case 1: on_settle fires once, fact JSON on stdin.
export DFS015_LOG="$JOURNAL_DIR/notifications.log"
PYTHONPATH=src python3 -m orc_werk.cli dispatch "observer demo" \
  --config dogfood/scenarios/DFS-015-observer-hooks/config.json \
  --run-id demo-observers \
  --journal "$JOURNAL_DIR"
sleep 1
echo "--- notifications.log after first dispatch ---"
cat "$DFS015_LOG"

# Case 2: re-dispatch of the now-terminal run fires nothing.
LINES_BEFORE=$(wc -l < "$DFS015_LOG")
PYTHONPATH=src python3 -m orc_werk.cli dispatch "observer demo" \
  --config dogfood/scenarios/DFS-015-observer-hooks/config.json \
  --run-id demo-observers \
  --journal "$JOURNAL_DIR"
sleep 1
LINES_AFTER=$(wc -l < "$DFS015_LOG")
echo "notification lines before=$LINES_BEFORE after=$LINES_AFTER"

# Case 3: hung observer, timeout_seconds: 1 -- dispatch itself returns fast.
export DFS015_LOG="$JOURNAL_DIR/hang.log"
START=$(date +%s)
PYTHONPATH=src python3 -m orc_werk.cli dispatch "hung observer demo" \
  --config dogfood/scenarios/DFS-015-observer-hooks/config-hung.json \
  --run-id demo-hung-observer \
  --journal "$JOURNAL_DIR"
END=$(date +%s)
echo "hung-observer dispatch elapsed=$((END-START))s"
sleep 3
echo "--- hang.log (must stay absent -- supervisor kills before the 300s sleep returns) ---"
cat "$DFS015_LOG" 2>/dev/null || echo "(absent, as expected)"

# Case 4: command escaping cwd is ERR-VALIDATION at config-load time.
PYTHONPATH=src python3 -m orc_werk.cli dispatch "escape observer demo" \
  --config dogfood/scenarios/DFS-015-observer-hooks/config-escape.json \
  --run-id demo-escape-observer \
  --journal "$JOURNAL_DIR"
echo "escape exit=$?"
ls "$JOURNAL_DIR/demo-escape-observer" 2>/dev/null || echo "(no journal dir created)"
```

## Expected observable outcomes

- Case 1: `dispatch` exit `0`, `work work-1: state=ACCEPTED attempts=1
  candidate_fingerprint=fp-a6fd5c0647f98d41b530afc5` plus the `assurance
  recorded: work 'work-1' verdict=accepted extensions=[] (seq 16)` summary
  line. `notifications.log` gets exactly one line: `notified:
  {"data":{"execution_id":"exec-8e96c29f5ba50592","outcome":"completed",
  "work_id":"work-1"},"delivery_run_id":"demo-observers","extensions":{},
  "id":"FACT-EXEC-SETTLED","kind":"fact","schema_version":1,"seq":10}` --
  the triggering `FACT-EXEC-SETTLED` envelope verbatim, arrived on stdin.
- Case 2: `dispatch` exit `0`, no `assurance recorded:` summary line
  (nothing newly journaled, same as `DFS-008`), and `notifications.log`'s
  line count is unchanged (`before` equals `after`) -- the observer did not
  fire for replayed history.
- Case 3: `dispatch` exit `0` in well under a second (`elapsed=0s`) despite
  `hang.sh`'s 300-second sleep -- dispatch never waits on an observer's own
  completion. `hang.log` stays absent after the wait: the supervisor
  process kills the observer's whole process group at the 1-second
  `timeout_seconds` deadline, well before it could reach its post-sleep
  write.
- Case 4: `dispatch` exit `2`, canonical `ERR-VALIDATION` JSON naming the
  offending config path (`<config>.observers.on_settle.command`) and the
  resolved `cwd`, with `next: ["orc config-schema"]`. No journal directory
  is created for `demo-escape-observer` -- the rejection happens at
  config-load time, before any Fact would be journaled, exactly like
  command assurance's own load-time containment check.

## Judgment notes

Case 3 is the one most worth a human's attention: a naive reading of
"dispatch spawns observers" might expect `dispatch` to block for up to
`timeout_seconds`, which would make a hung observer *slow* rather than
merely *silent*. The scenario should make it legible that the timeout
bounds the observer's own lifetime, never `dispatch`'s. Case 1's fixed
fingerprint (`fp-a6fd5c0647f98d41b530afc5`) and `execution_id`
(`exec-8e96c29f5ba50592`) matching the CLI reference doc's own captured
transcript byte-for-byte is a useful determinism cross-check, not just
incidental.

## Verification

Executed against `master` (worktree `docs-dogfood-frictions`) on
2026-09-03 in a `/tmp` sandbox (`/tmp/dfs015-scratch`), run verbatim from
the repo root with `DOGFOOD_SCRATCH=/tmp/dfs015-scratch`: case 1 exit `0`
with the single expected `notifications.log` line, fingerprint and
`execution_id` matching `docs/cli/README.md`'s own captured Observer
hooks example exactly; case 2 exit `0` with `before=1 after=1` (zero new
notifications); case 3 exit `0` with `elapsed=0s` and `hang.log` absent
after a 3-second post-dispatch wait (confirmed no lingering `hang.sh`
process via `ps aux`); case 4 exit `2` with the exact `ERR-VALIDATION`
JSON above and no `demo-escape-observer` journal directory created.
Confirmed known-good.
