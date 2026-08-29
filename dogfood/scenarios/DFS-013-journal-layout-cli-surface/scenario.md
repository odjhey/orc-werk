---
id: DFS-013
type: scenario
status: current
authority: informative
description: Fresh-session CLI journey across per-run journals, legacy reads, directory precedence, persisted-config resume, and pipe-safe output.
---

# DFS-013: issue-#55 journal-layout CLI surface

## Concern tags

`journal-layout`, `cli-output`, `idempotency`

## Intent

Exercise issue #55 as a fresh operator session rather than as isolated unit
checks: discover runs with bare `orc`, follow its status affordances, inspect
the new per-run artifacts alongside a legacy flat journal, resume from the
durable config using only a run id, select the journal root predictably, and
safely consume output from a pipe. This catches layout migrations that work
internally but leave discovery, recovery instructions, or agent-facing output
inconsistent.

## Setup

Run from the repository root. `DOGFOOD_SCRATCH` names a fresh disposable
directory outside the repository. The checked-in `config.json` deliberately
has no attempts, so the first dispatch rests pending and persists a config
that the journey then updates with an operator-recorded settlement.

```sh
export REPO_ROOT="$PWD"
export PYTHONPATH="$REPO_ROOT/src"
SCENARIO="$REPO_ROOT/dogfood/scenarios/DFS-013-journal-layout-cli-surface"
SCRATCH="$DOGFOOD_SCRATCH/DFS-013"
rm -rf "$SCRATCH"
mkdir -p "$SCRATCH/session"
cd "$SCRATCH/session"
```

## Commands

### 1. Fresh-session orientation and status affordances

```sh
# A fresh bare invocation is an index, not a usage error.
python3 -m orc_werk.cli

# Create a pending run in the default journal root.
python3 -m orc_werk.cli dispatch "exercise durable resume" \
  --config "$SCENARIO/config.json" --run-id dfs-013-resume
printf 'dispatch_exit=%s\n' "$?"

# Re-orient exactly as a newly resumed session would.
python3 -m orc_werk.cli
python3 -m orc_werk.cli status dfs-013-resume
```

### 2. Per-run layout, persisted config, and run-id-only re-dispatch

```sh
find .orc/dfs-013-resume -maxdepth 1 -type f -print | LC_ALL=C sort
python3 - <<'PY'
import json
from pathlib import Path
p = Path('.orc/dfs-013-resume/config.json')
cfg = json.loads(p.read_text())
cfg['attempts'] = {'work-1': [{
    'outcome': 'completed',
    'candidate': {'summary': 'DFS-013 settlement'},
    'assurance': {'verdict': 'accepted'},
}]}
p.write_text(json.dumps(cfg, indent=2) + '\n')
PY

# No intent and no --config: both come from durable run state/config.
python3 -m orc_werk.cli dispatch --run-id dfs-013-resume
python3 -m orc_werk.cli status dfs-013-resume
```

### 3. Mixed-layout discovery and legacy flat read-fallback

```sh
# Create a second accepted run, then reshape only that fixture to the legacy
# flat filename to simulate a journal written by a pre-#55 installation.
python3 - <<'PY'
import json
from pathlib import Path
Path('../legacy-config.json').write_text(json.dumps({
    'run_id': 'dfs-013-legacy',
    'attempts': {'work-1': [{
        'outcome': 'completed',
        'candidate': {'summary': 'legacy fixture'},
        'assurance': {'verdict': 'accepted'},
    }]},
}) + '\n')
PY
python3 -m orc_werk.cli dispatch "legacy layout fixture" \
  --config "$SCRATCH/legacy-config.json" --run-id dfs-013-legacy
mv .orc/dfs-013-legacy/journal.jsonl .orc/dfs-013-legacy.jsonl
rm -rf .orc/dfs-013-legacy

# A later write still uses the new layout.
python3 -m orc_werk.cli dispatch "new layout peer" \
  --config "$SCENARIO/config.json" --run-id dfs-013-new
printf 'dispatch_exit=%s\n' "$?"

python3 -m orc_werk.cli
python3 -m orc_werk.cli status dfs-013-legacy
python3 -m orc_werk.cli history .orc/dfs-013-legacy.jsonl --limit 1
```

### 4. Journal-directory precedence

```sh
mkdir -p default-case env-case flag-case

(cd default-case && env -u ORC_JOURNAL_DIR python3 -m orc_werk.cli dispatch \
  "default precedence" --config "$SCENARIO/config.json" --run-id default-run)
printf 'default_exit=%s\n' "$?"

env ORC_JOURNAL_DIR="$SCRATCH/env-root" python3 -m orc_werk.cli dispatch \
  "environment precedence" --config "$SCENARIO/config.json" --run-id env-run
printf 'env_exit=%s\n' "$?"

env ORC_JOURNAL_DIR="$SCRATCH/losing-env-root" python3 -m orc_werk.cli dispatch \
  "flag precedence" --config "$SCENARIO/config.json" --run-id flag-run \
  --journal "$SCRATCH/flag-root"
printf 'flag_exit=%s\n' "$?"

find "$SCRATCH" -name journal.jsonl -print | LC_ALL=C sort
```

### 5. Piped-output hygiene

```sh
python3 -m orc_werk.cli > "$SCRATCH/index.out"
python3 -m orc_werk.cli status dfs-013-resume > "$SCRATCH/status.out"
python3 -m orc_werk.cli report dfs-013-resume > "$SCRATCH/report.out"
python3 - <<'PY'
from pathlib import Path
for name in ('index.out', 'status.out', 'report.out'):
    data = (Path('..') / name).read_bytes()
    print(f'{name}: escape_bytes={data.count(bytes([27]))}')
    assert bytes([27]) not in data
PY
```

## Expected observable outcomes

1. The first bare `orc` exits `0` with a definitive empty state naming the
   resolved `.orc` directory. After dispatch, bare `orc` lists
   `dfs-013-resume`, its state, and a concrete next/status affordance; `status`
   exits `3`, identifies the submitted intent and pending work, and its `next:`
   block points at the durable absolute
   `.orc/dfs-013-resume/config.json`, not the checked-in source config.
2. The first dispatch exits `3`. The run directory contains
   `journal.jsonl`, `times.jsonl`, and `config.json`; it contains no legacy
   `.orc/dfs-013-resume.jsonl`. Run-id-only re-dispatch exits `0`, reports
   `state=ACCEPTED`, and status does likewise. The persisted config remains
   valid portable JSON.
3. Bare `orc` discovers both the new-layout `dfs-013-resume` run and flat
   `dfs-013-legacy.jsonl`; it does not classify sidecars as runs. Bare-id
   `status dfs-013-legacy` and explicit-path `history` both exit `0`, proving
   legacy read-fallback, and report the copied run as `ACCEPTED`. The
   subsequent write for `dfs-013-new` is under
   `.orc/dfs-013-new/journal.jsonl`, never a new flat journal.
4. Each precedence dispatch exits `3`. The only matching journal paths are
   `env-root/env-run/journal.jsonl`,
   `flag-root/flag-run/journal.jsonl`,
   `session/.orc/dfs-013-new/journal.jsonl`,
   `session/.orc/dfs-013-resume/journal.jsonl`, and
   `session/default-case/.orc/default-run/journal.jsonl`. No `env-case/.orc`, `flag-case/.orc`,
   or `losing-env-root` is created: explicit `--journal` beats the environment,
   which beats `./.orc`.
5. All three captured outputs print `escape_bytes=0`; the assertion passes.
   Printed journal/report/index paths remain plain absolute text when stdout
   is redirected or piped—no OSC-8 or other escape bytes leak into
   agent-consumed output.

## Judgment notes

Treat a technically resolvable but vague bare-index or `next:` message as
FRICTION: a fresh session should be able to locate the durable config and
copy the next command without knowing implementation details. Any new write
to the flat layout, failure to discover/read the legacy copy, precedence
inversion, missing durable-config resume, or escape byte in captured output
is a BUG.
