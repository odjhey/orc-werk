"""Fake `acpx` executable + world-state helper for `AcpExecution`'s
stub-acpx conformance/unit tests (`TASK-M1-005` acceptance item).

No real `acpx`/Node/`pi-acp` dependency: the fake binary is a small
self-contained Python script (stdlib only) placed on `PATH` for the
subprocess calls `AcpExecution` makes, driven entirely by a JSON
"world" directory this module also manages. It reproduces only the
narrow slice of real `acpx` behavior `AcpExecution` actually depends on
(`sessions ensure`, `set`, the default prompt-submit form, `sessions
show`, `status`, `cancel`) -- not a general ACP/acpx simulator.

Two session-state concepts, matching the real CLI's split (recorded in
`docs/adapters/acp/mapping.md`):

- the **session record** (`sessions/<name>.json`, this module's own control
  file, standing in for `acpx.session.v1`/`sessions show`'s output);
- the **raw event-log stream** (`sessions/<name>.stream.ndjson`), the only
  place a turn's `stopReason` ever appears -- `AcpExecution.inspect()`
  reads this file directly, exactly as it would the real one.

A turn's settlement is revealed gradually across repeated `sessions show`
calls, walking the scripted `states` list (`["running", "settled"]`, ...)
exactly the way `orc_werk.adapters.scripted.execution.ScriptedExecution`
walks its own script on successive `inspect()` calls -- this is what lets
`test_conf_exec_003_inspect_distinguishes_running_from_settled` pass
against this stub the same way it does against the scripted double.
"""

from __future__ import annotations

import json
import os
import stat
import textwrap
from pathlib import Path
from typing import Any, Mapping, Optional

_STUB_SOURCE = textwrap.dedent(
    '''
    #!/usr/bin/env python3
    """Fake `acpx` for AcpExecution's stub-acpx tests. See
    tests/conformance/support_acpx_stub.py for the protocol this
    implements and why."""
    import hashlib
    import json
    import os
    import sys
    from pathlib import Path

    WORLD = Path(os.environ["ORC_ACPX_STUB_WORLD"])
    SESSIONS_DIR = WORLD / "sessions"
    PENDING_DIR = WORLD / "pending"


    def _rec_path(name):
        return SESSIONS_DIR / f"{name}.json"


    def _stream_path(name):
        return SESSIONS_DIR / f"{name}.stream.ndjson"


    def _load(name):
        path = _rec_path(name)
        if not path.exists():
            return None
        return json.loads(path.read_text())


    def _save(name, rec):
        _rec_path(name).write_text(json.dumps(rec))


    def _stop_reason_for(entry):
        outcome = entry.get("outcome", "completed")
        return {"completed": "end_turn", "cancelled": "cancelled"}.get(outcome, "stub-refusal")


    def _append_stream(name, obj):
        with _stream_path(name).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj) + "\\n")


    def _emit(obj, code=0):
        sys.stdout.write(json.dumps(obj) + "\\n")
        sys.exit(code)


    def _fail(message, code=1, usage=False):
        prefix = "error: unknown option" if usage else "error"
        sys.stderr.write(f"{prefix}: {message}\\n")
        sys.exit(code)


    def _parse_global(argv):
        i = 0
        while i < len(argv):
            tok = argv[i]
            if tok == "--format":
                i += 2
                continue
            if tok == "--json-strict":
                i += 1
                continue
            if tok == "--ttl":
                i += 2
                continue
            if tok == "--cwd":
                i += 2
                continue
            if tok == "--approve-all":
                i += 1
                continue
            if tok == "--non-interactive-permissions":
                i += 2
                continue
            break
        return argv[i:]


    def cmd_ensure(name):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        existing = _load(name)
        created = existing is None
        if created:
            sid = f"sid-{hashlib.sha256(name.encode()).hexdigest()[:24]}"
            rec = {
                "id": sid,
                "script": [],
                "turns_submitted": 0,
                "turns_materialized": 0,
                "current_turn_show_calls": 0,
                "daemon_dead": False,
                "force_daemon_dead": False,
                "last_agent_exit_code": None,
                "last_agent_exit_signal": None,
                "pid_alive": True,
                "has_lease": True,
                "closed": False,
                # Issue #57 cross-process idempotency signal: null/empty
                # until the first prompt is queued, matching real acpx's
                # `sessions show` shape (probed against acpx@0.13.1/
                # pi-acp@0.0.31, docs/adapters/acp/mapping.md).
                "last_prompt_at": None,
                "messages": [],
                "available_models": [
                    "openai-codex/gpt-5.6-luna",
                    "openai-codex/gpt-5.6-sol",
                    "vendor/luna-preview",
                ],
                "current_model_id": "openai-codex/gpt-5.6-sol",
                "config_sets": [],
            }
            pending = PENDING_DIR / f"{name}.json"
            if pending.exists():
                pending_data = json.loads(pending.read_text())
                rec["script"] = pending_data.get("script", [])
                rec["available_models"] = pending_data.get(
                    "available_models", rec["available_models"]
                )
                pending.unlink()
            _stream_path(name).write_text("")
            _save(name, rec)
        else:
            rec = existing
            sid = rec["id"]
        _emit(
            {
                "action": "session_ensured",
                "created": created,
                "acpxRecordId": sid,
                "acpxSessionId": sid,
                "name": name,
            }
        )


    def cmd_show(name):
        rec = _load(name)
        if rec is None:
            _fail("No acpx session found", code=4)
        rec["current_turn_show_calls"] = rec.get("current_turn_show_calls", 0) + 1
        if not rec.get("force_daemon_dead") and rec["turns_materialized"] < rec["turns_submitted"]:
            entry = rec["script"][rec["turns_materialized"]]
            states = entry.get("states", ["settled"])
            idx = min(rec["current_turn_show_calls"] - 1, len(states) - 1)
            if states[idx] == "settled":
                next_id = rec["turns_materialized"] + 10
                _append_stream(
                    name,
                    {"jsonrpc": "2.0", "id": next_id, "result": {"stopReason": _stop_reason_for(entry)}},
                )
                rec["turns_materialized"] += 1
                rec["current_turn_show_calls"] = 0
        _save(name, rec)
        last_exit_code = rec.get("last_agent_exit_code")
        _emit(
            {
                "schema": "acpx.session.v1",
                "acpxRecordId": rec["id"],
                "acpSessionId": rec["id"],
                "name": name,
                "closed": rec["closed"],
                "eventLog": {"active_path": str(_stream_path(name))},
                "lastAgentExitCode": last_exit_code,
                "lastAgentExitSignal": rec.get("last_agent_exit_signal"),
                "acpx": {
                    "current_model_id": rec["current_model_id"],
                    "available_models": rec["available_models"],
                },
                # Issue #57 cross-process idempotency signal (see
                # cmd_prompt): null/[] until a prompt is queued, then set
                # -- mirrors real acpx's lastPromptAt/messages fields.
                "lastPromptAt": rec.get("last_prompt_at"),
                "messages": rec.get("messages", []),
            }
        )


    def cmd_status(name):
        rec = _load(name)
        if rec is None or rec.get("closed"):
            _emit({"action": "status_snapshot", "status": "no-session", "summary": "no active session"})
        if rec.get("force_daemon_dead") or rec.get("daemon_dead"):
            snapshot = {
                "action": "status_snapshot",
                "status": "dead",
                "hasLease": rec.get("has_lease"),
                "exitCode": rec.get("last_agent_exit_code"),
                "signal": rec.get("last_agent_exit_signal"),
                "summary": "queue owner unavailable",
            }
            if not rec.get("omit_pid_alive"):
                snapshot["pidAlive"] = rec.get("pid_alive")
            _emit(snapshot)
        _emit({
            "action": "status_snapshot",
            "status": "alive",
            "pidAlive": rec.get("pid_alive"),
            "hasLease": rec.get("has_lease"),
            "summary": "queue owner healthy",
        })


    def cmd_cancel(name):
        rec = _load(name)
        if rec is None:
            _emit({"action": "cancel_result", "cancelled": False})
        if rec["turns_materialized"] < rec["turns_submitted"] and not rec.get("force_daemon_dead"):
            next_id = rec["turns_materialized"] + 10
            _append_stream(name, {"jsonrpc": "2.0", "id": next_id, "result": {"stopReason": "cancelled"}})
            rec["turns_materialized"] += 1
            rec["current_turn_show_calls"] = 0
            _save(name, rec)
            _emit({"action": "cancel_result", "cancelled": True})
        _emit({"action": "cancel_result", "cancelled": False, "summary": "nothing to cancel"})


    def cmd_set(key, value, name):
        rec = _load(name)
        if rec is None:
            _fail(f"no session {name}", code=1)
        rec.setdefault("config_sets", []).append({"key": key, "value": value})
        if key == "model" and value in rec["available_models"]:
            rec["current_model_id"] = value
        _save(name, rec)
        _emit({"action": "config_set", "configId": key, "value": value, "acpxRecordId": rec["id"]})


    def cmd_prompt(name, prompt):
        rec = _load(name)
        if rec is None:
            _fail("No acpx session found", code=4)
        rec["turns_submitted"] += 1
        rec["current_turn_show_calls"] = 0
        # Issue #57 signal: set as soon as the prompt is queued, before
        # the turn settles -- matches real acpx (lastPromptAt/messages
        # both update on submit, not on completion; see mapping.md).
        rec["last_prompt_at"] = f"stub-prompt-{rec['turns_submitted']}"
        rec.setdefault("messages", []).append({"role": "user", "text": prompt})
        _save(name, rec)
        _emit({"action": "prompt_queued", "acpxRecordId": rec["id"], "requestId": f"stub-{rec[\'turns_submitted\']}"})


    def main():
        rest = _parse_global(sys.argv[1:])
        if not rest:
            _fail("missing agent subcommand", code=2, usage=True)
        rest = rest[1:]  # drop the agent token (e.g. "pi")
        if not rest:
            _fail("missing command", code=2, usage=True)
        head = rest[0]
        if head == "sessions":
            sub = rest[1]
            if sub == "ensure":
                name = rest[rest.index("-s") + 1]
                cmd_ensure(name)
            elif sub == "show":
                cmd_show(rest[2])
            else:
                _fail(f"unknown option for sessions {sub}", code=1, usage=True)
        elif head == "status":
            name = rest[rest.index("-s") + 1]
            cmd_status(name)
        elif head == "cancel":
            name = rest[rest.index("-s") + 1]
            cmd_cancel(name)
        elif head == "set":
            key, value = rest[1], rest[2]
            name = rest[rest.index("-s") + 1]
            cmd_set(key, value, name)
        elif head == "-s":
            name = rest[1]
            tail = rest[2:]
            if "--no-wait" in tail:
                tail = [t for t in tail if t != "--no-wait"]
            if not tail:
                _fail("missing prompt", code=1, usage=True)
            cmd_prompt(name, tail[-1])
        else:
            _fail(f"unknown option {head!r}", code=1, usage=True)


    if __name__ == "__main__":
        main()
    '''
).lstrip("\n")


def write_stub_acpx(bin_dir: Path) -> Path:
    """Write the fake `acpx` script into `bin_dir` (created if needed),
    make it executable, and return its path."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script_path = bin_dir / "acpx"
    script_path.write_text(_STUB_SOURCE)
    mode = script_path.stat().st_mode
    script_path.chmod(mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script_path


class AcpxStubWorld:
    """One isolated stub-`acpx` world: a scratch directory holding the
    fake session records/streams, plus the `env()` an `AcpExecution`
    instance needs to reach the fake binary and this world's state
    instead of any real `acpx` install."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.bin_dir = root / "bin"
        self.world_dir = root / "world"
        self.world_dir.mkdir(parents=True, exist_ok=True)
        (self.world_dir / "sessions").mkdir(parents=True, exist_ok=True)
        (self.world_dir / "pending").mkdir(parents=True, exist_ok=True)
        write_stub_acpx(self.bin_dir)

    def env(self) -> dict[str, str]:
        return {
            "PATH": f"{self.bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "ORC_ACPX_STUB_WORLD": str(self.world_dir),
            # Preserve HOME/etc. so Python's own startup (the stub is a
            # `python3` script) works normally in minimal test sandboxes.
            "HOME": os.environ.get("HOME", ""),
        }

    def seed_models(self, session_name: str, model_ids: list[str]) -> None:
        """Set the model ids advertised by a session before it is ensured."""
        pending_path = self.world_dir / "pending" / f"{session_name}.json"
        pending = json.loads(pending_path.read_text()) if pending_path.exists() else {}
        pending["available_models"] = model_ids
        pending_path.write_text(json.dumps(pending))

    def seed_script(self, session_name: str, script: list[Mapping[str, Any]]) -> None:
        """Queue the scripted turn outcome(s) for a session that may not
        exist yet -- consumed by the fake `acpx`'s `sessions ensure`
        handler the first time it creates that session's record."""
        pending_path = self.world_dir / "pending" / f"{session_name}.json"
        pending = json.loads(pending_path.read_text()) if pending_path.exists() else {}
        pending["script"] = list(script)
        pending_path.write_text(json.dumps(pending))

    def append_script(self, session_name: str, entry: Mapping[str, Any]) -> None:
        """Append one more scripted turn outcome to an ALREADY-created
        session (for CAP-EXEC-SEND follow-up-turn tests)."""
        rec = self.session_record(session_name)
        assert rec is not None, f"session {session_name!r} does not exist yet"
        rec["script"].append(dict(entry))
        self._save(session_name, rec)

    def set_script_entry(self, session_name: str, index: int, entry: Mapping[str, Any]) -> None:
        """Overwrite one already-seeded scripted turn entry in place (test
        support for exercising a specific `stopReason` mapping without a
        fresh `start()`)."""
        rec = self.session_record(session_name)
        assert rec is not None, f"session {session_name!r} does not exist yet"
        rec["script"][index] = dict(entry)
        self._save(session_name, rec)

    def set_dead_status(
        self,
        session_name: str,
        *,
        pid_alive: Any = None,
        has_lease: bool = True,
        omit_pid_alive: bool = False,
    ) -> None:
        """Make status emit an acpx dead snapshot with configurable owner health."""
        rec = self.session_record(session_name)
        assert rec is not None, f"session {session_name!r} does not exist yet"
        rec["daemon_dead"] = True
        rec["pid_alive"] = pid_alive
        rec["omit_pid_alive"] = omit_pid_alive
        rec["has_lease"] = has_lease
        self._save(session_name, rec)

    def set_agent_exit(
        self, session_name: str, *, exit_code: Optional[int], signal: Optional[str] = None
    ) -> None:
        """Record sessions show's durable agent-exit evidence."""
        rec = self.session_record(session_name)
        assert rec is not None, f"session {session_name!r} does not exist yet"
        rec["last_agent_exit_code"] = exit_code
        rec["last_agent_exit_signal"] = signal
        self._save(session_name, rec)

    def mark_daemon_dead(self, session_name: str, *, exit_code: int = 1) -> None:
        """Directly force a session's daemon into the "confirmed dead,
        nothing more will ever be recorded" state -- the deterministic
        unobservability signal (`docs/reports/2026-08-28-acpx-pi-spike.md`,
        the task card's abandonment ruling)."""
        rec = self.session_record(session_name)
        assert rec is not None, f"session {session_name!r} does not exist yet"
        rec["force_daemon_dead"] = True
        rec["pid_alive"] = False
        rec["last_agent_exit_code"] = exit_code
        self._save(session_name, rec)

    def append_stream(self, session_name: str, obj: Mapping[str, Any]) -> None:
        """Append one raw JSON-RPC-shaped line directly to a session's
        stream file -- the same file `AcpExecution.inspect()`'s
        `_scan_stream_terminal_results` reads. Exposed for tests that
        want to simulate specific raw stream shapes (e.g. a
        `session/load` line with no `stopReason`) independent of the
        stub's own `sessions show`-driven states-list progression.

        `force_settle` (a same-shaped direct-mutation helper for
        sidestepping poll-count-driven settlement, `mark_daemon_dead`'s
        analogue for the completed-turn case) lived here through issue
        #57's fix; removed once `AcpExecution.start()` became cross-
        process idempotent (`docs/adapters/acp/mapping.md` "Idempotency
        behavior") and `tests/scenarios/test_cli_acp_wiring.py`'s smoke
        test no longer needed it -- ordinary `sessions show`-driven
        states-list progression across dispatch processes works again
        now that a fresh process's replay no longer resubmits and resets
        it. See that fix's PR for the trace if this needs reintroducing."""
        path = self.world_dir / "sessions" / f"{session_name}.stream.ndjson"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(obj)) + "\n")

    def session_record(self, session_name: str) -> Optional[dict[str, Any]]:
        path = self.world_dir / "sessions" / f"{session_name}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def prompt_submission_count(self, session_name: str) -> int:
        """How many times the fake `acpx`'s prompt-submit form (`-s
        <name> --no-wait <prompt>` -> `cmd_prompt`) has actually run
        against this session -- the issue #57 regression assertion: two
        separate `AcpExecution` instances racing the same idempotency key
        must drive this to exactly 1, never 2. Returns 0 for a session
        that does not exist yet (mirrors `session_record`'s `None`-for-
        missing convention rather than raising)."""
        rec = self.session_record(session_name)
        return 0 if rec is None else rec.get("turns_submitted", 0)

    def _save(self, session_name: str, rec: Mapping[str, Any]) -> None:
        path = self.world_dir / "sessions" / f"{session_name}.json"
        path.write_text(json.dumps(dict(rec)))


__all__ = ["AcpxStubWorld", "write_stub_acpx"]
