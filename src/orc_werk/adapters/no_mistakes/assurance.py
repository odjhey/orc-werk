"""NoMistakesAssurance (`TASK-M2-001`): `PORT-ASSURANCE` adapter over the
`no-mistakes` CLI, a local automated code-review/gate pipeline.

All `no-mistakes`/`axi` vocabulary -- CLI flags, TOON field names, pipeline
step/gate shapes -- stays in this module and `docs/adapters/no-mistakes/
mapping.md`, per `INV-014` and `docs/adapters/README.md`.

**Judge-only ruling (watchtower, `TASK-M2-001`, normative for this
adapter)**: this adapter is a READ-ONLY JUDGE of the exact observed
candidate. It NEVER passes `--yes` to `axi run`, NEVER calls
`axi respond`/`axi sync` -- any operation that could let `no-mistakes`
fix findings or auto-resolve a gate -- and passes `--skip push`
(`_SKIPPED_STEPS`) on EVERY `axi run` spawn as the mechanical never-push
guarantee: omitting `--yes` alone is NOT sufficient (it only governs gate
auto-resolution -- a clean candidate with no gates runs the full pipeline
INCLUDING the push step; confirmed empirically, PR #80 fix round finding
B). A candidate that `no-mistakes` would mutate (fix commits) or push is
a DIFFERENT candidate than the one this adapter was asked to assure
(`P-004`, `INV-007` through `INV-010`).
Concretely: when the pipeline reaches a gate (`awaiting_approval`), this
adapter never advances it -- it reads the parked findings and renders its
OWN canonical verdict from them (see "Verdict mapping" below). The
underlying `no-mistakes` run is left parked; a human operator (not this
adapter) resolves it later via `no-mistakes axi respond`/`axi abort`. See
the mapping doc's "Judge-only ruling" and "Limitations" sections for the
full rationale and the resulting stale-parked-run tradeoff.

Design summary (full rationale: `docs/adapters/no-mistakes/mapping.md`):

- `request()` never blocks on the pipeline: it spawns `no-mistakes axi run
  --intent <text> --skip push` DETACHED (`subprocess.Popen`, not waited
  on) and returns
  once it has confirmed a run id exists to reference -- never once the
  pipeline itself has progressed. Unlike `acpx`'s `--no-wait` (a
  synchronous, sub-second acknowledgement), `axi run` offers no such flag,
  so this adapter uses a small BOUNDED poll of `axi status` (default 10s /
  0.25s interval, both overridable) purely to observe the new run's id
  appearing -- documented in the mapping doc as a deliberate, bounded
  tradeoff, not a wait on pipeline completion.
- `inspect()` is the sole settlement authority, always re-derived from
  `no-mistakes axi status --run <id>` (durable, provider-owned state) --
  never from in-process memory as the correctness path (an in-process
  settled-observation cache exists only as a fast path, mirroring
  `ScriptedAssurance`/`AcpExecution`).
- `assurance_id` durably encodes everything a FRESH process needs to
  inspect: the candidate fingerprint this run was bound to at request time
  (`INV-007`), the `no-mistakes`-native run id, and the configured
  `repo_path` (the cwd every `no-mistakes` invocation runs in) -- see
  `_assurance_id`/`_parse_assurance_id`.
- Verdict mapping (full table + rationale: mapping doc):
  a terminal `outcome: passed` -> `accepted`; `outcome: failed` -> `rejected`;
  a parked gate with 1+ findings -> `rejected` (the review policy itself
  declined to let the candidate proceed, `EXT-REVIEW-FINDINGS-V1-
  SEMANTICS`'s disposition framing); a parked gate with zero findings, or
  a `cancelled`/`aborted` run -> `inconclusive`.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any, Iterable, Mapping, Optional

from orc_werk.adapters.no_mistakes.toon import parse_toon
from orc_werk.core.errors import (
    CoreError,
    canonical_error,
    not_found_error,
    validation_error,
)
from orc_werk.core.errors import ERR_PROVIDER_UNAVAILABLE, ERR_TEMPORARY, ERR_UNSAFE_STATE
from orc_werk.core.models import AssuranceRun, Candidate
from orc_werk.ports.assurance import AssuranceObservation, AssurancePort
from orc_werk.ports.base import LIFECYCLE_STATE_REQUESTED, LIFECYCLE_STATE_RUNNING, LIFECYCLE_STATE_SETTLED
from orc_werk.ports.capabilities import (
    CAP_ASSURE_CANDIDATE_BOUND,
    CAP_ASSURE_MAY_MUTATE_CANDIDATE,
    CAP_ASSURE_STRUCTURED_FINDINGS,
    CAP_ASSURE_STRUCTURED_VERDICT,
    validate_capabilities,
)

# Capability set this adapter is entitled to advertise. CAP-ASSURE-MAY-
# MUTATE-CANDIDATE is deliberately never a member -- the judge-only ruling
# means this adapter never lets no-mistakes fix/push, so it never mutates
# the candidate it was asked to assure (module docstring).
_ADVERTISABLE_CAPABILITIES = frozenset(
    {
        CAP_ASSURE_CANDIDATE_BOUND,
        CAP_ASSURE_STRUCTURED_VERDICT,
        CAP_ASSURE_STRUCTURED_FINDINGS,
    }
)
_DEFAULT_CAPABILITIES = _ADVERTISABLE_CAPABILITIES

# Pipeline steps every `axi run` spawn skips (comma-separated, the CLI's
# own `--skip` format). `push` is the mechanical never-push guarantee (PR
# #80 fix round, finding B; module docstring "Judge-only ruling"):
# confirmed empirically that `--skip push` completes a clean pipeline with
# the push step `skipped`, `pushed_head` empty, and the local branch head
# untouched. Fail-closed note: if a future no-mistakes version renames
# the `push` step, this skip silently stops matching anything -- the pin
# must be re-proved against that version's own step list (`axi logs
# --help` names the canonical steps) before upgrading, the same
# version-re-probe discipline the TOON parser already requires (mapping
# doc "Limitations" / docs/playbooks/cli-usage.md known-issues row).
_SKIPPED_STEPS = "push"

# Bounded wait for a freshly-spawned `axi run` to register a run id
# (mapping doc "Poll model"). Not a wait on pipeline progress -- purely on
# the daemon materializing a queryable run record. Overridable per
# instance (tests use much smaller values against the stub).
_DEFAULT_SPAWN_POLL_TIMEOUT_S = 10.0
_DEFAULT_SPAWN_POLL_INTERVAL_S = 0.25

# no-mistakes review-severity -> EXT-REVIEW-FINDINGS-V1-SCHEMA severity.
# Best-effort, documented heuristic (mapping doc "Limitations") -- no-
# mistakes does not itself speak this vocabulary.
_SEVERITY_MAP = {"error": "high", "warning": "medium", "info": "info"}
_DEFAULT_SEVERITY = "medium"

# Best-effort finding-id-substring -> EXT-REVIEW-FINDINGS-V1-SCHEMA
# category heuristic (mapping doc "Limitations"). Checked in order;
# first substring match wins. no-mistakes finding ids are an open,
# provider-owned vocabulary this adapter does not control, so this is
# intentionally a small, non-exhaustive default table, never claimed
# authoritative.
_CATEGORY_HINTS = (
    ("secret", "security"), ("credential", "security"), ("security", "security"),
    ("perf", "performance"),
    ("concurren", "concurrency"), ("race", "concurrency"),
    ("test", "testing"),
    ("style", "style"), ("lint", "style"),
    ("doc", "docs"),
    ("compat", "compatibility"),
    ("contract", "contract"),
    ("maintain", "maintainability"), ("dead", "maintainability"), ("unused", "maintainability"),
    ("data", "data-integrity"),
)
_DEFAULT_CATEGORY = "correctness"

# run.status values that mean "nothing further will ever be observed for
# this run" without a decision-relevant outcome (mapping doc "Verdict
# mapping"). completed is handled separately (it carries an outcome/gate).
_INCONCLUSIVE_TERMINAL_STATUSES = frozenset({"cancelled", "aborted", "failed"})
_TERMINAL_STATUSES = _INCONCLUSIVE_TERMINAL_STATUSES | {"completed"}


def _category_for(finding_id: str) -> str:
    lowered = finding_id.lower()
    for hint, category in _CATEGORY_HINTS:
        if hint in lowered:
            return category
    return _DEFAULT_CATEGORY


def _assurance_id(*, fingerprint: str, native_run_id: str, repo_path: str) -> str:
    # fingerprint is always "fp-<24hex>" (no colon); native_run_id is a
    # fixed-width ULID-shaped token (no colon) -- so a maxsplit=3 parse is
    # unambiguous even when repo_path itself contains ':' (mirrors
    # AcpExecution's execution_id shape/rationale).
    return f"no-mistakes:{fingerprint}:{native_run_id}:{repo_path}"


def _parse_assurance_id(assurance_id: str) -> tuple[str, str, str]:
    parts = assurance_id.split(":", 3)
    if (
        len(parts) != 4
        or parts[0] != "no-mistakes"
        or not parts[1].startswith("fp-")
        or not parts[2]
        or not parts[3]
    ):
        raise not_found_error(
            "assurance_id is not a recognizable NoMistakesAssurance reference",
            assurance_id=assurance_id,
        )
    _prefix, fingerprint, native_run_id, repo_path = parts
    return fingerprint, native_run_id, repo_path


class _NoMistakesInvocationError(Exception):
    def __init__(self, *, returncode: int, stdout: str, stderr: str) -> None:
        super().__init__(f"no-mistakes exited {returncode}")
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    @property
    def combined_lower(self) -> str:
        return (self.stdout + "\n" + self.stderr).lower()


class NoMistakesAssurance(AssurancePort):
    """`PORT-ASSURANCE` adapter driving one `no-mistakes`-gated repository
    (one configured `repo_path`, mirroring `AcpExecution`'s one-`cwd`-per-
    instance / `GitDiffCandidate`'s one-worktree-per-Work assumption).

    `requirements` shape (adapter-owned, opaque to the core per
    `PORT-ASSURE-001`; see `docs/adapters/no-mistakes/mapping.md`):

    ```python
    {"intent": "<required, non-empty --intent text for a NEW pipeline run>"}
    ```
    """

    def __init__(
        self,
        *,
        repo_path: str,
        capabilities: Iterable[str] = _DEFAULT_CAPABILITIES,
        no_mistakes_bin: str = "no-mistakes",
        env: Optional[Mapping[str, str]] = None,
        spawn_poll_timeout_s: float = _DEFAULT_SPAWN_POLL_TIMEOUT_S,
        spawn_poll_interval_s: float = _DEFAULT_SPAWN_POLL_INTERVAL_S,
    ) -> None:
        self._repo_path = repo_path
        self._bin = no_mistakes_bin
        self._env = dict(env) if env is not None else None
        self._spawn_poll_timeout_s = spawn_poll_timeout_s
        self._spawn_poll_interval_s = spawn_poll_interval_s

        caps = validate_capabilities(capabilities)
        unadvertisable = caps - _ADVERTISABLE_CAPABILITIES
        if unadvertisable:
            # Judge-only ruling / capability-durability rule
            # (CONTRACT-CAPABILITIES): this adapter never mutates the
            # candidate, so constructing an instance that claims
            # CAP-ASSURE-MAY-MUTATE-CANDIDATE is a programming error.
            raise ValueError(
                f"NoMistakesAssurance cannot advertise {sorted(unadvertisable)}: "
                "unmeetable under the judge-only ruling (TASK-M2-001)"
            )
        self._capabilities = caps

        self._by_idempotency_key: dict[str, AssuranceRun] = {}
        self._settled_snapshot: dict[str, AssuranceObservation] = {}

    # -- capabilities -----------------------------------------------------

    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    # -- subprocess plumbing ------------------------------------------------

    def _ensure_binary(self) -> None:
        search_path = self._env.get("PATH") if self._env is not None else None
        if shutil.which(self._bin, path=search_path) is None and "/" not in self._bin:
            raise CoreError(
                canonical_error(
                    ERR_PROVIDER_UNAVAILABLE, f"{self._bin!r} is not on PATH", no_mistakes_bin=self._bin
                )
            )

    def _axi_status(self, *, repo_path: str, run_id: Optional[str] = None) -> dict[str, Any]:
        self._ensure_binary()
        argv = [self._bin, "axi", "status"]
        if run_id:
            argv += ["--run", run_id]
        try:
            proc = subprocess.run(argv, cwd=repo_path, capture_output=True, text=True, env=self._env)
        except OSError as exc:
            raise CoreError(
                canonical_error(
                    ERR_PROVIDER_UNAVAILABLE, f"failed to execute {self._bin!r}: {exc}", argv=argv
                )
            ) from exc
        if proc.returncode != 0:
            combined = (proc.stdout + "\n" + proc.stderr).lower()
            if "not initialized" in combined:
                raise CoreError(
                    canonical_error(
                        ERR_PROVIDER_UNAVAILABLE,
                        "no-mistakes gate is not initialized at repo_path (run `no-mistakes init` first)",
                        repo_path=repo_path,
                    )
                )
            if run_id is not None and ("not found" in combined or "no run" in combined):
                # Nothing durable exists yet for this exact run id -- honest
                # "requested" territory, not an error (mirrors AcpExecution
                # treating an absent stopReason as "still running", never a
                # fabricated failure).
                return {}
            raise CoreError(
                canonical_error(
                    ERR_TEMPORARY,
                    f"no-mistakes axi status exited {proc.returncode}",
                    argv=argv,
                    stderr=proc.stderr[:2000],
                )
            )
        if not proc.stdout.strip():
            return {}
        return parse_toon(proc.stdout)

    def _spawn_and_capture_run_id(self, intent: str) -> str:
        self._ensure_binary()
        argv = [self._bin, "axi", "run", "--intent", intent, "--skip", _SKIPPED_STEPS]
        # Judge-only ruling: --yes is NEVER passed here -- see module
        # docstring. `--skip push` (_SKIPPED_STEPS) is the MECHANICAL
        # never-push guarantee (PR #80 fix round, finding B): omitting
        # --yes only prevents gate auto-resolution -- a CLEAN candidate
        # with no gates would otherwise run the full pipeline INCLUDING
        # the push step (confirmed empirically; see the mapping doc's
        # "Judge-only ruling" for the probe evidence, including that
        # pipeline-internal commits stay confined to the gate copy and
        # never reach the branch/remote when push is skipped).
        # Detached: not waited on (mapping doc "Poll model").
        try:
            proc = subprocess.Popen(
                argv,
                cwd=self._repo_path,
                env=self._env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise CoreError(
                canonical_error(
                    ERR_PROVIDER_UNAVAILABLE, f"failed to execute {self._bin!r}: {exc}", argv=argv
                )
            ) from exc

        deadline = time.monotonic() + self._spawn_poll_timeout_s
        while True:
            # Best-effort, non-blocking reap: never waited on for
            # correctness (this is a detached, fire-and-forget submission,
            # module docstring "Poll model") -- polled only so a short-
            # lived process (e.g. the stub CLI in tests) does not linger
            # as an un-reaped zombie/ResourceWarning source.
            proc.poll()
            status = self._axi_status(repo_path=self._repo_path)
            run_block = status.get("run")
            if isinstance(run_block, dict) and run_block.get("id"):
                return str(run_block["id"])
            if time.monotonic() >= deadline:
                raise CoreError(
                    canonical_error(
                        ERR_TEMPORARY,
                        "no-mistakes did not register a new pipeline run within the bounded "
                        f"spawn-wait ({self._spawn_poll_timeout_s}s); this may mean the invocation "
                        "failed immediately (this adapter never observes that directly -- see "
                        "mapping doc Limitations) or is merely slow to register; retry request()",
                        repo_path=self._repo_path,
                        timeout_s=self._spawn_poll_timeout_s,
                    )
                )
            time.sleep(self._spawn_poll_interval_s)

    def _repo_head(self) -> Optional[str]:
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD^{commit}"],
                cwd=self._repo_path,
                env=self._env,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        head = proc.stdout.strip()
        return head if proc.returncode == 0 and head else None

    # -- request --------------------------------------------------------------

    def request(
        self,
        *,
        candidate: Candidate,
        requirements: Mapping[str, Any],
        idempotency_key: str,
    ) -> AssuranceRun:
        if idempotency_key in self._by_idempotency_key:
            return self._by_idempotency_key[idempotency_key]

        intent = requirements.get("intent")
        if not isinstance(intent, str) or not intent:
            raise validation_error(
                "requirements['intent'] must be a non-empty string", requirements=requirements
            )

        subject = candidate.subject_identity if isinstance(candidate.subject_identity, Mapping) else {}
        expected_head = subject.get("head_sha") if isinstance(subject.get("head_sha"), str) else None
        if expected_head is None:
            # A replay-rehydrated Candidate may retain only its durable
            # fingerprint. CLI wiring constrains this adapter to a git
            # candidate, so re-read the configured repository's current
            # HEAD rather than weakening active-run identity confirmation.
            expected_head = self._repo_head()

        status = self._axi_status(repo_path=self._repo_path)
        run_block = status.get("run") if isinstance(status.get("run"), dict) else None

        if run_block is not None and run_block.get("status") not in _TERMINAL_STATUSES:
            observed_head = _observed_head(status)
            if expected_head is None or observed_head is None or observed_head != expected_head:
                raise CoreError(
                    canonical_error(
                        ERR_UNSAFE_STATE,
                        "an unrelated or unconfirmable no-mistakes pipeline is active in this repo; "
                        "abort or await it before requesting assurance",
                        repo_path=self._repo_path,
                        expected_head=expected_head,
                        observed_head=observed_head,
                        active_run_id=run_block.get("id"),
                    )
                )
            native_run_id = str(run_block["id"])
        else:
            native_run_id = self._spawn_and_capture_run_id(intent)

        assurance_id = _assurance_id(
            fingerprint=candidate.fingerprint, native_run_id=native_run_id, repo_path=self._repo_path
        )
        run = AssuranceRun(id=assurance_id, candidate_id=candidate.id)
        self._by_idempotency_key[idempotency_key] = run
        return run

    # -- inspect --------------------------------------------------------------

    def inspect(self, *, assurance_id: str) -> AssuranceObservation:
        if assurance_id in self._settled_snapshot:
            # CONF-ASSURE-002: a settled verdict is immutable. Fast path
            # only -- the durable answer below is always independently
            # re-derivable from `axi status --run <id>` (INV-020).
            return self._settled_snapshot[assurance_id]

        fingerprint, native_run_id, repo_path = _parse_assurance_id(assurance_id)
        status = self._axi_status(repo_path=repo_path, run_id=native_run_id)
        run_block = status.get("run") if isinstance(status.get("run"), dict) else None

        if run_block is None or str(run_block.get("id")) != native_run_id:
            # Nothing durable observed yet for THIS exact run id -- honest
            # PORT-ASSURE-002 "requested", never fabricated.
            return AssuranceObservation(state=LIFECYCLE_STATE_REQUESTED)

        gate = status.get("gate") if isinstance(status.get("gate"), dict) else None
        if gate is not None:
            observation = self._settle_from_gate(
                fingerprint=fingerprint, run_block=run_block, gate=gate, repo_path=repo_path
            )
            self._settled_snapshot[assurance_id] = observation
            return observation

        run_status = run_block.get("status")
        if run_status == "completed":
            observation = self._settle_from_outcome(
                fingerprint=fingerprint, run_block=run_block, status=status, repo_path=repo_path
            )
            self._settled_snapshot[assurance_id] = observation
            return observation
        if run_status in _INCONCLUSIVE_TERMINAL_STATUSES:
            observation = AssuranceObservation(
                state=LIFECYCLE_STATE_SETTLED,
                verdict="inconclusive",
                candidate_fingerprint=fingerprint,
                evidence_refs=(self._evidence_ref(run_block=run_block, repo_path=repo_path),),
            )
            self._settled_snapshot[assurance_id] = observation
            return observation

        return AssuranceObservation(state=LIFECYCLE_STATE_RUNNING)

    # -- verdict derivation -------------------------------------------------

    def _evidence_ref(
        self, *, run_block: Mapping[str, Any], repo_path: str, step: Optional[str] = None
    ) -> dict[str, Any]:
        run_id = str(run_block.get("id"))
        ref: dict[str, Any] = {
            "no_mistakes_run_id": run_id,
            "repo_path": repo_path,
            "command": f"no-mistakes axi status --run {run_id}",
        }
        branch = run_block.get("branch")
        if isinstance(branch, str):
            ref["branch"] = branch
        if step is not None:
            ref["step"] = step
            ref["logs_command"] = f"no-mistakes axi logs --run {run_id} --step {step} --full"
        return ref

    def _settle_from_gate(
        self,
        *,
        fingerprint: str,
        run_block: Mapping[str, Any],
        gate: Mapping[str, Any],
        repo_path: str,
    ) -> AssuranceObservation:
        step = gate.get("step") if isinstance(gate.get("step"), str) else None
        raw_findings = gate.get("findings")
        findings = raw_findings if isinstance(raw_findings, list) else []

        if not findings:
            # A parked gate with nothing to explain it: genuinely
            # ambiguous, per the mapping doc's verdict table -- never
            # guessed toward rejected or accepted.
            return AssuranceObservation(
                state=LIFECYCLE_STATE_SETTLED,
                verdict="inconclusive",
                candidate_fingerprint=fingerprint,
                evidence_refs=(self._evidence_ref(run_block=run_block, repo_path=repo_path, step=step),),
            )

        review_findings = [
            _to_review_finding(finding, index=index, step=step) for index, finding in enumerate(findings)
        ]
        extensions = {"review-findings/v1": {"findings": review_findings}}
        return AssuranceObservation(
            state=LIFECYCLE_STATE_SETTLED,
            # Judge-only verdict rule (mapping doc "Verdict mapping"): a
            # parked gate means no-mistakes' OWN review policy declined to
            # let this exact candidate proceed automatically
            # (EXT-REVIEW-FINDINGS-V1-SEMANTICS' disposition framing) --
            # that is rejected, regardless of individual finding severity.
            verdict="rejected",
            candidate_fingerprint=fingerprint,
            evidence_refs=(self._evidence_ref(run_block=run_block, repo_path=repo_path, step=step),),
            extensions=extensions,
        )

    def _settle_from_outcome(
        self,
        *,
        fingerprint: str,
        run_block: Mapping[str, Any],
        status: Mapping[str, Any],
        repo_path: str,
    ) -> AssuranceObservation:
        outcome = status.get("outcome")
        if outcome == "passed":
            verdict = "accepted"
        elif outcome == "failed":
            verdict = "rejected"
        else:
            # Missing/unrecognized outcome on a completed run: never
            # guessed toward accepted (mapping doc "Verdict mapping").
            verdict = "inconclusive"
        return AssuranceObservation(
            state=LIFECYCLE_STATE_SETTLED,
            verdict=verdict,
            candidate_fingerprint=fingerprint,
            evidence_refs=(self._evidence_ref(run_block=run_block, repo_path=repo_path),),
        )


def _observed_head(status: Mapping[str, Any]) -> Optional[str]:
    run_block = status.get("run")
    if isinstance(run_block, dict) and isinstance(run_block.get("head"), str) and run_block["head"]:
        return run_block["head"]
    branch_sync = status.get("branch_sync")
    if not isinstance(branch_sync, dict):
        return None
    pipeline = branch_sync.get("pipeline")
    if isinstance(pipeline, dict) and isinstance(pipeline.get("submitted_head"), str) and pipeline["submitted_head"]:
        return pipeline["submitted_head"]
    local = branch_sync.get("local")
    if isinstance(local, dict) and isinstance(local.get("head"), str) and local["head"]:
        return local["head"]
    return None


def _to_review_finding(finding: Mapping[str, Any], *, index: int, step: Optional[str]) -> dict[str, Any]:
    raw_id = finding.get("id")
    finding_id = f"{raw_id}-{index}" if isinstance(raw_id, str) and raw_id else f"finding-{index}"
    severity_raw = str(finding.get("severity", "")).lower()
    severity = _SEVERITY_MAP.get(severity_raw, _DEFAULT_SEVERITY)
    # Disposition mirrors the overall gate verdict rule: an error-severity
    # finding is blocking; anything else parked at the same gate is still
    # reported (never dropped) but as non-blocking detail, since only the
    # error-severity findings are what no-mistakes' own note text
    # describes as requiring a decision to avoid being silently applied.
    disposition = "blocking" if severity_raw == "error" else "non-blocking"
    category = _category_for(str(raw_id)) if isinstance(raw_id, str) else _DEFAULT_CATEGORY
    description = finding.get("description")
    summary = description if isinstance(description, str) and description else "(no description provided)"
    review_finding: dict[str, Any] = {
        "id": finding_id,
        "severity": severity,
        "disposition": disposition,
        "category": category,
        # no-mistakes does not emit a confidence signal for review
        # findings; "medium" is a documented neutral default, never
        # fabricated as "high" (mapping doc "Limitations").
        "confidence": "medium",
        "status": "open",
        "evidence": [{"kind": "explanation", "summary": summary, "ref": str(raw_id) if raw_id else finding_id}],
    }
    file_path = finding.get("file")
    if isinstance(file_path, str) and file_path:
        review_finding["location"] = {"path": file_path}
    return review_finding


__all__ = ["NoMistakesAssurance"]
