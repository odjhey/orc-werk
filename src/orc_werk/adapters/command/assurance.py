"""Generic, judge-only ``PORT-ASSURANCE`` adapter over an in-repo script.

The adapter-local contract is ``ADAPTER-COMMAND-MAPPING``. Candidate identity
crosses the subprocess boundary only as ``command-assurance-input/v1`` JSON on
stdin. The configured script is invoked as a one-element argv list without a
shell; stdout is bounded, untrusted enrichment and can never select canonical
verdict, state, or fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from orc_werk.core.errors import CoreError, ERR_PROVIDER_UNAVAILABLE, canonical_error, not_found_error, validation_error
from orc_werk.core.models import AssuranceRun, Candidate
from orc_werk.core.portable import is_portable
from orc_werk.ports.assurance import AssuranceObservation, AssurancePort
from orc_werk.ports.base import LIFECYCLE_STATE_SETTLED
from orc_werk.ports.capabilities import (
    CAP_ASSURE_CANDIDATE_BOUND,
    CAP_ASSURE_STRUCTURED_VERDICT,
    validate_capabilities,
)

_INPUT_SCHEMA = "command-assurance-input/v1"
_STDOUT_CAP_BYTES = 256 * 1024
_EXTENSION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*/v[1-9][0-9]*$")
_REVIEW_REQUIRED = frozenset({"id", "severity", "disposition", "category", "confidence", "status", "evidence"})
_ADVERTISABLE_CAPABILITIES = frozenset({CAP_ASSURE_CANDIDATE_BOUND, CAP_ASSURE_STRUCTURED_VERDICT})
_DEFAULT_TIMEOUT_S = 300.0


def _provider_unavailable(message: str, **details: Any) -> CoreError:
    return CoreError(canonical_error(ERR_PROVIDER_UNAVAILABLE, message, **details))


def _assurance_id(fingerprint: str, idempotency_key: str) -> str:
    suffix = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
    return f"command:{fingerprint}:{suffix}"


def _parse_assurance_id(value: str) -> str:
    parts = value.split(":")
    if len(parts) != 3 or parts[0] != "command" or not parts[1].startswith("fp-") or len(parts[2]) != 16:
        raise not_found_error("assurance_id is not a recognizable CommandAssurance reference", assurance_id=value)
    return parts[1]


def _review_findings_floor(payload: Any) -> bool:
    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
        return False
    for finding in payload["findings"]:
        if not isinstance(finding, dict) or not _REVIEW_REQUIRED.issubset(finding):
            return False
        evidence = finding.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return False
    return True


def _validated_enrichment(raw: bytes) -> tuple[list[Any], dict[str, Any], str | None]:
    if not raw:
        return [], {}, None
    if len(raw) > _STDOUT_CAP_BYTES:
        return [], {}, "oversized"
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return [], {}, "malformed-json"
    if not isinstance(value, dict):
        return [], {}, "not-an-object"
    if set(value) - {"evidence_refs", "extensions"}:
        return [], {}, "non-allowlisted-key"
    if not is_portable(value):
        return [], {}, "non-portable"
    evidence = value.get("evidence_refs", [])
    extensions = value.get("extensions", {})
    if not isinstance(evidence, list):
        return [], {}, "evidence-refs-not-list"
    if not isinstance(extensions, dict):
        return [], {}, "extensions-not-object"
    if any(not isinstance(key, str) or _EXTENSION_ID.fullmatch(key) is None for key in extensions):
        return [], {}, "invalid-extension-id"
    if "review-findings/v1" in extensions and not _review_findings_floor(extensions["review-findings/v1"]):
        return [], {}, "review-findings-schema-floor"
    return evidence, extensions, None


class CommandAssurance(AssurancePort):
    """Run one configured, cwd-contained verifier script on first inspect."""

    def __init__(
        self,
        *,
        script: str,
        cwd: str,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        capabilities: Iterable[str] = _ADVERTISABLE_CAPABILITIES,
    ) -> None:
        if not isinstance(script, str) or not script:
            raise validation_error("command assurance script must be a non-empty string")
        if not isinstance(cwd, str) or not cwd:
            raise validation_error("command assurance cwd must be a non-empty string")
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
            raise validation_error("command assurance timeout_s must be a positive number", timeout_s=timeout_s)
        caps = validate_capabilities(capabilities)
        unsupported = caps - _ADVERTISABLE_CAPABILITIES
        if unsupported:
            raise ValueError(f"CommandAssurance cannot advertise {sorted(unsupported)}")
        self._script_config = script
        self._cwd = Path(cwd).resolve()
        self._timeout_s = float(timeout_s)
        self._capabilities = caps
        self._by_key: dict[str, AssuranceRun] = {}
        self._request_by_id: dict[str, tuple[Candidate, Mapping[str, Any], Path]] = {}
        self._settled: dict[str, AssuranceObservation] = {}

    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    def _resolve_script(self) -> Path:
        configured = Path(self._script_config)
        resolved = (self._cwd / configured).resolve() if not configured.is_absolute() else configured.resolve()
        try:
            resolved.relative_to(self._cwd)
        except ValueError as exc:
            raise validation_error(
                "command assurance script must resolve inside cwd",
                script=self._script_config,
                resolved_script=str(resolved),
                cwd=str(self._cwd),
            ) from exc
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise _provider_unavailable(
                "command assurance script is missing or not executable",
                script=str(resolved),
                cwd=str(self._cwd),
            )
        return resolved

    def request(
        self,
        *,
        candidate: Candidate,
        requirements: Mapping[str, Any],
        idempotency_key: str,
    ) -> AssuranceRun:
        cached = self._by_key.get(idempotency_key)
        if cached is not None:
            return cached
        script = self._resolve_script()
        document = {
            "schema": _INPUT_SCHEMA,
            "candidate": {
                "id": candidate.id,
                "work_id": candidate.work_id,
                "execution_id": candidate.execution_id,
                "fingerprint": candidate.fingerprint,
                "subject_identity": candidate.subject_identity,
            },
            "requirements": dict(requirements),
            "assurance_id": _assurance_id(candidate.fingerprint, idempotency_key),
        }
        if not is_portable(document):
            raise validation_error("command assurance input must be portable JSON")
        run = AssuranceRun(id=document["assurance_id"], candidate_id=candidate.id)
        self._by_key[idempotency_key] = run
        self._request_by_id[run.id] = (candidate, document, script)
        return run

    def inspect(self, *, assurance_id: str) -> AssuranceObservation:
        fingerprint = _parse_assurance_id(assurance_id)
        if assurance_id in self._settled:
            return self._settled[assurance_id]
        request = self._request_by_id.get(assurance_id)
        if request is None:
            raise not_found_error(
                "CommandAssurance request is unavailable in this process",
                assurance_id=assurance_id,
            )
        _candidate, document, requested_script = request
        # Re-resolve at execution time so path replacement/escape cannot occur
        # between request and inspect. A changed in-repo file is permitted and
        # made explicit by the run-time content hash.
        script = self._resolve_script()
        if script != requested_script:
            raise validation_error("command assurance script resolution changed after request")
        try:
            script_hash = hashlib.sha256(script.read_bytes()).hexdigest()
        except OSError as exc:
            raise _provider_unavailable("failed to read command assurance script", script=str(script)) from exc

        stdin_bytes = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        started = time.monotonic()
        timed_out = False
        returncode: int
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                proc = subprocess.Popen(
                    [str(script)],
                    cwd=str(self._cwd),
                    stdin=subprocess.PIPE,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    shell=False,
                    start_new_session=True,
                )
            except OSError as exc:
                raise _provider_unavailable("failed to execute command assurance script", script=str(script)) from exc
            try:
                proc.communicate(input=stdin_bytes, timeout=self._timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
            returncode = proc.returncode
            stdout_file.seek(0)
            raw_stdout = stdout_file.read(_STDOUT_CAP_BYTES + 1)

        duration = max(0.0, time.monotonic() - started)
        verdict = "accepted" if not timed_out and returncode == 0 else "rejected" if not timed_out and returncode == 1 else "inconclusive"
        extra_evidence, extensions, drop_reason = _validated_enrichment(raw_stdout)
        synthesized = {
            "script": str(script),
            "script_sha256": script_hash,
            "exit_code": returncode,
            "duration_s": duration,
            "timed_out": timed_out,
        }
        evidence: list[Any] = [synthesized, *extra_evidence]
        if drop_reason is not None:
            evidence.append({"stdout_enrichment": "dropped", "reason": drop_reason})
        observation = AssuranceObservation(
            state=LIFECYCLE_STATE_SETTLED,
            verdict=verdict,
            candidate_fingerprint=fingerprint,
            evidence_refs=tuple(evidence),
            extensions=extensions,
        )
        self._settled[assurance_id] = observation
        return observation


__all__ = ["CommandAssurance"]
