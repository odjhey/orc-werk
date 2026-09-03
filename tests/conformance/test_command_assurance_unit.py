"""Adapter-local command assurance termination, containment, and stdout
tests (`SCN-015`, `docs/adapters/command/conformance.md`).

Traceability (per `docs/adapters/command/conformance.md`'s own evidence
column, made explicit here as stable-ID citations):

- `CONF-ASSURE-006` (exit-status honesty): `test_full_exit_status_table`
  (clean 0/1 map to accepted/rejected; every other exit code maps to
  inconclusive, never guessed) and `test_signal_and_timeout_are_
  inconclusive` (signal termination and timeout both map to inconclusive).
- `CONF-ASSURE-007` (hostile-stdout containment): `test_stdout_validation_
  table_drops_only_enrichment` and `test_oversized_stdout_dropped_and_
  valid_enrichment_transported` -- malformed/oversized/non-portable/non-
  allowlisted stdout never changes verdict/state/fingerprint, and the drop
  itself is recorded in evidence (`stdout_enrichment: "dropped"`).
- `CONF-EXT-004` (canonical fields win): the `"unknown": '{"verdict":
  "rejected"}'` case inside `test_stdout_validation_table_drops_only_
  enrichment` is a stdout payload naming a canonical-looking `verdict`
  field that must not (and does not) override the exit-code-determined
  `"accepted"` verdict actually observed.
- `CONF-EXT-005` (capability honesty): `test_capability_withholding_is_
  constructor_enforced` -- a provider that cannot durably produce
  `CAP-ASSURE-MAY-MUTATE-CANDIDATE`/`CAP-ASSURE-STRUCTURED-FINDINGS`
  semantics does not advertise them; the constructor refuses to accept
  either capability at all.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.command.assurance import CommandAssurance
from orc_werk.core.errors import CoreError
from orc_werk.ports.capabilities import CAP_ASSURE_MAY_MUTATE_CANDIDATE, CAP_ASSURE_STRUCTURED_FINDINGS
from tests.conformance.test_assurance_conformance import _candidate


class CommandAssuranceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.candidate = _candidate("work-1", "exec-1", {"head_sha": "a" * 40, "hostile": "$(touch nope)"})

    def script(self, body: str, name: str = "assure.sh") -> Path:
        path = self.root / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
        return path

    def run_script(self, body: str, *, timeout: float = 2) -> tuple[CommandAssurance, object]:
        path = self.script(body)
        adapter = CommandAssurance(script=path.name, cwd=str(self.root), timeout_s=timeout)
        run = adapter.request(candidate=self.candidate, requirements={"policy": "strict"}, idempotency_key="key")
        return adapter, adapter.inspect(assurance_id=run.id)

    def test_full_exit_status_table(self) -> None:
        for code, verdict in ((0, "accepted"), (1, "rejected"), (2, "inconclusive"), (125, "inconclusive")):
            with self.subTest(code=code):
                _adapter, observed = self.run_script(f"cat >/dev/null\nexit {code}\n")
                self.assertEqual(observed.verdict, verdict)
                self.assertEqual(observed.evidence_refs[0]["exit_code"], code)
                (self.root / "assure.sh").unlink()

    def test_signal_and_timeout_are_inconclusive(self) -> None:
        _adapter, signalled = self.run_script("cat >/dev/null\nkill -TERM $$\n")
        self.assertEqual(signalled.verdict, "inconclusive")
        self.assertLess(signalled.evidence_refs[0]["exit_code"], 0)
        (self.root / "assure.sh").unlink()
        _adapter, timed = self.run_script("cat >/dev/null\nsleep 10\n", timeout=0.05)
        self.assertEqual(timed.verdict, "inconclusive")
        self.assertTrue(timed.evidence_refs[0]["timed_out"])

    def test_stdin_shape_and_no_identity_in_argv_or_environment(self) -> None:
        output = self.root / "stdin.json"
        _adapter, observed = self.run_script(
            f"cat > {output}\nprintf '{{\"evidence_refs\":[{{\"argv_count\":%s}}]}}' \"$#\"\n"
        )
        import json
        document = json.loads(output.read_text())
        self.assertEqual(document["schema"], "command-assurance-input/v1")
        self.assertEqual(document["candidate"]["fingerprint"], self.candidate.fingerprint)
        self.assertEqual(document["assurance_id"].split(":")[0], "command")
        self.assertEqual(observed.evidence_refs[1], {"argv_count": 0})
        self.assertFalse((self.root / "nope").exists())

    def test_synthesized_evidence_hashes_runtime_script_and_settlement_is_immutable(self) -> None:
        path = self.script("cat >/dev/null\nexit 0\n")
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        adapter = CommandAssurance(script=path.name, cwd=str(self.root))
        run = adapter.request(candidate=self.candidate, requirements={}, idempotency_key="key")
        first = adapter.inspect(assurance_id=run.id)
        path.write_text("#!/bin/sh\nexit 1\n")
        second = adapter.inspect(assurance_id=run.id)
        self.assertIs(first, second)
        self.assertEqual(first.evidence_refs[0]["script_sha256"], expected)
        self.assertEqual(first.verdict, "accepted")

    def test_missing_non_executable_and_spawn_failure_are_provider_unavailable(self) -> None:
        for name in ("missing.sh", "plain.sh"):
            if name == "plain.sh":
                (self.root / name).write_text("exit 0\n")
            adapter = CommandAssurance(script=name, cwd=str(self.root))
            with self.assertRaises(CoreError) as ctx:
                adapter.request(candidate=self.candidate, requirements={}, idempotency_key=name)
            self.assertEqual(ctx.exception.error["error"], "ERR-PROVIDER-UNAVAILABLE")

        path = self.script("exit 0\n", "bad-format")
        path.write_bytes(b"not an executable format")
        path.chmod(0o755)
        adapter = CommandAssurance(script=path.name, cwd=str(self.root))
        run = adapter.request(candidate=self.candidate, requirements={}, idempotency_key="spawn")
        with self.assertRaises(CoreError) as ctx:
            adapter.inspect(assurance_id=run.id)
        self.assertEqual(ctx.exception.error["error"], "ERR-PROVIDER-UNAVAILABLE")

    def test_resolved_script_must_be_inside_cwd(self) -> None:
        outside = self.root.parent / f"outside-{os.getpid()}.sh"
        outside.write_text("#!/bin/sh\nexit 0\n")
        outside.chmod(0o755)
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        adapter = CommandAssurance(script=str(outside), cwd=str(self.root))
        with self.assertRaises(CoreError) as ctx:
            adapter.request(candidate=self.candidate, requirements={}, idempotency_key="escape")
        self.assertEqual(ctx.exception.error["error"], "ERR-VALIDATION")

    def test_capability_withholding_is_constructor_enforced(self) -> None:
        path = self.script("exit 0\n")
        for cap in (CAP_ASSURE_MAY_MUTATE_CANDIDATE, CAP_ASSURE_STRUCTURED_FINDINGS):
            with self.assertRaises(ValueError):
                CommandAssurance(script=path.name, cwd=str(self.root), capabilities=[cap])

    def test_stdout_validation_table_drops_only_enrichment(self) -> None:
        cases = {
            "malformed": "not-json",
            "array": "[]",
            "unknown": '{"verdict":"rejected"}',
            "nonportable": '{"evidence_refs":[NaN]}',
            "evidence-shape": '{"evidence_refs":{}}',
            "extensions-shape": '{"extensions":[]}',
            "extension-id": '{"extensions":{"unversioned":{}}}',
            "findings-floor": '{"extensions":{"review-findings/v1":{"findings":[{}]}}}',
        }
        for name, stdout in cases.items():
            with self.subTest(name=name):
                _adapter, observed = self.run_script(f"cat >/dev/null\nprintf '%s' '{stdout}'\nexit 0\n")
                self.assertEqual(observed.verdict, "accepted")
                self.assertEqual(observed.candidate_fingerprint, self.candidate.fingerprint)
                self.assertEqual(observed.evidence_refs[-1]["stdout_enrichment"], "dropped")
                self.assertEqual(dict(observed.extensions), {})
                (self.root / "assure.sh").unlink()

    def test_oversized_stdout_dropped_and_valid_enrichment_transported(self) -> None:
        _adapter, oversized = self.run_script("cat >/dev/null\ndd if=/dev/zero bs=1024 count=257 2>/dev/null | tr '\\0' x\n")
        self.assertEqual(oversized.verdict, "accepted")
        self.assertEqual(oversized.evidence_refs[-1]["reason"], "oversized")
        (self.root / "assure.sh").unlink()
        valid = '{"evidence_refs":[{"report":"ok"}],"extensions":{"custom/v2":{"x":1}}}'
        _adapter, observed = self.run_script(f"cat >/dev/null\nprintf '%s' '{valid}'\nexit 1\n")
        self.assertEqual(observed.verdict, "rejected")
        self.assertEqual(observed.evidence_refs[1], {"report": "ok"})
        self.assertEqual(dict(observed.extensions), {"custom/v2": {"x": 1}})


if __name__ == "__main__":
    unittest.main()
