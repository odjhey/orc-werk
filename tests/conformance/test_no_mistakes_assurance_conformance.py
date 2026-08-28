"""`CONF-ASSURE-*` conformance for `NoMistakesAssurance` (`TASK-M2-001`),
driven against a fake `no-mistakes` executable on `PATH` (`tests/
conformance/support_no_mistakes_stub.py`) -- no real `no-mistakes`
install/daemon/agent required. Mirrors `test_acp_execution_conformance.py`'s
stub-subprocess pattern for `AcpExecution`.

This reuses the exact same `AssurancePortConformance` mixin
`ScriptedAssuranceConformanceTest` runs (`test_assurance_conformance.py`),
via `_StubNoMistakesAssuranceHarness`: a thin `AssurancePort` wrapper that
delegates every real operation to a genuine `NoMistakesAssurance` instance
talking to the fake binary over a real subprocess boundary, translating
the mixin's per-fingerprint `script` (verdict/states) into stub-world
mutations applied just before each scripted `inspect()` call settles --
mirroring how `ScriptedAssurance` itself walks a `states` list.

`CONF-ASSURE-003` ("evidence from a different fingerprint is rejected by
the kernel") is deliberately not re-exercised here -- per
`test_assurance_conformance.py`'s own docstring, it is core's job
(`orc_werk.core.reducer`), already proven generically by
`Conf003ForeignFingerprintRejectedByKernelTest` there. This adapter's only
obligation toward it is faithfully reporting the fingerprint it actually
evaluated (`INV-007`), which `test_conf_assure_001` below already covers.

Two mixin tests are overridden -- one with a documented skip, one with a
documented adaptation -- both for the same underlying reason `AcpExecution`
overrides two of its own: a real, provider-driven adapter cannot honor a
caller-scripted passthrough payload the way a test double can.

- `test_inspect_transports_scripted_extensions_losslessly` assumes
  `inspect()` echoes back caller-scripted `extensions` verbatim.
  `NoMistakesAssurance.inspect()`'s `extensions` are always this adapter's
  own `review-findings/v1` derived from real observed gate findings (see
  `docs/adapters/no-mistakes/mapping.md`) -- there is no channel for a
  caller to hand it arbitrary opaque data at `request()` time and have it
  echoed back unchanged.
- `test_conf_assure_001_settled_evidence_names_candidate_fingerprint`'s
  own normative concern (settled state + exact candidate-fingerprint
  naming) is preserved verbatim; only its incidental
  `assertIn("report-1", observed.evidence_refs)` assertion -- which
  assumes a caller-scripted, passthrough `evidence_refs` string a real
  adapter cannot honor -- is replaced with an assertion appropriate to
  this adapter's real, structured `evidence_refs` shape (see
  `_evidence_ref` in `assurance.py`).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from orc_werk.adapters.no_mistakes.assurance import NoMistakesAssurance
from orc_werk.core.models import AssuranceRun, Candidate
from orc_werk.ports.assurance import AssuranceObservation, AssurancePort
from orc_werk.ports.base import LIFECYCLE_STATE_SETTLED
from tests.conformance.support_no_mistakes_stub import NoMistakesStubWorld
from tests.conformance.test_assurance_conformance import AssurancePortConformance


class _StubNoMistakesAssuranceHarness(AssurancePort):
    """See module docstring. Delegates every operation to a real
    `NoMistakesAssurance` instance talking to the fake binary; translates
    the mixin's `script` (keyed by candidate fingerprint) into stub-world
    mutations applied just-in-time as each scripted `inspect()` call's
    `states` entry reaches `"settled"`."""

    def __init__(
        self,
        *,
        script: Mapping[str, Mapping[str, Any]],
        capabilities: Iterable[str],
        world: NoMistakesStubWorld,
    ) -> None:
        self._script = {fp: dict(entry) for fp, entry in script.items()}
        self._world = world
        kwargs: dict[str, Any] = {
            "repo_path": world.repo_path,
            "env": world.env(),
            "spawn_poll_timeout_s": 2.0,
            "spawn_poll_interval_s": 0.02,
        }
        if capabilities:
            kwargs["capabilities"] = tuple(capabilities)
        self._real = NoMistakesAssurance(**kwargs)
        self._fingerprint_by_assurance_id: dict[str, str] = {}
        self._inspect_calls: dict[str, int] = {}

    def capabilities(self) -> frozenset[str]:
        return self._real.capabilities()

    def request(
        self, *, candidate: Candidate, requirements: Mapping[str, Any], idempotency_key: str
    ) -> AssuranceRun:
        req = dict(requirements)
        req.setdefault("intent", "conformance-fixture-intent")
        run = self._real.request(candidate=candidate, requirements=req, idempotency_key=idempotency_key)
        self._fingerprint_by_assurance_id.setdefault(run.id, candidate.fingerprint)
        self._inspect_calls.setdefault(run.id, 0)
        return run

    def inspect(self, *, assurance_id: str) -> AssuranceObservation:
        fingerprint = self._fingerprint_by_assurance_id.get(assurance_id)
        entry = self._script.get(fingerprint) if fingerprint is not None else None
        if entry is not None:
            states = list(entry.get("states", ["settled"]))
            call_index = self._inspect_calls.get(assurance_id, 0)
            self._inspect_calls[assurance_id] = call_index + 1
            state = states[min(call_index, len(states) - 1)]
            if state == LIFECYCLE_STATE_SETTLED:
                self._apply_settlement(assurance_id, entry)
        return self._real.inspect(assurance_id=assurance_id)

    def _apply_settlement(self, assurance_id: str, entry: Mapping[str, Any]) -> None:
        # assurance_id shape: "no-mistakes:<fingerprint>:<native_run_id>:<repo_path>"
        # (see assurance.py's _assurance_id/_parse_assurance_id).
        parts = assurance_id.split(":", 3)
        native_run_id = parts[2]
        verdict = entry.get("verdict")
        if verdict == "accepted":
            self._world.set_outcome(native_run_id, "passed")
        elif verdict == "rejected":
            self._world.set_outcome(native_run_id, "failed")
        elif verdict == "inconclusive":
            self._world.set_status(native_run_id, "cancelled")


class NoMistakesAssuranceConformanceTest(AssurancePortConformance, unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._world = NoMistakesStubWorld(Path(self._tmp.name))

    def make_assurance(
        self,
        *,
        script: Mapping[str, Mapping[str, Any]],
        capabilities: Optional[Iterable[str]] = None,
    ) -> AssurancePort:
        return _StubNoMistakesAssuranceHarness(
            script=script, capabilities=capabilities or (), world=self._world
        )

    # -- documented overrides: see module docstring. --

    def test_inspect_transports_scripted_extensions_losslessly(self) -> None:
        self.skipTest(
            "NoMistakesAssurance derives extensions from real observed gate findings "
            "(review-findings/v1), not from caller-scripted passthrough content -- "
            "see docs/adapters/no-mistakes/mapping.md 'Lossy mappings'."
        )

    def test_conf_assure_001_settled_evidence_names_candidate_fingerprint(self) -> None:
        candidate = self._candidate_via_mixin("w1", "e1", {"a": 1})
        adapter = self.make_assurance(script={candidate.fingerprint: {"verdict": "accepted"}})
        run = adapter.request(candidate=candidate, requirements={}, idempotency_key="k1")
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.state, LIFECYCLE_STATE_SETTLED)
        # CONF-ASSURE-001's own normative concern: settled evidence names
        # the exact candidate fingerprint this run was bound to.
        self.assertEqual(observed.candidate_fingerprint, candidate.fingerprint)
        # This adapter's real, structured evidence_refs shape (never a
        # caller-scripted passthrough string -- see class docstring):
        # non-empty, and each entry externally resolvable via a real
        # no-mistakes run id, never narrative prose.
        self.assertTrue(observed.evidence_refs)
        for ref in observed.evidence_refs:
            self.assertIn("no_mistakes_run_id", ref)
            self.assertIn("command", ref)

    @staticmethod
    def _candidate_via_mixin(work_id: str, execution_id: str, content: Any) -> Candidate:
        from tests.conformance.test_assurance_conformance import _candidate

        return _candidate(work_id, execution_id, content)


if __name__ == "__main__":
    unittest.main()
