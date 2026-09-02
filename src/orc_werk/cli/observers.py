"""CLI-owned observer hooks -- config-declared push notifications fired
after specific canonical Facts are journaled (`SCN-018`, issue #193).

Observer hooks add **no kernel semantics** (`SCN-018` Purpose): this module
is the sole normative definition of firing, the same architectural slot as
the Beads mirror's write-only-observer posture (`INV-014`,
`docs/adapters/beads/mapping.md`'s "Direct CLI invocations" section) and
command assurance's containment/argv-only/process-group discipline
(`SCN-015`, `docs/adapters/command/mapping.md`). `src/orc_werk/core` and
`src/orc_werk/app` never import this module and never know observers exist
(`CLAUDE.md` rule 8).

## Trigger mapping

Exactly three triggers, each optional and independent
(`orc_werk.cli.config`'s `observers` schema):

- ``on_settle``  -- fires once per dispatch pass for each ``FACT-EXEC-SETTLED``
  newly appended that pass, regardless of outcome.
- ``on_verdict`` -- fires once per pass for each ``FACT-ASSURE-SETTLED``
  newly appended that pass, regardless of verdict. Verdict inheritance
  (`STATE-DELIVERY` item 8, ``orc_werk.core.reducer._inherit_verdict``)
  journals no new ``FACT-ASSURE-SETTLED`` for a re-observed candidate, so
  this trigger mapping alone -- keyed to the Fact actually appearing in
  ``new_records`` -- already excludes inherited verdicts with no special
  case needed.
- ``on_blocked`` -- fires once per pass for each ``FACT-WORK-BLOCKED``
  newly appended that pass.

`fire_observers` is called by ``orc_werk.cli.main._dispatch_pass`` with
that pass's own ``new_records`` (the same seq-filtered "durably appended by
this invocation" slice issues #147/#150 already compute for the assurance-
settlement print block) -- never the run's full replayed history. Firing in
``new_records``' own order (already seq-sorted, `JournalPort.history`) is
firing in seq order across triggers, satisfying `SCN-018` step 6 with no
extra bookkeeping: replay of pre-existing history never re-enters this
function's input at all, which is this module's entire at-most-once
replay-safety contract (`SCN-018` steps 13-15) -- there is no per-hook
"already fired" ledger anywhere, in memory or on disk, because there does
not need to be one.

## Fact delivery and fire-and-forget

The triggering fact's exact journal envelope (`kind`/`id`/`data`/`seq`/
`extensions`/...) is serialized as one JSON document and written to the
observer's standard input, then standard input is closed -- never argv,
never environment (`SCN-018` step 7, identical discipline to command
assurance's "Trust boundary and invocation" section). The command runs as
the configured argv list with ``shell=False``.

Dispatch spawns and does not wait: `fire_observers` returns as soon as
every eligible observer's spawn has been confirmed (or warned-and-skipped),
never blocking on an observer's own completion. Bounded lifetime enforcement
(the entry's `timeout_seconds`, default `DEFAULT_TIMEOUT_SECONDS`) is
delegated to a small stdlib supervisor process this module spawns in its
own session/process group (`_SUPERVISOR_SOURCE`): the supervisor spawns the
observer as its own child in a SECOND, separate session/process group, waits
up to the deadline, and -- on timeout -- kills the observer's whole group
with ``SIGKILL``, reaps it, and exits normally. The supervisor outlives the
kill (it never kills its own group), so the post-timeout state is
deterministic: observer group gone, no zombie left behind. Dispatch exiting
does not orphan that enforcement; it travels with the spawned supervision,
never a later dispatch pass's job (`SCN-018` step 12). See
`_SUPERVISOR_SOURCE`'s comment for the full kill-topology rationale
(verify-seat finding, PR #225 attempt 2) and the honest bounding scope: a
cooperative-but-hung observer is bounded; a hostile observer calling
``setsid()`` itself is out of SCN-018's scope.

A hook whose command spawn itself fails (missing or non-executable script)
is a one-line stderr warning, never a raised error -- the run is unaffected,
dispatch proceeds exactly as if the observer had not been configured
(`SCN-018` step 11). Containment (the resolved command path escaping the
effective cwd) is instead rejected eagerly at config-validation time, before
any journal write (`orc_werk.cli.config`'s `_validate_observers_config`,
mirroring command assurance's own load-time containment check) -- by the
time this module's `resolve_command_path` runs again here (a TOCTOU
re-check, the same discipline `CommandAssurance._resolve_script` applies at
its own inspect time), an escape should already be structurally impossible
for a config that loaded at all.

## Ambiguity: "the dispatch config's cwd"

`SCN-018`'s Given clause states relative `command` paths "resolve against
the dispatch config's cwd, matching command assurance" -- but unlike
command assurance (whose own `cwd` is a REQUIRED per-adapter config key),
the observers schema carries no `cwd` field of its own (`command`/
`timeout_seconds` are its only two keys, deliberately -- module docstring
of `orc_werk.cli.config`). This is a genuine gap the merged scenario leaves
open. The closest faithful reading, and this module's ruling: "the dispatch
config's cwd" is the CLI process's own actual working directory at
invocation time (`Path.cwd()`) -- the ordinary sense of "cwd" absent a more
specific field, and the one every example config's relative
`./scripts/...` path already assumes when `orc dispatch` is run from a repo
root. Recorded here and in the SCN-018 PR body's "Ambiguities encountered"
section rather than silently invented.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from orc_werk.core.facts import FACT_ASSURE_SETTLED, FACT_EXEC_SETTLED, FACT_WORK_BLOCKED
from orc_werk.core.serialization import KIND_FACT

DEFAULT_TIMEOUT_SECONDS = 30

# Trigger mapping (SCN-018 "Trigger mapping" steps 1-3) -- the sole source
# every fact-kind-to-trigger-key lookup in this module and in
# `orc_werk.cli.config` shares.
TRIGGER_BY_FACT_ID: Mapping[str, str] = {
    FACT_EXEC_SETTLED: "on_settle",
    FACT_ASSURE_SETTLED: "on_verdict",
    FACT_WORK_BLOCKED: "on_blocked",
}
OBSERVER_TRIGGERS = frozenset(TRIGGER_BY_FACT_ID.values())

# A small stdlib supervisor (`-c` script, no extra file to ship/resolve):
# reads the fact envelope from ITS OWN stdin (forwarded by this module,
# already closed once written -- see `_spawn_one`), spawns the configured
# observer command as its own child IN ITS OWN, SEPARATE session/process
# group (`start_new_session=True` on the OBSERVER's Popen below), and
# enforces `timeout_seconds` locally via
# `subprocess.communicate(timeout=...)`.
#
# Kill topology (verify-seat finding, PR #225 attempt 2): the supervisor
# OUTLIVES the kill. Supervisor and observer live in SEPARATE process
# groups precisely so that on timeout the supervisor can
# `killpg(observer's pgid, SIGKILL)` -- the observer's whole group, never
# its own -- then REAP the observer (`child.wait()`) and exit 0 normally.
# The earlier design (observer sharing the supervisor's group, timeout
# handled by killpg'ing that shared group, supervisor included) made the
# post-timeout teardown ordering uncontrolled and externally observable: a
# probe of the group could catch it half-torn-down, and a `killpg` probe
# against a reused/mixed-state pgid raises EPERM. With the supervisor
# surviving to reap, the post-timeout state is deterministic: observer
# group gone, no zombie (the supervisor reaped it), supervisor exits 0.
# `ProcessLookupError` (ESRCH -- group already gone, e.g. the observer
# exited between the timeout and the kill) is tolerated as success.
#
# `SCN-018` step 12's semantics are unchanged by this topology: enforcement
# still travels with the spawned supervision (the supervisor itself, still
# spawned detached in its own session by `_spawn_one` so dispatch exiting
# orphans nothing), dispatch still blocks only for spawn + the stdin
# handoff, and no later dispatch pass ever owns any observer lifecycle.
#
# Bounding scope, stated honestly: this bounds a COOPERATIVE-but-hung
# observer (SCN-018's contract). A hostile observer that itself calls
# setsid() escapes its own process group and therefore this group kill --
# SCN-018 does not require defeating a hostile observer, only bounding a
# hung one, and the config is operator-authored and PR-reviewed (Given
# section) precisely so hostility is out of scope.
#
# A spawn failure for the observer command itself (e.g. deleted between
# this module's pre-flight check and the supervisor's own spawn -- an
# inherent TOCTOU window, never widened by design) exits the supervisor
# quietly: observer spawn failure is CLI-warned synchronously by the
# pre-flight check in `_spawn_one` below, not asynchronously by the
# supervisor, which dispatch is never waiting on to hear back from.
_SUPERVISOR_SOURCE = """
import os, signal, subprocess, sys

def _main():
    timeout = float(sys.argv[1])
    cwd = sys.argv[2]
    command = sys.argv[3:]
    payload = sys.stdin.buffer.read()
    try:
        child = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=True,
        )
    except OSError:
        return
    try:
        child.communicate(input=payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # observer group already gone between timeout and kill
        child.wait()  # reap: no zombie survives the supervisor

_main()
"""


def resolve_command_path(command: Sequence[str], *, cwd: Path) -> Path:
    """Resolve `command[0]` against `cwd` (relative) or as-is (absolute),
    then require the result stay inside `cwd` by path containment -- the
    identical rule `SCN-015`'s "Containment and seat checks" section states
    for command assurance's own script, reused here per `SCN-018`'s
    "Containment and seat checks" section. Raises `ValueError` (never a
    canonical error itself -- callers translate: `orc_werk.cli.config`
    raises `ERR-VALIDATION` at config-load time; this module's own fire-time
    re-check, a TOCTOU precaution, folds it into the ordinary
    missing/non-executable stderr warning instead, since containment is
    already load-time-enforced and this is only ever a defensive re-check)."""
    cwd = cwd.resolve()
    configured = Path(command[0])
    resolved = (cwd / configured).resolve() if not configured.is_absolute() else configured.resolve()
    resolved.relative_to(cwd)  # raises ValueError when resolved is outside cwd
    return resolved


def _warn(trigger: str, message: str) -> None:
    print(f"observer: {trigger}: {message} -- run unaffected", file=sys.stderr)


def _spawn_one(entry: Mapping[str, Any], *, trigger: str, cwd: Path, record: Mapping[str, Any]) -> Optional["subprocess.Popen[bytes]"]:
    command = list(entry["command"])
    timeout = float(entry.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    try:
        resolved = resolve_command_path(command, cwd=cwd)
    except ValueError:
        _warn(trigger, f"command resolves outside cwd: {command[0]!r}")
        return None
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        _warn(trigger, f"command is missing or not executable: {resolved}")
        return None

    argv = [str(resolved), *command[1:]]
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    supervisor_argv = [sys.executable, "-c", _SUPERVISOR_SOURCE, str(timeout), str(cwd), *argv]
    try:
        proc = subprocess.Popen(
            supervisor_argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            start_new_session=True,
        )
    except OSError as exc:
        _warn(trigger, f"failed to spawn supervisor: {exc}")
        return None
    try:
        if proc.stdin is not None:
            proc.stdin.write(payload)
            proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    return proc


def fire_observers(
    observers_cfg: Optional[Mapping[str, Any]],
    *,
    new_records: Sequence[Mapping[str, Any]],
    cwd: Optional[Path] = None,
) -> list["subprocess.Popen[bytes]"]:
    """Fire every configured observer whose trigger matches a fact kind in
    `new_records` -- this dispatch pass's own newly-appended facts only,
    already in seq order. Returns the spawned (never waited-on) supervisor
    process handles, exposed only for test inspection; production callers
    (`orc_werk.cli.main._dispatch_pass`) ignore the return value -- dispatch
    itself never depends on whether or when a spawned observer exits
    (`SCN-018` step 9)."""
    if not observers_cfg:
        return []
    effective_cwd = (cwd or Path.cwd()).resolve()
    handles: list["subprocess.Popen[bytes]"] = []
    for record in new_records:
        if record.get("kind") != KIND_FACT:
            continue
        trigger = TRIGGER_BY_FACT_ID.get(record.get("id"))
        if trigger is None:
            continue
        entry = observers_cfg.get(trigger)
        if not entry:
            continue
        handle = _spawn_one(entry, trigger=trigger, cwd=effective_cwd, record=record)
        if handle is not None:
            handles.append(handle)
    return handles


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "OBSERVER_TRIGGERS",
    "TRIGGER_BY_FACT_ID",
    "fire_observers",
    "resolve_command_path",
]
