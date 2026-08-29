"""AcpExecution (`TASK-M1-005`): `PORT-EXECUTION` adapter over the `acpx`
CLI (an Agent Client Protocol client), driving Pi (`acpx pi`) as its first
configured agent.

All `acpx`/ACP vocabulary -- CLI flags, session-scope keys, JSON-RPC
`stopReason` values, `acpx.session.v1` field names, process exit codes --
stays in this module and `docs/adapters/acp/mapping.md`, per `INV-014` and
`docs/adapters/README.md`. This module is the concrete basis for the
subprocess pattern recorded empirically in
`docs/reports/2026-08-28-acpx-pi-spike.md` and normatively required by
`docs/delivery/task-cards/TASK-M1-005-acp-adapter.md`.

Design summary (full rationale: `docs/adapters/acp/mapping.md`):

- Sessions are always explicit and named (`-s <name>`), never anonymous;
  the name is a deterministic digest of the caller's idempotency key
  (`INV-020`) -- never randomness or wall-clock time.
- `start()` uses `sessions ensure` (idempotent create-or-attach, never
  `sessions new`) then queues the prompt with `--no-wait` and returns
  immediately -- it never blocks the calling (orchestrator) process on a
  turn's completion. This matches the orchestrator's poll model: `start()`
  must be cheap and `inspect()` must be able to observe settlement from a
  *different* process (crash recovery), so both the "normal poll" and
  "recovering after my own submitter died" cases are the exact same code
  path in `inspect()` -- there is no separate blocking-wait code path to
  keep in sync.
- `start()` is idempotent **across processes**, not just within one
  (issue #57): `Orchestrator._reconcile_ports` replays `FX-START-
  EXECUTION` -- i.e. calls `start()` again -- from a fresh adapter
  instance on every ordinary `orc dispatch`, so an in-process-only
  duplicate-submit guard resubmits the prompt on every poll of a
  still-running attempt. After `sessions ensure`, `start()` consults
  `sessions show`'s durable session record (`_session_already_prompted`:
  `lastPromptAt`/`messages` presence, never a wall-clock comparison) and
  skips the submit step -- returning the same stable `Execution` ref --
  whenever this attempt's session has already seen a prompt, from any
  process. See `docs/adapters/acp/mapping.md` "Idempotency behavior" for
  the durable-signal choice and its failure modes.
- `inspect()` derives settlement **only** from a recorded `result.stopReason`
  in the session's raw JSON-RPC event-log stream (`sessions show`'s
  `eventLog.active_path`) -- never from `acpx status`/`sessions show`'s
  process-liveness fields (`status`/`lastAgent*`), which the spike proved
  unsafe (`running` can persist 70+s after settlement; `idle`/`dead`
  describe host/daemon state, not turn outcome). `sessions history`/`sessions
  read` render transcript text only -- confirmed empirically (this
  adapter's own probing, recorded in the mapping doc) to **never** carry
  `stopReason` at all, so the raw stream is not a fallback, it is the only
  source for the field this adapter needs.
- Unobservability (the task card's ruling) is a deterministic check, never
  a timeout: reconnect via `sessions show`/stream-tail first; settle
  `failed` only when the daemon is confirmed dead (`lastAgentExitCode`
  populated as an actual int, or `acpx pi status`'s `status` field reading
  literally `"dead"`) with no recorded result for the outstanding turn.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from orc_werk.core.errors import (
    CoreError,
    canonical_error,
    not_found_error,
    validation_error,
)
from orc_werk.core.errors import ERR_PROVIDER_UNAVAILABLE, ERR_TEMPORARY, ERR_UNSAFE_STATE
from orc_werk.core.models import Execution
from orc_werk.ports.base import LIFECYCLE_STATE_RUNNING, LIFECYCLE_STATE_SETTLED
from orc_werk.ports.capabilities import (
    CAP_EXEC_CANCEL,
    CAP_EXEC_RESUME_BEST_EFFORT,
    CAP_EXEC_RESUME_EXACT,
    CAP_EXEC_SEND,
    CAP_EXEC_STRUCTURED_LIFECYCLE,
    validate_capabilities,
)
from orc_werk.ports.execution import ExecutionObservation, ExecutionPort

# Capability set this adapter is entitled to advertise (task card, "Advertised
# capability set"). CAP-EXEC-RESUME-EXACT is deliberately never a member --
# the spike (2026-08-28) confirmed no native agentSessionId ever surfaces for
# pi-acp@0.0.31, so proving-condition (1) for that capability is unmeetable,
# not merely unproven (CONTRACT-CAPABILITIES capability-durability rule).
_ADVERTISABLE_CAPABILITIES = frozenset(
    {
        CAP_EXEC_SEND,
        CAP_EXEC_CANCEL,
        CAP_EXEC_RESUME_BEST_EFFORT,
        CAP_EXEC_STRUCTURED_LIFECYCLE,
    }
)

_DEFAULT_CAPABILITIES = _ADVERTISABLE_CAPABILITIES

# Version pins (docs/adapters/acp/mapping.md "Version pins"). Informative
# here -- not enforced at runtime, since pinning the installed CLI/npm
# package version is an operational concern outside this adapter's process
# boundary; recorded as a constant so it is discoverable from the code that
# depends on the pinned behavior.
ACPX_VERSION_PIN = "0.13.1"
PI_ACP_VERSION_PIN = "0.0.31"

_STOP_REASON_TO_OUTCOME = {
    "end_turn": "completed",
    "cancelled": "cancelled",
    # Every other stopReason (refusal, max_turn_requests, max_tokens, or any
    # value this adapter has not special-cased) maps to "failed" -- the
    # honest catch-all per PORT-EXEC-002's closed outcome vocabulary
    # (completed | failed | cancelled) and the mapping-doc footgun that a
    # permission-denied/refused turn MUST NOT be reported as success.
}


def _session_already_prompted(show: Mapping[str, Any]) -> bool:
    """Cross-process `start()` idempotency signal (issue #57). Presence-
    only, never wall-clock (`CONF-EXEC-001`'s no-randomness/no-wall-clock
    spirit extended to this decision): does NOT compare `lastPromptAt`
    against anything, only checks whether it is set at all.

    Confirmed empirically against real `acpx@0.13.1`/`pi-acp@0.0.31`
    (`docs/adapters/acp/mapping.md` "Idempotency behavior" records the
    full probe): a session's `sessions show --format json` record carries
    `lastPromptAt: null` and `messages: []` from the moment `sessions
    ensure` creates it, until the *first* prompt is queued against it --
    at which point `lastPromptAt` becomes a set (non-null) string and
    `messages` gains the submitted turn's entry, both *before* the turn
    settles (i.e. this is a submission signal, not a completion signal;
    `inspect()`'s `stopReason`-in-the-stream check remains the only
    settlement authority). Checking both fields is defense-in-depth, not
    redundancy: either one being truthy is independently sufficient
    evidence a prompt was submitted, so a caller/version-drift losing one
    field does not silently disable the guard as long as the other
    survives.
    """
    if show.get("lastPromptAt") is not None:
        return True
    return bool(show.get("messages"))


def session_name_for_idempotency_key(idempotency_key: str) -> str:
    """Deterministic, CLI-safe `acpx` session name derived from an
    `INV-020` idempotency key -- never randomness/wall-clock time
    (`CONF-EXEC-001`). Exposed as a module-level pure function so a test
    harness can predict a session name without duplicating this adapter's
    hashing scheme (mirrors `orc_werk.adapters.scripted.candidate.
    fingerprint_of` being exported for the same reason)."""
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"orcw-{digest[:24]}"


def _execution_id(*, agent: str, session_name: str, work_id: str) -> str:
    # session_name is a fixed-width hex digest (never contains ':'), so a
    # maxsplit=2 parse of this string is unambiguous even when work_id
    # itself contains ':'.
    return f"acpx-{agent}:{session_name}:{work_id}"


def _parse_execution_id(execution_id: str) -> tuple[str, str, str]:
    parts = execution_id.split(":", 2)
    if len(parts) != 3 or not parts[0].startswith("acpx-") or not parts[1] or not parts[2]:
        raise not_found_error(
            "execution_id is not a recognizable AcpExecution reference",
            execution_id=execution_id,
        )
    agent = parts[0][len("acpx-") :]
    session_name, work_id = parts[1], parts[2]
    return agent, session_name, work_id


class _AcpxInvocationError(Exception):
    """Internal carrier for a raw `acpx` subprocess failure, translated to
    a canonical `CoreError` by the caller once it has enough context
    (which operation, which session) to build a useful error payload."""

    def __init__(self, *, returncode: int, stdout: str, stderr: str) -> None:
        super().__init__(f"acpx exited {returncode}")
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    @property
    def looks_like_usage_error(self) -> bool:
        # Footgun (spike): subcommand-level bad-flag usage errors exit 1,
        # not the documented 2 -- only top-level parse errors reliably
        # exit 2. Never branch on exit code alone; always also inspect
        # stderr shape for the usage-banner pattern.
        lowered = self.stderr.lower()
        return self.returncode in (1, 2) and (
            "unknown option" in lowered or "usage:" in lowered or "error: missing" in lowered
        )


class AcpExecution(ExecutionPort):
    """`PORT-EXECUTION` adapter driving one ACP agent (default `pi`) over
    the `acpx` CLI.

    `execution_request` shape (adapter-owned, opaque to the core per
    `PORT-EXEC-001`; see `docs/adapters/acp/mapping.md`):

    ```python
    {
      "prompt": "<required prompt text>",
      "model": "<optional opaque model id>",
    }
    ```

    The adapter is agent-agnostic at the protocol layer (task card,
    "Adapter shape"): swapping `agent="pi"` for `agent="claude"` (or any
    other `acpx`-supported agent) requires no code change here, only a
    different constructor argument.
    """

    def __init__(
        self,
        *,
        agent: str = "pi",
        cwd: Optional[str] = None,
        capabilities: Iterable[str] = _DEFAULT_CAPABILITIES,
        thought_level: Optional[str] = "low",
        approve_all: bool = False,
        acpx_bin: str = "acpx",
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._agent = agent
        self._cwd = cwd
        # Optional explicit subprocess environment (e.g. to inject API
        # keys, or -- the stub-acpx conformance harness -- a PATH prefix
        # pointing at a fake `acpx` and a fixture-controlled working
        # directory). None (the default) inherits the calling process's
        # environment unchanged.
        self._env = dict(env) if env is not None else None
        caps = validate_capabilities(capabilities)
        unadvertisable = caps - _ADVERTISABLE_CAPABILITIES
        if unadvertisable:
            # Capability-durability rule (CONTRACT-CAPABILITIES): this
            # adapter never durably persists native session/resume identity
            # strong enough for CAP-EXEC-RESUME-EXACT (spike, 2026-08-28) --
            # constructing an instance that claims it is a programming
            # error, not a runtime one, so this fails fast at construction.
            raise ValueError(
                f"AcpExecution cannot advertise {sorted(unadvertisable)}: "
                "unmeetable per the 2026-08-28 spike / capability-durability rule"
            )
        self._capabilities = caps
        # thought_level default "low" (never trust the agent's own
        # default) per the mapping-doc footgun; pass None to skip pinning.
        self._thought_level = thought_level
        # --approve-all is a documented security stance, set once at
        # construction time, never a silent per-call default (mapping-doc
        # footgun). The instance-level default here is the fail-closed
        # posture (--non-interactive-permissions deny).
        self._approve_all = approve_all
        self._acpx_bin = acpx_bin

        # In-process-only bookkeeping. Neither of these is required for
        # correctness from a fresh process (session identity and
        # settlement are always re-derived from acpx/the stream, per the
        # module docstring) -- they exist purely to make attempt_number
        # (CONF-EXEC-002) and multi-turn correlation (CAP-EXEC-SEND) exact
        # *when this same instance drove every call*, and degrade to
        # documented, safe fallbacks otherwise (see inspect()/start()).
        self._by_idempotency_key: dict[str, Execution] = {}
        self._attempt_counts_by_work: dict[str, int] = {}
        self._submitted_turns: dict[str, int] = {}

    # -- capabilities -----------------------------------------------------

    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    # -- subprocess plumbing -----------------------------------------------

    def _base_argv(self, *, json_strict: bool = False) -> list[str]:
        # Footgun: global/output flags (--format, --json-strict, --cwd,
        # permission posture) are TOP-LEVEL acpx options and MUST precede
        # the agent subcommand -- `acpx --format json pi ...`, never
        # `acpx pi ... --format json`.
        argv = [self._acpx_bin, "--format", "json"]
        if json_strict:
            argv.append("--json-strict")
        if self._cwd:
            argv += ["--cwd", self._cwd]
        if self._approve_all:
            argv.append("--approve-all")
        else:
            argv += ["--non-interactive-permissions", "deny"]
        argv.append(self._agent)
        return argv

    def _run(self, args: list[str], *, json_strict: bool = False) -> Any:
        """Run one `acpx` subcommand, parse its JSON stdout. Raises
        `_AcpxInvocationError` on non-zero exit; raises canonical
        `ERR_PROVIDER_UNAVAILABLE` directly if the `acpx` binary itself
        cannot be found/executed (a distinct failure mode from the
        subprocess running and exiting non-zero)."""
        search_path = self._env.get("PATH") if self._env is not None else None
        if shutil.which(self._acpx_bin, path=search_path) is None and "/" not in self._acpx_bin:
            raise CoreError(
                canonical_error(
                    ERR_PROVIDER_UNAVAILABLE,
                    f"{self._acpx_bin!r} is not on PATH",
                    acpx_bin=self._acpx_bin,
                )
            )
        argv = self._base_argv(json_strict=json_strict) + args
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, env=self._env)
        except OSError as exc:
            raise CoreError(
                canonical_error(
                    ERR_PROVIDER_UNAVAILABLE,
                    f"failed to execute {self._acpx_bin!r}: {exc}",
                    argv=argv,
                )
            ) from exc
        if proc.returncode != 0:
            raise _AcpxInvocationError(
                returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
            )
        stdout = proc.stdout.strip()
        if not stdout:
            return {}
        try:
            return json.loads(stdout)
        except ValueError as exc:
            raise CoreError(
                canonical_error(
                    ERR_UNSAFE_STATE,
                    f"acpx produced non-JSON stdout despite --format json: {exc}",
                    argv=argv,
                    stdout=stdout[:2000],
                )
            ) from exc

    def _translate_invocation_error(
        self, exc: _AcpxInvocationError, *, operation: str, **details: Any
    ) -> CoreError:
        if exc.looks_like_usage_error:
            # An adapter-shaped invocation was rejected as malformed -- we
            # do not know whether it had side effects, so this is not
            # safely retryable as-is (ERR_UNSAFE_STATE), not a validation
            # complaint about the caller's portable input.
            return CoreError(
                canonical_error(
                    ERR_UNSAFE_STATE,
                    f"acpx rejected the {operation} invocation as malformed",
                    operation=operation,
                    returncode=exc.returncode,
                    stderr=exc.stderr[:2000],
                    **details,
                )
            )
        if exc.returncode == 4:
            return not_found_error(
                f"acpx reports no session for {operation}", returncode=exc.returncode, **details
            )
        return CoreError(
            canonical_error(
                ERR_TEMPORARY,
                f"acpx {operation} exited {exc.returncode}",
                operation=operation,
                returncode=exc.returncode,
                stderr=exc.stderr[:2000],
                **details,
            )
        )

    # -- start --------------------------------------------------------------

    def start(
        self,
        *,
        work_id: str,
        execution_request: Mapping[str, Any],
        idempotency_key: str,
    ) -> Execution:
        if idempotency_key in self._by_idempotency_key:
            # CONF-EXEC-002: same idempotency key -> same Execution ref,
            # no duplicate logical execution, no new acpx session/turn.
            # Fast path only -- NOT the correctness mechanism for
            # cross-process de-duplication (issue #57): a fresh process
            # always misses this cache, so the durable check below is
            # what actually prevents a duplicate prompt.
            return self._by_idempotency_key[idempotency_key]

        session_name = session_name_for_idempotency_key(idempotency_key)
        execution_id = _execution_id(agent=self._agent, session_name=session_name, work_id=work_id)

        try:
            self._run(["sessions", "ensure", "-s", session_name])
        except _AcpxInvocationError as exc:
            raise self._translate_invocation_error(
                exc, operation="start", session_name=session_name, work_id=work_id
            ) from exc

        # Issue #57: `Orchestrator._reconcile_ports` replays FX-START-
        # EXECUTION -- i.e. calls this method again -- from a FRESH
        # process/instance on every ordinary `orc dispatch`, not just
        # genuine crash recovery (`docs/adapters/acp/mapping.md`
        # "Idempotency behavior"). The in-process cache above is empty in
        # that fresh process, so cross-process idempotency MUST come from
        # a durable acpx signal, consulted before ever touching the
        # prompt: `sessions show`'s own session record. Because
        # `session_name` is a deterministic 1:1 function of this
        # attempt's idempotency key (`session_name_for_idempotency_key`),
        # "this session has ever seen a prompt" is exactly "this
        # attempt's start() already ran its submit step once" -- there is
        # no other submitter that could have written that signal.
        try:
            show = self._run(["sessions", "show", session_name])
        except _AcpxInvocationError as exc:
            raise self._translate_invocation_error(
                exc, operation="start", session_name=session_name, work_id=work_id
            ) from exc

        if _session_already_prompted(show):
            # Edge cases (a) running and (b) completed both land here --
            # inspect() (not start()) is the settlement authority either
            # way, so returning the same stable ref without resubmitting
            # is correct and sufficient for both. Deliberately does NOT
            # validate/require execution_request['prompt'] on this path:
            # a bare replay call (e.g. `Orchestrator._replay_effect_record`,
            # which always calls start() with execution_request={}) must
            # not raise ERR-VALIDATION just because it has no prompt text
            # to offer -- it doesn't need one, nothing is being submitted.
            attempt_index = self._attempt_counts_by_work.get(work_id, 0)
            self._attempt_counts_by_work[work_id] = attempt_index + 1
            execution = Execution(id=execution_id, work_id=work_id, attempt_number=attempt_index + 1)
            self._by_idempotency_key[idempotency_key] = execution
            return execution

        # Edge case (c) fresh session, or (d) crash between `sessions
        # ensure` and the prompt submit that follows -- either way, no
        # prompt has ever reached this session, so this is the legitimate
        # (at most once) submit.
        prompt = execution_request.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            raise validation_error(
                "execution_request['prompt'] must be a non-empty string",
                execution_request=execution_request,
            )
        requested_model = execution_request.get("model")

        if self._thought_level is not None:
            self._set_config_option(session_name, "thought_level", self._thought_level)
        if requested_model is not None:
            resolved_model = self._resolve_model(show, requested_model)
            try:
                self._run(["set", "model", resolved_model, "-s", session_name])
            except _AcpxInvocationError as exc:
                # A requested model is a pin, not a preference.  If acpx
                # cannot apply the validated id, running at the session
                # default would be an unsafe silent substitution.
                raise self._translate_invocation_error(
                    exc,
                    operation="start.model",
                    session_name=session_name,
                    requested_model=requested_model,
                    resolved_model=resolved_model,
                ) from exc

        try:
            self._run(
                ["-s", session_name, "--no-wait", prompt],
                json_strict=True,
            )
        except _AcpxInvocationError as exc:
            raise self._translate_invocation_error(
                exc, operation="start.prompt", session_name=session_name, work_id=work_id
            ) from exc

        attempt_index = self._attempt_counts_by_work.get(work_id, 0)
        self._attempt_counts_by_work[work_id] = attempt_index + 1
        execution = Execution(id=execution_id, work_id=work_id, attempt_number=attempt_index + 1)
        self._by_idempotency_key[idempotency_key] = execution
        self._submitted_turns[execution_id] = 1
        return execution

    @staticmethod
    def _resolve_model(show: Mapping[str, Any], requested_model: Any) -> str:
        advertised = (show.get("acpx") or {}).get("available_models")
        available_ids = (
            [model_id for model_id in advertised if isinstance(model_id, str)]
            if isinstance(advertised, list)
            else []
        )
        if not isinstance(requested_model, str) or not requested_model:
            raise validation_error(
                "execution_request['model'] must be a non-empty string matching an "
                f"advertised model id; advertised ids: {available_ids}",
                requested_model=requested_model,
                advertised_model_ids=available_ids,
            )

        if requested_model in available_ids:
            return requested_model

        requested_folded = requested_model.casefold()
        matches = [
            model_id for model_id in available_ids if requested_folded in model_id.casefold()
        ]
        if len(matches) == 1:
            return matches[0]

        reason = "not advertised" if not matches else "ambiguous"
        raise validation_error(
            f"requested model {requested_model!r} is {reason}; advertised ids: {available_ids}",
            requested_model=requested_model,
            advertised_model_ids=available_ids,
            matching_model_ids=matches,
        )

    def _set_config_option(self, session_name: str, key: str, value: str) -> None:
        # thought_level is settable non-interactively per session and is
        # pinned explicitly rather than trusting the agent's own default.
        # Best-effort: a set
        # failure here should not abort the whole start() -- the session
        # already exists and is usable, just possibly not at the pinned
        # config -- so this is deliberately swallowed into a soft no-op
        # rather than raised, documented in mapping.md.
        try:
            self._run(["set", key, value, "-s", session_name])
        except _AcpxInvocationError:
            pass

    # -- inspect --------------------------------------------------------------

    def inspect(self, *, execution_id: str) -> ExecutionObservation:
        _agent, session_name, _work_id = _parse_execution_id(execution_id)

        try:
            show = self._run(["sessions", "show", session_name])
        except _AcpxInvocationError as exc:
            raise self._translate_invocation_error(
                exc, operation="inspect", session_name=session_name
            ) from exc

        stream_path = ((show or {}).get("eventLog") or {}).get("active_path")
        terminal_results = _scan_stream_terminal_results(stream_path) if stream_path else []

        expected = self._submitted_turns.get(execution_id)
        settled_result: Optional[str] = None
        if expected is not None:
            if len(terminal_results) >= expected:
                settled_result = terminal_results[expected - 1]
        else:
            # Fresh process/instance: no local record of how many turns we
            # ourselves submitted. Per the module docstring, Execution<->
            # session identity is 1:1, so "the latest recorded turn" is the
            # correct thing to report for the crash-recovery case (the
            # process that died was the sole submitter, so there is
            # exactly one outstanding turn).
            if terminal_results:
                settled_result = terminal_results[-1]

        if settled_result is not None:
            outcome = _STOP_REASON_TO_OUTCOME.get(settled_result, "failed")
            return ExecutionObservation(
                state=LIFECYCLE_STATE_SETTLED,
                outcome=outcome,
                extensions=self._session_provenance(show, session_name, resume_ref=session_name),
            )

        if self._daemon_confirmed_dead(show, session_name):
            # The task card's abandonment ruling: settle failed ONLY on a
            # deterministic unobservability signal, never a timeout. This
            # is an honest observation of a lost outcome, not a
            # fabrication (STATE-DELIVERY mechanical fact sequencing item
            # 6's normalization family).
            return ExecutionObservation(
                state=LIFECYCLE_STATE_SETTLED,
                outcome="failed",
                extensions=self._session_provenance(
                    show, session_name, resume_ref=session_name
                ),
            )

        return ExecutionObservation(state=LIFECYCLE_STATE_RUNNING)

    def _daemon_confirmed_dead(self, show: Mapping[str, Any], session_name: str) -> bool:
        # Primary signal: sessions show's own durable session record.
        last_exit_code = show.get("lastAgentExitCode")
        if isinstance(last_exit_code, int):
            return True
        # Secondary, corroborating signal: acpx's own liveness snapshot.
        # "no-session" is deliberately NOT treated as dead here -- it is
        # also returned for a brand-new session before its queue owner has
        # spawned, which would make a fresh in-flight turn look dead. Only
        # a literal "dead" status counts (never a timeout, per the ruling).
        try:
            status = self._run(["status", "-s", session_name])
        except _AcpxInvocationError:
            return False
        return status.get("status") == "dead"

    def _session_provenance(
        self,
        show: Mapping[str, Any],
        session_name: str,
        *,
        resume_ref: str,
    ) -> dict[str, Any]:
        # execution-session/v1 (EXT-EXECUTION-SESSION-V1): acpxRecordId and
        # acpSessionId are confirmed always identical for Pi (spike); no
        # agentSessionId ever surfaces, so native_session_id is acpx's own
        # generated id -- there is no other candidate. resume.strength is
        # "best-effort" because acpx never calls session/resume for Pi,
        # only session/load (spike, SPIKE 2b) -- an operationally real,
        # durably-recorded best-effort reconnect, never "exact".
        native_session_id = show.get("acpxRecordId") or show.get("acpSessionId") or session_name
        payload: dict[str, Any] = {
            "provider": f"acpx-{self._agent}",
            "native_session_id": native_session_id,
            "resume": {"strength": "best-effort", "ref": resume_ref},
        }
        event_log = show.get("eventLog") or {}
        transcript_ref = event_log.get("active_path")
        if transcript_ref:
            payload["transcript_ref"] = transcript_ref
        acpx_meta = show.get("acpx") or {}
        profile: dict[str, Any] = {}
        model = acpx_meta.get("current_model_id")
        if model:
            profile["model"] = model
        if self._thought_level is not None:
            profile["effort"] = self._thought_level
        if profile:
            payload["profile"] = profile
        return {"execution-session/v1": payload}

    # -- send / cancel / resume ------------------------------------------

    def send(self, *, execution_id: str, message: Mapping[str, Any]) -> None:
        self._require_capability(CAP_EXEC_SEND, operation="send", execution_id=execution_id)
        _agent, session_name, _work_id = _parse_execution_id(execution_id)
        # message['prompt'] is preferred; message['text'] is accepted as an
        # alias so this adapter also serves generic PORT-EXEC-003 callers
        # that follow the port doc's own opaque-mapping exemplar rather
        # than this adapter's specific field name (mapping.md).
        prompt = message.get("prompt", message.get("text"))
        if not isinstance(prompt, str) or not prompt:
            raise validation_error(
                "message['prompt'] (or message['text']) must be a non-empty string",
                message=message,
            )
        try:
            self._run(["-s", session_name, "--no-wait", prompt], json_strict=True)
        except _AcpxInvocationError as exc:
            raise self._translate_invocation_error(
                exc, operation="send", session_name=session_name
            ) from exc
        self._submitted_turns[execution_id] = self._submitted_turns.get(execution_id, 0) + 1

    def cancel(self, *, execution_id: str) -> None:
        self._require_capability(CAP_EXEC_CANCEL, operation="cancel", execution_id=execution_id)
        _agent, session_name, _work_id = _parse_execution_id(execution_id)
        try:
            self._run(["cancel", "-s", session_name])
        except _AcpxInvocationError as exc:
            raise self._translate_invocation_error(
                exc, operation="cancel", session_name=session_name
            ) from exc
        # Footgun: a cancel that exits 0 may mean "nothing to cancel" --
        # exit code alone never proves a cancellation happened. Post-verify
        # by re-inspecting for stopReason == cancelled. This does not
        # raise on a no-op cancel (idle-cancel is a legitimate outcome,
        # e.g. the turn had already settled before the cancel arrived);
        # cancel() only fails if acpx itself failed.
        self.inspect(execution_id=execution_id)

    def resume(self, *, execution_id: str, resume_request: Mapping[str, Any]) -> Execution:
        requested = resume_request.get("capability")
        if requested not in (CAP_EXEC_RESUME_BEST_EFFORT, CAP_EXEC_RESUME_EXACT):
            raise validation_error(
                "resume_request['capability'] must name a resume-strength capability id "
                f"(one of {sorted((CAP_EXEC_RESUME_BEST_EFFORT, CAP_EXEC_RESUME_EXACT))})",
                requested=requested,
            )
        # INV-013 / CONF-EXEC-004: CAP-EXEC-RESUME-EXACT is never in
        # self._capabilities (enforced at __init__), so a request for it
        # always fails explicitly here -- never silently served at
        # best-effort strength.
        self._require_capability(requested, operation="resume", execution_id=execution_id)

        _agent, session_name, work_id = _parse_execution_id(execution_id)
        try:
            self._run(["sessions", "show", session_name])
        except _AcpxInvocationError as exc:
            raise self._translate_invocation_error(
                exc, operation="resume", session_name=session_name
            ) from exc

        cached = self._by_idempotency_key
        attempt_number = 1
        for execution in cached.values():
            if execution.id == execution_id:
                attempt_number = execution.attempt_number
                break
        return Execution(id=execution_id, work_id=work_id, attempt_number=attempt_number)


def _scan_stream_terminal_results(stream_path: str) -> list[str]:
    """Parse `stopReason` values, in file order, from an `acpx` session's
    raw JSON-RPC event-log stream. Tolerant of unparsable/partial lines
    (a concurrently-written NDJSON file, not a canonical journal --
    unlike `orc_werk.adapters.jsonl.tailsafe`, a bad line here is simply
    skipped, never an error): the stream is third-party output this
    adapter only reads, never owns or repairs.

    Confirmed empirically (this adapter's own probing against a live
    `acpx pi` session, recorded in `docs/adapters/acp/mapping.md`):
    `sessions history`/`sessions read` render transcript text only and
    never carry `stopReason` -- the raw stream is not a fallback source
    for this field, it is the *only* source.
    """
    path = Path(stream_path)
    if not path.exists():
        return []
    results: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            result = record.get("result")
            if isinstance(result, dict) and "stopReason" in result and "id" in record:
                stop_reason = result["stopReason"]
                if isinstance(stop_reason, str):
                    results.append(stop_reason)
    return results


__all__ = [
    "ACPX_VERSION_PIN",
    "PI_ACP_VERSION_PIN",
    "AcpExecution",
    "session_name_for_idempotency_key",
]
