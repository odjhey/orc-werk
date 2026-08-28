"""Fake `no-mistakes` executable + world-state helper for
`NoMistakesAssurance`'s stub-subprocess conformance/unit tests
(`TASK-M2-001` acceptance item), mirroring `support_acpx_stub.py`'s
pattern for `AcpExecution`.

No real `no-mistakes` install/daemon/agent required: the fake binary is a
small self-contained Python script (stdlib only) placed on `PATH`,
implementing only the narrow slice of `no-mistakes axi` behavior
`NoMistakesAssurance` actually depends on (`axi run --intent`, `axi status
[--run <id>]`) -- not a general `no-mistakes` simulator. It emits real
TOON-shaped text (the same `orc_werk.adapters.no_mistakes.toon.parse_toon`
the adapter uses parses this output identically to the real CLI's), so
these tests exercise the actual subprocess + TOON-parsing boundary, not a
mocked-out shortcut.

World state (one JSON file per world, `runs.json`): a dict of run records
plus an `active_run_id` pointer and a `next_head` the next `axi run` will
be stamped with (`NoMistakesStubWorld.set_next_head`) -- tests use this to
control whether a freshly-`request()`-ed candidate's head matches the
stub's "currently active" run, exercising the adapter's cross-process
idempotency / stale-run-mismatch logic the same way `AcpxStubWorld.
mark_daemon_dead` exercises `AcpExecution`'s unobservability branch.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

_STUB_SOURCE = textwrap.dedent(
    '''
    #!/usr/bin/env python3
    """Fake `no-mistakes` for NoMistakesAssurance's stub tests. See
    tests/conformance/support_no_mistakes_stub.py for the protocol this
    implements and why."""
    import json
    import os
    import sys
    import tempfile
    import time
    from pathlib import Path

    WORLD = Path(os.environ["ORC_NM_STUB_WORLD"])
    STATE_PATH = WORLD / "runs.json"

    EMPTY_STATE = {"runs": {}, "active_run_id": None, "next_head": None, "counter": 0, "branch": "stub-branch"}


    def _load():
        # PR #80 fix round, finding A: reads must tolerate a concurrent
        # writer. _save below is atomic (os.replace), so a torn read
        # should no longer be observable on POSIX -- the brief retry loop
        # is defense-in-depth only (e.g. a hypothetical filesystem where
        # replace is not atomic for readers).
        for _attempt in range(20):
            if not STATE_PATH.exists():
                return dict(EMPTY_STATE)
            try:
                return json.loads(STATE_PATH.read_text())
            except ValueError:
                time.sleep(0.01)
        return dict(EMPTY_STATE)


    def _save(state):
        # PR #80 fix round, finding A: a plain write_text here was
        # non-atomic -- the adapter's immediate post-spawn `axi status`
        # poll races this detached `axi run` child's write and could
        # observe a torn/partial runs.json (reproduced by the verifier at
        # ~5% per request(): torn json.loads -> stub exit 1 ->
        # ERR-TEMPORARY -> flaky check.sh). Write to a temp file in the
        # same directory, then os.replace() onto runs.json -- atomic on
        # POSIX, so a reader always sees either the old or the new
        # complete document, never a partial write.
        fd, tmp_path = tempfile.mkstemp(dir=str(STATE_PATH.parent), prefix=".runs-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(json.dumps(state))
            os.replace(tmp_path, STATE_PATH)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


    def _csv_field(value):
        text = str(value)
        if any(c in text for c in (",", '"', "\\n")):
            escaped = text.replace("\\\\", "\\\\\\\\").replace('"', '\\\\"')
            return f'"{escaped}"'
        return text


    def _emit_status(rec):
        lines = []
        lines.append("run:")
        lines.append(f'  id: "{rec["id"]}"')
        lines.append(f'  branch: {rec["branch"]}')
        lines.append(f'  status: {rec["status"]}')
        gate = rec.get("gate")
        if gate is not None:
            lines.append("gate:")
            lines.append(f'  step: {gate["step"]}')
            lines.append("  status: awaiting_approval")
            findings = gate.get("findings", [])
            lines.append(f'  findings[{len(findings)}]{{id,severity,file,action,description}}:')
            for f in findings:
                row = ",".join(
                    _csv_field(f.get(col, ""))
                    for col in ("id", "severity", "file", "action", "description")
                )
                lines.append(f"    {row}")
        outcome = rec.get("outcome")
        lines.append("branch_sync:")
        lines.append("  pipeline:")
        lines.append(f'    submitted_head: {rec.get("head") or ""}')
        lines.append("  local:")
        lines.append(f'    head: {rec.get("head") or ""}')
        if outcome is not None:
            lines.append(f"outcome: {outcome}")
        sys.stdout.write("\\n".join(lines) + "\\n")


    def cmd_axi_run(intent, skip):
        state = _load()
        state["counter"] += 1
        run_id = f"STUB{state[\'counter\']:022d}"
        state["runs"][run_id] = {
            "id": run_id,
            "branch": state.get("branch") or "stub-branch",
            "status": "running",
            "head": state.get("next_head"),
            "outcome": None,
            "gate": None,
            # PR #80 fix round, finding B: record the exact --skip value
            # this invocation carried (comma-split, [] when absent) so a
            # test can assert the adapter's mechanical never-push
            # guarantee -- that every spawn passes `--skip push`.
            "skip": [s for s in (skip or "").split(",") if s],
        }
        state["active_run_id"] = run_id
        _save(state)
        sys.exit(0)


    def cmd_axi_status(run_id):
        state = _load()
        if run_id is not None:
            rec = state["runs"].get(run_id)
            if rec is None:
                sys.stderr.write("error: no run found matching that id\\n")
                sys.exit(1)
            _emit_status(rec)
            sys.exit(0)
        active_id = state.get("active_run_id")
        rec = state["runs"].get(active_id) if active_id else None
        if rec is None:
            sys.stdout.write("no active run\\n")
            sys.exit(0)
        _emit_status(rec)
        sys.exit(0)


    def main():
        argv = sys.argv[1:]
        if not argv or argv[0] != "axi":
            sys.stderr.write("error: unknown command\\n")
            sys.exit(2)
        rest = argv[1:]
        if not rest:
            sys.stderr.write("error: missing axi subcommand\\n")
            sys.exit(2)
        sub = rest[0]
        if sub == "run":
            if "--intent" not in rest:
                sys.stderr.write("error: --intent is required\\n")
                sys.exit(1)
            intent = rest[rest.index("--intent") + 1]
            skip = rest[rest.index("--skip") + 1] if "--skip" in rest else None
            cmd_axi_run(intent, skip)
        elif sub == "status":
            run_id = None
            if "--run" in rest:
                run_id = rest[rest.index("--run") + 1]
            cmd_axi_status(run_id)
        else:
            sys.stderr.write(f"error: unknown axi subcommand {sub!r}\\n")
            sys.exit(1)


    if __name__ == "__main__":
        main()
    '''
).lstrip("\n")


def write_stub_no_mistakes(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script_path = bin_dir / "no-mistakes"
    script_path.write_text(_STUB_SOURCE)
    mode = script_path.stat().st_mode
    script_path.chmod(mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script_path


class NoMistakesStubWorld:
    """One isolated stub-`no-mistakes` world: a scratch directory holding
    the fake run records, plus the `env()`/`repo_path` a `NoMistakesAssurance`
    instance needs to reach the fake binary instead of any real install.
    `repo_path` doubles as the fake CLI's cwd -- the stub does not care
    what is actually in it (unlike real `no-mistakes`, which reviews real
    git state there), so a plain empty directory is sufficient."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.bin_dir = root / "bin"
        self.repo_dir = root / "repo"
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        write_stub_no_mistakes(self.bin_dir)
        self._state_path = self.root / "world" / "runs.json"
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._save(
            {"runs": {}, "active_run_id": None, "next_head": None, "counter": 0, "branch": "stub-branch"}
        )

    @property
    def repo_path(self) -> str:
        return str(self.repo_dir)

    def env(self) -> dict[str, str]:
        return {
            "PATH": f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "ORC_NM_STUB_WORLD": str(self.root / "world"),
            "HOME": os.environ.get("HOME", ""),
        }

    def _load(self) -> dict[str, Any]:
        return json.loads(self._state_path.read_text())

    def _save(self, state: Mapping[str, Any]) -> None:
        # PR #80 fix round, finding A: same atomic-replace discipline as
        # the fake CLI's own _save (see _STUB_SOURCE) -- a detached `axi
        # run` child spawned by the adapter can still be in flight when a
        # test mutates world state, so this writer must not be tearable
        # either.
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._state_path.parent), prefix=".runs-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(json.dumps(dict(state)))
            os.replace(tmp_path, self._state_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def set_next_head(self, head: Optional[str]) -> None:
        """Every subsequent `axi run` invocation stamps its new run with
        this head, until changed again -- lets a test control whether a
        freshly-spawned run's observed head matches a candidate's
        `subject_identity['head_sha']`."""
        state = self._load()
        state["next_head"] = head
        self._save(state)

    def set_branch(self, branch: str) -> None:
        state = self._load()
        state["branch"] = branch
        self._save(state)

    def active_run_id(self) -> Optional[str]:
        return self._load().get("active_run_id")

    def run_count(self) -> int:
        """How many times the fake `axi run` has actually created a new
        run record -- the cross-process idempotency assertion (mirrors
        `AcpxStubWorld.prompt_submission_count`): a candidate whose run is
        already active must never cause a second spawn."""
        return len(self._load()["runs"])

    def run_skip_args(self, run_id: str) -> list[str]:
        """The exact `--skip` step list the fake `axi run` invocation that
        created `run_id` carried (comma-split; `[]` when the flag was
        absent) -- the finding-B mechanical never-push assertion: every
        adapter spawn must include `push` here."""
        return list(self._load()["runs"][run_id].get("skip", []))

    def set_gate(self, run_id: str, *, step: str, findings: Sequence[Mapping[str, Any]]) -> None:
        state = self._load()
        rec = state["runs"][run_id]
        rec["gate"] = {"step": step, "findings": [dict(f) for f in findings]}
        self._save(state)

    def clear_gate(self, run_id: str) -> None:
        state = self._load()
        state["runs"][run_id]["gate"] = None
        self._save(state)

    def set_outcome(self, run_id: str, outcome: str) -> None:
        """Settle the run terminally with a top-level `outcome:`
        (`passed`/`failed`), clearing any gate -- mirrors what real
        `no-mistakes` shows once a run finishes past every gate."""
        state = self._load()
        rec = state["runs"][run_id]
        rec["status"] = "completed"
        rec["outcome"] = outcome
        rec["gate"] = None
        self._save(state)

    def set_status(self, run_id: str, status: str) -> None:
        """Force a raw `run.status` value directly (e.g. `cancelled`,
        `aborted`) without an `outcome:` -- the terminal-without-a-verdict
        shapes real `no-mistakes axi abort` produces."""
        state = self._load()
        rec = state["runs"][run_id]
        rec["status"] = status
        rec["gate"] = None
        self._save(state)


__all__ = ["NoMistakesStubWorld", "write_stub_no_mistakes"]
