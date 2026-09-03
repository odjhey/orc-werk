"""Issue #227 (dev-gate producer conformance) -- operator ruling (2026-09-03,
option 1): "A test-suite check validates extension payloads emitted by orc's
OWN code paths against their registered schemas. Runtime stays fully opaque
(CONF-EXT-006 untouched); adopter/third-party payloads are never policed."

`docs/conformance/extensions.md` (CONF-EXT-001..007) proves generic,
adapter-independent properties (portability, unknown-safety, canonical-win,
core ignorance, ...) about how extension payloads *transport*. Nothing there
checks that a PRODUCER's payload actually matches the shape its own
registered schema promises -- the #223 gap this issue tracks: `orc record`
emitted `execution-session/v1` payloads missing that schema's required
`provider`/`native_session_id` and no test caught it.

This module is that missing guard, scoped exactly to the ruling: dev-only,
test-suite-only, and only for payloads orc's OWN code emits. It does NOT
change any runtime code path (zero `src/` changes in this delivery) and it
never validates a third-party/adopter payload (e.g. `CommandAssurance`'s
subprocess stdout passthrough in `adapters/command/assurance.py`, which is
adopter content orc's own script config merely forwards, not something orc
itself produces).

Two things live here:

1. Validators (`_validate_*`) -- each one hand-encodes one registered
   schema doc's required/optional fields and value constraints as data. The
   doc comment on each validator names the exact file+section it mirrors.
   The docs stay canonical; a validator is a drift guard, not a second
   source of truth -- if a schema doc changes, the validator must be
   updated to match, not the other way around.
2. Tests that exercise the REAL emitting code path (a real `orc record`
   subprocess, a real `GitDiffCandidate.identify()` against a real `git`
   repository) and feed the payload that actually lands in the persisted
   config entry and/or the journaled Fact through the matching validator.

Paper trail -- extension -> emitter(s) -> covered/not-and-why
---------------------------------------------------------------

- `executor-identity/v1` -> `orc record --outcome` (role=ship) and
  `orc record --verdict` (role=verify), both in `src/orc_werk/cli/main.py`
  (`cmd_record`). COVERED: both roles are exercised end to end (CLI
  subprocess -> persisted config entry -> re-dispatch -> journaled Fact
  extensions) and both payloads conform to
  `docs/extensions/executor-identity/v1/schema.md`.

- `review-findings/v1` -> `orc record --verdict --finding TEXT` in the same
  `cmd_record`, which wraps each raw `--finding` string directly into
  `{"findings": [...]}` (`src/orc_werk/cli/main.py`, the
  `extensions["review-findings/v1"] = {"findings": list(args.finding)}`
  line). COVERED: issue #249 amended `docs/extensions/review-findings/schema.md`
  in place (additive, no version bump) so each `findings[]` entry is
  `string | ReviewFinding` -- a bare nonblank string is now a first-class,
  fully conforming "unstructured form" entry, not a violation of the
  structured form's required fields. `test_review_findings_v1_ship_emission_conforms`
  below exercises the real `orc record --finding` emission path end to end
  and asserts it conforms; this used to be
  `test_review_findings_v1_ship_emission_is_a_known_schema_violation`, an
  `@unittest.expectedFailure` before the schema amendment (see #249 and its
  originating issue #227). `CommandAssurance`'s `review-findings/v1`
  passthrough (`adapters/command/assurance.py`) is EXCLUDED from this table
  on purpose -- that payload is adopter/subprocess content orc forwards,
  not content orc itself produces; `_review_findings_floor` there is
  transport-floor policing, not this issue's producer-conformance concern.

- `git-candidate-identification/v1` -> `GitDiffCandidate._subject_identity`
  (`src/orc_werk/adapters/git/candidate.py`), emitted only when
  identification observes the worktree HEAD advance mid-observation.
  COVERED: exercised via a real `identify()` call against a real temporary
  `git` repository, with an injected head-read sequence forcing the advance
  branch (the same technique `tests/conformance/test_git_candidate_conformance.py`
  uses), and the resulting payload conforms to
  `docs/extensions/git-candidate-identification/schema.md`.

- `execution-session/v1` -> NOT EMITTED by any code path in this tree. Prior
  to issue #224 `orc record --outcome` emitted it (that emission carried the
  #223 bug this issue exists because of); post-#224 the ship-outcome path
  emits `artifact_refs` instead and `src/orc_werk/cli/main.py` says so
  explicitly ("execution-session/v1 is reserved for real provider session
  provenance and is no longer emitted here"). The only remaining in-tree
  references (`src/orc_werk/cli/refs.py`, `src/orc_werk/cli/show.py`) only
  *read* `extensions.get("execution-session/v1")` -- they are consumers, not
  producers. NOT COVERED as a live emitter (there is currently no adapter in
  this tree that persists real provider session provenance to exercise), but
  its validator exists and is proven via the historical #223 bug-shape
  fixture below (`test_execution_session_v1_validator_catches_the_223_bug_shape`)
  -- that is this delivery's required "prove it bites" mutation evidence.

- `assurance-context/v1` -> NOT EMITTED by any code path in this tree.
  `src/orc_werk/cli/refs.py` only reads `extensions.get("assurance-context/v1")`.
  `docs/extensions/assurance-context/semantics.md` says a Git-backed
  verification seat SHOULD record this per `PLAYBOOK-AGENT-CLI`, but that is
  documented *operator* practice for a human/agent verify seat, not
  something any in-tree adapter code path emits programmatically. NOT
  COVERED as a live emitter; its validator exists (registry-coverage
  requires one) and is exercised directly against schema-shaped fixtures.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

from orc_werk.adapters.git import GitDiffCandidate
from orc_werk.adapters.jsonl import layout

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
EXTENSIONS_README = REPO_ROOT / "docs" / "extensions" / "README.md"


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args], cwd=root,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=30,
    )


def _journal_facts(root: Path, run_id: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in layout.journal_path(root / ".orc", run_id).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Validators. Each one is a data-encoded mirror of one registered schema
# doc's required/optional fields and value constraints -- NOT a second
# definition of the semantics. Returns a list of human-readable violation
# strings; an empty list means the payload conforms.
# ---------------------------------------------------------------------------


def _validate_executor_identity_v1(payload: Any) -> list[str]:
    """Mirrors `docs/extensions/executor-identity/v1/schema.md`.

    "These four names are the complete field set for `executor-identity/v1`;
    producers MUST NOT add other fields to a v1 payload." / "`role` is
    required and MUST be either `ship` or `verify`." / "`model`,
    `session_ref`, and `seat_ref` are independently optional strings."
    """
    violations: list[str] = []
    if not isinstance(payload, dict):
        return [f"payload must be an object, got {type(payload).__name__}"]
    allowed = {"model", "session_ref", "seat_ref", "role"}
    extra = set(payload) - allowed
    if extra:
        violations.append(f"undeclared field(s) not in the v1 field set: {sorted(extra)}")
    if "role" not in payload:
        violations.append("missing required field: role")
    elif payload["role"] not in ("ship", "verify"):
        violations.append(f"role must be 'ship' or 'verify', got {payload['role']!r}")
    for key in ("model", "session_ref", "seat_ref"):
        if key in payload and not isinstance(payload[key], str):
            violations.append(f"{key} must be a string when present, got {type(payload[key]).__name__}")
    return violations


_REVIEW_SEVERITIES = {"critical", "high", "medium", "low", "info"}
_REVIEW_DISPOSITIONS = {"blocking", "non-blocking"}
_REVIEW_CATEGORIES = {
    "correctness", "security", "contract", "reliability", "performance", "concurrency",
    "data-integrity", "testing", "maintainability", "compatibility", "docs", "style",
}
_REVIEW_CONFIDENCES = {"high", "medium", "low"}
_REVIEW_STATUSES = {"open", "fixed", "accepted", "false-positive", "out-of-scope"}
_REVIEW_EVIDENCE_KINDS = {"explanation", "test", "contract", "reference"}
_REVIEW_REQUIRED = {"id", "severity", "disposition", "category", "confidence", "status", "evidence"}


def _validate_review_findings_v1(payload: Any) -> list[str]:
    """Mirrors `docs/extensions/review-findings/schema.md`.

    Per issue #249's additive amendment, each `findings[]` entry is
    `string | ReviewFinding` ("Entry forms"): a plain nonblank string (the
    unstructured form -- "String form field rules") OR a structured object
    (the structured form, unchanged strictness -- see below). Structured
    entries still carry the required per-finding fields, the closed enums
    for `severity`/`disposition`/`category`/`confidence`/`status`,
    "`evidence` MUST contain at least one entry", and the `location`/
    `evidence` sub-shape rules (1-based line numbers, `end_line >=
    start_line`, evidence `kind` enum).
    """
    violations: list[str] = []
    if not isinstance(payload, dict):
        return [f"payload must be an object, got {type(payload).__name__}"]
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return ["payload.findings must be an array"]
    for i, finding in enumerate(findings):
        prefix = f"findings[{i}]"
        if isinstance(finding, str):
            if not finding.strip():
                violations.append(f"{prefix} string entry must be nonblank")
            continue
        if not isinstance(finding, dict):
            violations.append(f"{prefix} must be a string or an object, got {type(finding).__name__}")
            continue
        missing = _REVIEW_REQUIRED - set(finding)
        if missing:
            violations.append(f"{prefix} missing required field(s): {sorted(missing)}")
            continue
        if finding["severity"] not in _REVIEW_SEVERITIES:
            violations.append(f"{prefix}.severity invalid: {finding['severity']!r}")
        if finding["disposition"] not in _REVIEW_DISPOSITIONS:
            violations.append(f"{prefix}.disposition invalid: {finding['disposition']!r}")
        if finding["category"] not in _REVIEW_CATEGORIES:
            violations.append(f"{prefix}.category invalid: {finding['category']!r}")
        if finding["confidence"] not in _REVIEW_CONFIDENCES:
            violations.append(f"{prefix}.confidence invalid: {finding['confidence']!r}")
        if finding["status"] not in _REVIEW_STATUSES:
            violations.append(f"{prefix}.status invalid: {finding['status']!r}")
        evidence = finding["evidence"]
        if not isinstance(evidence, list) or not evidence:
            violations.append(f"{prefix}.evidence must be a non-empty array")
        else:
            for j, item in enumerate(evidence):
                eprefix = f"{prefix}.evidence[{j}]"
                if not isinstance(item, dict):
                    violations.append(f"{eprefix} must be an object, got {type(item).__name__}")
                    continue
                if item.get("kind") not in _REVIEW_EVIDENCE_KINDS:
                    violations.append(f"{eprefix}.kind invalid: {item.get('kind')!r}")
                if not isinstance(item.get("summary"), str):
                    violations.append(f"{eprefix}.summary must be a string")
                if "ref" in item and not isinstance(item["ref"], str):
                    violations.append(f"{eprefix}.ref must be a string when present")
        location = finding.get("location")
        if location is not None:
            if not isinstance(location, dict) or not isinstance(location.get("path"), str):
                violations.append(f"{prefix}.location must be an object with a string path")
            else:
                start, end = location.get("start_line"), location.get("end_line")
                for name, value in (("start_line", start), ("end_line", end)):
                    if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
                        violations.append(f"{prefix}.location.{name} must be a 1-based positive integer")
                if isinstance(start, int) and isinstance(end, int) and end < start:
                    violations.append(f"{prefix}.location.end_line must be >= start_line")
    return violations


def _validate_git_candidate_identification_v1(payload: Any) -> list[str]:
    """Mirrors `docs/extensions/git-candidate-identification/schema.md`.

    "All fields are required when emitted": `worktree_advanced` (bool),
    `initial_head` (opaque string), `bound_head` (opaque string), `note`
    (opaque string).
    """
    violations: list[str] = []
    if not isinstance(payload, dict):
        return [f"payload must be an object, got {type(payload).__name__}"]
    required_types = {
        "worktree_advanced": bool, "initial_head": str, "bound_head": str, "note": str,
    }
    for key, expected_type in required_types.items():
        if key not in payload:
            violations.append(f"missing required field: {key}")
        elif not isinstance(payload[key], expected_type):
            violations.append(f"{key} must be a {expected_type.__name__}, got {type(payload[key]).__name__}")
    return violations


def _validate_execution_session_v1(payload: Any) -> list[str]:
    """Mirrors `docs/extensions/execution-session/schema.md`.

    Required: `provider`, `native_session_id` ("These two fields identify
    the session; everything else is present only when the adapter has it").
    Optional `resume.strength` closed to `exact`/`best-effort`, optional
    `transcript_ref` (opaque string, "never inlined"), optional `profile`
    fields, and the explicit producer prohibition: "a producer MUST NOT
    emit a `dispatcher` field" (dispatcher/watchtower provenance is a
    separate, unregistered extension).
    """
    violations: list[str] = []
    if not isinstance(payload, dict):
        return [f"payload must be an object, got {type(payload).__name__}"]
    for key in ("provider", "native_session_id"):
        if key not in payload:
            violations.append(f"missing required field: {key}")
        elif not isinstance(payload[key], str):
            violations.append(f"{key} must be a string, got {type(payload[key]).__name__}")
    if "dispatcher" in payload:
        violations.append("producers MUST NOT emit a dispatcher field (out of scope for v1)")
    resume = payload.get("resume")
    if resume is not None:
        if not isinstance(resume, dict):
            violations.append("resume must be an object when present")
        else:
            if resume.get("strength") not in ("exact", "best-effort"):
                violations.append(f"resume.strength must be 'exact' or 'best-effort', got {resume.get('strength')!r}")
            if not isinstance(resume.get("ref"), str):
                violations.append("resume.ref must be a string")
    if "transcript_ref" in payload and payload["transcript_ref"] is not None and not isinstance(payload["transcript_ref"], str):
        violations.append("transcript_ref must be a string when present")
    profile = payload.get("profile")
    if profile is not None:
        if not isinstance(profile, dict):
            violations.append("profile must be an object when present")
        else:
            for key in ("model", "effort", "permission_mode"):
                if key in profile and profile[key] is not None and not isinstance(profile[key], str):
                    violations.append(f"profile.{key} must be a string when present")
            if "fast" in profile and not isinstance(profile["fast"], bool):
                violations.append("profile.fast must be a boolean when present")
    return violations


def _validate_assurance_context_v1(payload: Any) -> list[str]:
    """Mirrors `docs/extensions/assurance-context/schema.md`.

    Required: `base` (object), `base.identity` (opaque string). Optional
    `base.ref`/`base.relation`/`base.derivation_ref`/`base.trial_merge`,
    each independently optional opaque strings.
    """
    violations: list[str] = []
    if not isinstance(payload, dict):
        return [f"payload must be an object, got {type(payload).__name__}"]
    base = payload.get("base")
    if not isinstance(base, dict):
        return ["missing or non-object required field: base"]
    if "identity" not in base:
        violations.append("missing required field: base.identity")
    elif not isinstance(base["identity"], str):
        violations.append("base.identity must be a string")
    for key in ("ref", "relation", "derivation_ref", "trial_merge"):
        if key in base and base[key] is not None and not isinstance(base[key], str):
            violations.append(f"base.{key} must be a string when present")
    return violations


# Every CURRENT registered extension (docs/extensions/README.md) MUST have an
# entry here -- see RegistryCoverageGuardTest below, which fails loudly for
# any registered extension missing from this dict.
VALIDATORS: dict[str, Callable[[Any], list[str]]] = {
    "executor-identity/v1": _validate_executor_identity_v1,
    "review-findings/v1": _validate_review_findings_v1,
    "git-candidate-identification/v1": _validate_git_candidate_identification_v1,
    "execution-session/v1": _validate_execution_session_v1,
    "assurance-context/v1": _validate_assurance_context_v1,
}


# ---------------------------------------------------------------------------
# Registry-coverage guard (deliverable 2): a newly registered extension that
# nobody adds a validator for fails this loudly, on purpose.
# ---------------------------------------------------------------------------


class RegistryCoverageGuardTest(unittest.TestCase):
    def _registered_extension_names(self) -> list[str]:
        text = EXTENSIONS_README.read_text(encoding="utf-8")
        section_match = re.search(
            r"## Registered extensions\n(.*?)\n## ", text, re.DOTALL
        )
        self.assertIsNotNone(section_match, "docs/extensions/README.md's '## Registered extensions' section moved or was renamed")
        section = section_match.group(1)
        # Match only the "... under `payload/vN`" clause each bullet uses to
        # name its payload id -- not every backticked slash-versioned token
        # in the section, which would also pick up parenthetical mentions
        # inside other bullets' prose (e.g. the crew-report bullet below
        # name-drops `execution-session/v1` as its replacement).
        names = re.findall(r"under `([a-z0-9][a-z0-9._-]*/v[0-9]+)`", section)
        self.assertTrue(names, "no registered extension payload names found -- parser drifted from the doc's format")
        return names

    def test_every_current_registered_extension_has_a_validator(self) -> None:
        for name in self._registered_extension_names():
            with self.subTest(extension=name):
                self.assertIn(
                    name, VALIDATORS,
                    f"{name} is registered in docs/extensions/README.md but has no producer-conformance "
                    "validator in tests/conformance/test_extension_producer_conformance.py -- add one "
                    "(mirroring the extension's schema.md) before this can pass",
                )

    def test_superseded_extensions_are_not_in_the_validator_set(self) -> None:
        # Superseded extensions (crew-report/v1, acp-settlement/v1) are
        # retained history only ("do not build against these"); orc no
        # longer emits them and this dev-gate does not validate them.
        text = EXTENSIONS_README.read_text(encoding="utf-8")
        superseded_match = re.search(r"## Superseded extensions\n(.*?)\n## ", text, re.DOTALL)
        self.assertIsNotNone(superseded_match)
        superseded_names = re.findall(r"under `([a-z0-9][a-z0-9._-]*/v[0-9]+)`", superseded_match.group(1))
        self.assertEqual({"crew-report/v1", "acp-settlement/v1"}, set(superseded_names))
        for name in superseded_names:
            self.assertNotIn(name, VALIDATORS, f"{name} is superseded; it must not gain a producer validator")


# ---------------------------------------------------------------------------
# executor-identity/v1 -- COVERED, both roles, real `orc record` subprocess.
# ---------------------------------------------------------------------------


class ExecutorIdentityV1EmissionTest(unittest.TestCase):
    def test_ship_role_via_record_outcome_conforms_at_config_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.json").write_text("{}")
            dispatched = _cli(root, "dispatch", "producer-conformance ship", "--config", str(root / "input.json"),
                               "--run-id", "ship-run", "--journal", str(root / ".orc"))
            self.assertEqual(dispatched.returncode, 3, dispatched.stdout + dispatched.stderr)
            self.assertIn("awaiting=execution-outcome", dispatched.stdout)

            config_path = root / ".orc" / "ship-run" / "config.json"
            data = json.loads(config_path.read_text())
            data.setdefault("attempts", {})["work-1"] = [{"candidate": {"head_sha": "abc"}}]
            config_path.write_text(json.dumps(data))

            recorded = _cli(root, "record", "ship-run", "--work", "work-1", "--outcome", "completed",
                             "--model", "conformance-model", "--session-ref", "sess-1", "--seat-ref", "ship-1",
                             "--journal", str(root / ".orc"))
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

            config_payload = json.loads(config_path.read_text())["attempts"]["work-1"][0]["extensions"]["executor-identity/v1"]
            self.assertEqual(_validate_executor_identity_v1(config_payload), [])

            settled = _cli(root, "dispatch", "--run-id", "ship-run", "--journal", str(root / ".orc"))
            self.assertIn("state=ASSURING", settled.stdout, settled.stdout + settled.stderr)

            facts = _journal_facts(root, "ship-run")
            exec_settled = next(f for f in facts if f["kind"] == "fact" and f["id"] == "FACT-EXEC-SETTLED")
            journal_payload = exec_settled["extensions"]["executor-identity/v1"]
            self.assertEqual(_validate_executor_identity_v1(journal_payload), [])
            self.assertEqual(journal_payload["role"], "ship")

    def test_verify_role_via_record_verdict_conforms_at_config_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.json").write_text(json.dumps(
                {"attempts": {"work-1": [{"outcome": "completed", "candidate": {"head_sha": "right"}}]}}
            ))
            dispatched = _cli(root, "dispatch", "producer-conformance verify", "--config", str(root / "input.json"),
                               "--run-id", "verify-run", "--journal", str(root / ".orc"))
            self.assertEqual(dispatched.returncode, 3, dispatched.stdout + dispatched.stderr)
            self.assertIn("awaiting=assurance-verdict", dispatched.stdout)

            recorded = _cli(root, "record", "verify-run", "--work", "work-1", "--verdict", "accepted",
                             "--model", "conformance-model", "--session-ref", "sess-2", "--seat-ref", "verify-1",
                             "--journal", str(root / ".orc"))
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)

            config_path = root / ".orc" / "verify-run" / "config.json"
            config_payload = json.loads(config_path.read_text())["attempts"]["work-1"][0]["assurance"]["extensions"]["executor-identity/v1"]
            self.assertEqual(_validate_executor_identity_v1(config_payload), [])

            settled = _cli(root, "dispatch", "--run-id", "verify-run", "--journal", str(root / ".orc"))
            self.assertIn("state=ACCEPTED", settled.stdout, settled.stdout + settled.stderr)

            facts = _journal_facts(root, "verify-run")
            assure_settled = next(f for f in facts if f["kind"] == "fact" and f["id"] == "FACT-ASSURE-SETTLED")
            journal_payload = assure_settled["extensions"]["executor-identity/v1"]
            self.assertEqual(_validate_executor_identity_v1(journal_payload), [])
            self.assertEqual(journal_payload["role"], "verify")


# ---------------------------------------------------------------------------
# review-findings/v1 -- COVERED. #249 amended the schema in place (additive,
# no version bump) to admit a plain nonblank string as a first-class
# "unstructured form" findings[] entry alongside the pre-existing structured
# object form. The real orc record --finding emission path now conforms;
# see the module docstring's paper trail entry for the pre-amendment
# history (this test used to be an @unittest.expectedFailure).
# ---------------------------------------------------------------------------


class ReviewFindingsV1EmissionTest(unittest.TestCase):
    def test_review_findings_v1_ship_emission_conforms(self) -> None:
        # `orc record --verdict --finding TEXT` (src/orc_werk/cli/main.py,
        # cmd_record) wraps each raw --finding string directly into
        # {"findings": [...]}: extensions["review-findings/v1"] =
        # {"findings": list(args.finding)}. Post-#249,
        # docs/extensions/review-findings/schema.md's "Entry forms" admits
        # a plain nonblank string as a complete, conforming entry, so this
        # real orc-emitted payload conforms to its own registered schema.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "input.json").write_text(json.dumps(
                {"attempts": {"work-1": [{"outcome": "completed", "candidate": {"head_sha": "right"}}]}}
            ))
            _cli(root, "dispatch", "producer-conformance findings", "--config", str(root / "input.json"),
                 "--run-id", "findings-run", "--journal", str(root / ".orc"))
            recorded = _cli(root, "record", "findings-run", "--work", "work-1", "--verdict", "accepted",
                             "--finding", "looks good", "--journal", str(root / ".orc"))
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
            config_path = root / ".orc" / "findings-run" / "config.json"
            payload = json.loads(config_path.read_text())["attempts"]["work-1"][0]["assurance"]["extensions"]["review-findings/v1"]
            self.assertEqual(_validate_review_findings_v1(payload), [])


# ---------------------------------------------------------------------------
# review-findings/v1 -- #249 union-entry validator fixtures: mixed entries
# valid, an empty-string entry invalid, and a structured object missing
# required fields still invalid (proving object-form strictness survived
# the amendment unchanged).
# ---------------------------------------------------------------------------


class ReviewFindingsV1UnionValidatorFixtureTest(unittest.TestCase):
    def test_mixed_string_and_object_entries_are_valid(self) -> None:
        payload = {
            "findings": [
                "looks good overall",
                {
                    "id": "finding-9",
                    "severity": "medium",
                    "disposition": "non-blocking",
                    "category": "style",
                    "confidence": "medium",
                    "status": "open",
                    "evidence": [{"kind": "explanation", "summary": "Naming is inconsistent."}],
                },
            ]
        }
        self.assertEqual(_validate_review_findings_v1(payload), [])

    def test_empty_string_entry_is_a_violation(self) -> None:
        self.assertEqual(
            _validate_review_findings_v1({"findings": ["   "]}),
            ["findings[0] string entry must be nonblank"],
        )

    def test_object_entry_missing_required_fields_is_still_a_violation(self) -> None:
        violations = _validate_review_findings_v1({"findings": [{"id": "finding-1"}]})
        self.assertEqual(len(violations), 1)
        self.assertIn("findings[0] missing required field(s):", violations[0])


# ---------------------------------------------------------------------------
# git-candidate-identification/v1 -- COVERED, real GitDiffCandidate.identify()
# against a real temporary git repository, forcing the worktree-advanced
# branch the same way tests/conformance/test_git_candidate_conformance.py
# does for its own race-marker assertions.
# ---------------------------------------------------------------------------


def _git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class GitCandidateIdentificationV1EmissionTest(unittest.TestCase):
    def test_worktree_advance_emission_conforms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _git(["init", "-q"], cwd=repo)
            _git(["config", "user.email", "conformance@example.invalid"], cwd=repo)
            _git(["config", "user.name", "Conformance Fixture"], cwd=repo)
            (repo / "a.txt").write_text("x")
            _git(["add", "."], cwd=repo)
            _git(["commit", "-q", "-m", "init"], cwd=repo)
            first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                                    capture_output=True, text=True).stdout.strip()
            (repo / "b.txt").write_text("advance")
            _git(["add", "."], cwd=repo)
            _git(["commit", "-q", "-m", "advance"], cwd=repo)
            later = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                                    capture_output=True, text=True).stdout.strip()
            reads = iter([first, later, later])

            class _AdvancingHeadCandidate(GitDiffCandidate):
                def __init__(self, *, repo_path: str) -> None:
                    super().__init__(repo_path=repo_path)
                    self._settle_wait = lambda _seconds: None

                def _git(self, args: list[str], *, cwd: Path) -> str | None:
                    if args[:2] == ["rev-parse", "--verify"]:
                        return next(reads)
                    return super()._git(args, cwd=cwd)

            adapter = _AdvancingHeadCandidate(repo_path=str(repo))
            candidate = adapter.identify(execution_id="producer-conformance")

            self.assertIsNotNone(candidate)
            payload = candidate.subject_identity["extensions"]["git-candidate-identification/v1"]
            self.assertEqual(_validate_git_candidate_identification_v1(payload), [])
            self.assertTrue(payload["worktree_advanced"])
            self.assertEqual(payload["initial_head"], first)
            self.assertEqual(payload["bound_head"], later)


# ---------------------------------------------------------------------------
# Mutation evidence (deliverable 3): the historical #223 bug shape, applied
# to execution-session/v1 (the extension #223 was actually about) via a
# fixture -- there is no live in-tree emitter left to drive post-#224 (see
# the module docstring's paper trail), which is exactly what the ruling's
# "synthesize via the emitter or a fixture" alternative is for.
# ---------------------------------------------------------------------------


class ExecutionSessionV1MutationEvidenceTest(unittest.TestCase):
    def test_execution_session_v1_validator_catches_the_223_bug_shape(self) -> None:
        # The actual #223 shape (from the #227 issue body): "execution-
        # session/v1 payloads missing that schema's required
        # provider/native_session_id and carrying an undeclared
        # evidence_refs key". Reintroduced here as a fixture, not live
        # code -- #224 already fixed the real emitter (it no longer emits
        # execution-session/v1 at all).
        bug_shape = {"evidence_refs": ["audit.log"]}
        violations = _validate_execution_session_v1(bug_shape)
        self.assertIn("missing required field: provider", violations)
        self.assertIn("missing required field: native_session_id", violations)

        # Restore: a schema-conformant payload passes cleanly, proving the
        # validator actually discriminates rather than failing everything.
        fixed_shape = {"provider": "opaque-provider-a", "native_session_id": "opaque-session-9f2c"}
        self.assertEqual(_validate_execution_session_v1(fixed_shape), [])

    def test_execution_session_v1_validator_rejects_dispatcher_field(self) -> None:
        # docs/extensions/execution-session/schema.md's explicit producer
        # prohibition, exercised as its own fixture (not a #223 shape, but
        # the schema's other named producer violation).
        payload = {
            "provider": "opaque-provider-a", "native_session_id": "opaque-session-9f2c",
            "dispatcher": {"watchtower": "opaque-watchtower-id"},
        }
        self.assertIn(
            "producers MUST NOT emit a dispatcher field (out of scope for v1)",
            _validate_execution_session_v1(payload),
        )


# ---------------------------------------------------------------------------
# assurance-context/v1 -- NOT COVERED as a live emitter (see paper trail);
# validator exercised directly against schema-shaped fixtures so the
# registry-coverage guard has something real to point at.
# ---------------------------------------------------------------------------


class AssuranceContextV1ValidatorTest(unittest.TestCase):
    def test_conformant_fixture_passes(self) -> None:
        payload = {
            "base": {
                "identity": "0123456789abcdef0123456789abcdef01234567",
                "ref": "master", "relation": "merge-base",
                "derivation_ref": "git merge-base origin/master <head_sha>", "trial_merge": "clean",
            }
        }
        self.assertEqual(_validate_assurance_context_v1(payload), [])

    def test_missing_identity_fails(self) -> None:
        self.assertEqual(
            _validate_assurance_context_v1({"base": {"ref": "master"}}),
            ["missing required field: base.identity"],
        )


if __name__ == "__main__":
    unittest.main()
