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
    from pathlib import Path

    WORLD = Path(os.environ["ORC_NM_STUB_WORLD"])
    STATE_PATH = WORLD / "runs.json"


    def _load():
        if not STATE_PATH.exists():
            return {"runs": {}, "active_run_id": None, "next_head": None, "counter": 0, "branch": "stub-branch"}
        return json.loads(STATE_PATH.read_text())


    def _save(state):
        STATE_PATH.write_text(json.dumps(state))


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


    def cmd_axi_run(intent):
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
            cmd_axi_run(intent)
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
        self._state_path.write_text(json.dumps(dict(state)))

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
