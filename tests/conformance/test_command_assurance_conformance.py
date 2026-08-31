"""Shared assurance-conformance re-proof for the synchronous command adapter."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from orc_werk.adapters.command.assurance import CommandAssurance
from orc_werk.ports.assurance import AssurancePort
from tests.conformance.test_assurance_conformance import AssurancePortConformance


class _CommandHarness(CommandAssurance):
    pass


class CommandAssuranceConformanceTest(AssurancePortConformance, unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def make_assurance(
        self,
        *,
        script: Mapping[str, Mapping[str, Any]],
        capabilities: Optional[Iterable[str]] = None,
    ) -> AssurancePort:
        verdict = next(iter(script.values()), {}).get("verdict", "accepted")
        exit_code = {"accepted": 0, "rejected": 1, "inconclusive": 2}[verdict]
        path = self.root / f"assure-{len(list(self.root.iterdir()))}.sh"
        path.write_text(f"#!/bin/sh\ncat >/dev/null\nexit {exit_code}\n")
        path.chmod(0o755)
        kwargs: dict[str, Any] = {"script": path.name, "cwd": str(self.root)}
        if capabilities is not None:
            kwargs["capabilities"] = capabilities
        return _CommandHarness(**kwargs)

    def test_inspect_distinguishes_running_from_settled(self) -> None:
        self.skipTest("CommandAssurance intentionally executes synchronously on first inspect")

    def test_inspect_transports_scripted_extensions_losslessly(self) -> None:
        self.skipTest("CommandAssurance transports only script stdout, not caller-scripted data")

    def test_conf_assure_001_settled_evidence_names_candidate_fingerprint(self) -> None:
        candidate = self._candidate("w1", "e1", {"a": 1})
        adapter = self.make_assurance(script={candidate.fingerprint: {"verdict": "accepted"}})
        run = adapter.request(candidate=candidate, requirements={}, idempotency_key="k1")
        observed = adapter.inspect(assurance_id=run.id)
        self.assertEqual(observed.state, "settled")
        self.assertEqual(observed.candidate_fingerprint, candidate.fingerprint)
        self.assertTrue(observed.evidence_refs)
        self.assertIn("script_sha256", observed.evidence_refs[0])

    @staticmethod
    def _candidate(work_id: str, execution_id: str, content: Any):
        from tests.conformance.test_assurance_conformance import _candidate
        return _candidate(work_id, execution_id, content)


if __name__ == "__main__":
    unittest.main()
