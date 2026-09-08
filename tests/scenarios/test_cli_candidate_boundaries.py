"""Issues #289/#295 (`TASK-FIX-289-295`, `SCN-010`'s widened abandon basis,
`STATE-DELIVERY` item 8's verdict-inheritance warning): CLI-level regression
coverage for the two new `orc dispatch` stderr warnings added in
`orc_werk.cli.main`.

- `_warn_git_candidate_divergence` (issue #289): the FIRST real caller of
  `PORT-CAND-002` (`CandidatePort.current`) anywhere in the tree. Fires only
  when a Work's own bound candidate (frozen at `EXECUTING`/`ASSURING`) has a
  fingerprint that no longer matches the live git worktree -- never on a
  scripted candidate (that path is `_warn_candidate_divergence`, already
  covered by `tests/scenarios/test_cli_abandon.py`'s
  `CandidateDivergenceWarningTest`), never as a forced rebind (the frozen
  candidate's identity and any pending/settled assurance judge it exactly
  as before -- this is a warning, not a mutation).
- `_warn_verdict_inheritance` (issue #295): names the prior attempt/verdict
  explicitly when THIS dispatch pass mechanically inherited a settled
  verdict for a re-observed candidate (`STATE-DELIVERY` item 8) instead of
  requesting fresh assurance. Scoped to facts newly appended by THIS pass
  only, and gated by the reducer's own same-`candidate_id` requirement
  (`INV-006`/`INV-007`/`INV-008`) before it ever compares fingerprints, so
  two candidates that merely share a fingerprint under different ids can
  never mis-fire it.

Both real-git shapes below reuse `test_cli_show.py`'s documented
`execution.adapter: "scripted"` + `candidate.adapter: "git"` combination
against a real temporary git repository, since `GitDiffCandidate`'s
`candidate_id` is a pure function of worktree content.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.adapters.jsonl.journal import JSONLJournal
from orc_werk.cli.main import _warn_verdict_inheritance
from orc_werk.core.effects import FX_START_EXECUTION, make_effect
from orc_werk.core.facts import (
    FACT_ASSURE_SETTLED,
    FACT_ASSURE_STARTED,
    FACT_CANDIDATE_OBSERVED,
    FACT_EXEC_SETTLED,
    FACT_EXEC_STARTED,
    FACT_WORK_CREATED,
    FACT_WORK_READY,
    make_fact,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _run_cli(tmp_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=tmp_dir,
        env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )


def _git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], cwd=path)
    _git(["config", "user.email", "candidate-boundaries-test@example.invalid"], cwd=path)
    _git(["config", "user.name", "Candidate Boundaries Test Fixture"], cwd=path)
    (path / "a.txt").write_text("x")
    _git(["add", "."], cwd=path)
    _git(["commit", "-q", "-m", "init"], cwd=path)


class GitCandidateDivergenceCliTest(unittest.TestCase):
    """Issue #289: `orc dispatch` warns when git HEAD has moved past a
    frozen candidate still resting at `ASSURING`, and the frozen candidate's
    own identity/budget arithmetic is provably unaffected by the warning."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        _init_repo(self.repo)
        self.config_path = self.root / "cfg.json"

    def _write_config(self, *, attempts: list) -> None:
        data = {
            "candidate": {"adapter": "git", "repo_path": str(self.repo)},
            "max_attempts": 3,
            "attempts": {"work-1": attempts},
        }
        self.config_path.write_text(json.dumps(data), encoding="utf-8")

    def _dispatch(self, run_id: str) -> subprocess.CompletedProcess:
        return _run_cli(
            self.root, "dispatch", "divergence demo", "--config", str(self.config_path),
            "--journal", "./.orc", "--run-id", run_id,
        )

    def test_head_moves_while_frozen_assuring_warns_without_rebinding(self) -> None:
        run_id = "candidate-divergence-git"
        # 1) Attempt 1 settles execution and observes a real candidate;
        # nothing scripted to bind assurance against yet -- rests ASSURING,
        # unbound, pending.
        self._write_config(attempts=[{"outcome": "completed"}])
        d1 = self._dispatch(run_id)
        self.assertEqual(d1.returncode, 3, msg=d1.stdout + d1.stderr)
        self.assertIn("awaiting=assurance-verdict", d1.stdout)
        self.assertNotIn("diverged", d1.stderr)

        # 2) A REAL worktree change while the candidate is still frozen at
        # ASSURING -- the exact issue #289 shape (external invalidation).
        (self.repo / "a.txt").write_text("changed after freeze")
        _git(["commit", "-aqm", "external change"], cwd=self.repo)

        # 3) Re-dispatch the SAME config (no abandon, no assurance script
        # entry yet) -- the candidate is still unbound so nothing else
        # about the run's state changes, but the live git HEAD no longer
        # matches the frozen fingerprint.
        d2 = self._dispatch(run_id)
        self.assertEqual(d2.returncode, 3, msg=d2.stdout + d2.stderr)
        self.assertIn("awaiting=assurance-verdict", d2.stdout)
        self.assertIn("warning: git HEAD (", d2.stderr)
        self.assertIn("has diverged from the bound attempt-1 candidate", d2.stderr)
        self.assertIn("--abandon-work work-1", d2.stderr)

        # 4) The warning never rebinds anything: supplying a verdict now
        # judges the ORIGINAL frozen candidate exactly as an unchanged
        # worktree would have, and the run accepts on it -- proving the
        # divergence warning is observational only, never a mutation of
        # identity or budget.
        self._write_config(
            attempts=[{"outcome": "completed", "assurance": {"verdict": "accepted"}}]
        )
        d3 = self._dispatch(run_id)
        self.assertEqual(d3.returncode, 0, msg=d3.stdout + d3.stderr)
        self.assertIn("state=ACCEPTED", d3.stdout)
        self.assertIn("attempts=1", d3.stdout)

    def test_unchanged_worktree_never_warns(self) -> None:
        run_id = "candidate-no-divergence-git"
        self._write_config(attempts=[{"outcome": "completed"}])
        d1 = self._dispatch(run_id)
        self.assertEqual(d1.returncode, 3, msg=d1.stdout + d1.stderr)

        # Re-dispatch with NO git change at all.
        d2 = self._dispatch(run_id)
        self.assertEqual(d2.returncode, 3, msg=d2.stdout + d2.stderr)
        self.assertNotIn("diverged", d2.stderr)


class VerdictInheritanceWarningCliTest(unittest.TestCase):
    """Issue #295: the dispatch pass itself names a re-observed candidate's
    inherited verdict explicitly, matching `orc show`'s existing rendering
    of the same mechanical fact (`STATE-DELIVERY` item 8)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        _init_repo(self.repo)
        self.config_path = self.root / "cfg.json"

    def _write_config(self, *, attempts: list) -> None:
        data = {
            "candidate": {"adapter": "git", "repo_path": str(self.repo)},
            "max_attempts": 3,
            "attempts": {"work-1": attempts},
        }
        self.config_path.write_text(json.dumps(data), encoding="utf-8")

    def _dispatch(self, run_id: str) -> subprocess.CompletedProcess:
        return _run_cli(
            self.root, "dispatch", "inheritance demo", "--config", str(self.config_path),
            "--journal", "./.orc", "--run-id", run_id,
        )

    def test_reobserving_unchanged_candidate_warns_inherited_rejected(self) -> None:
        run_id = "candidate-inherit-git"
        self._write_config(attempts=[{"outcome": "completed"}])
        d1 = self._dispatch(run_id)
        self.assertEqual(d1.returncode, 3, msg=d1.stdout + d1.stderr)

        # Bind attempt 1's real fingerprint to a rejected verdict -- settles
        # rejected, retries to attempt 2's execution.
        self._write_config(
            attempts=[{"outcome": "completed", "assurance": {"verdict": "rejected"}}]
        )
        d2 = self._dispatch(run_id)
        self.assertEqual(d2.returncode, 3, msg=d2.stdout + d2.stderr)
        self.assertIn("attempts=2", d2.stdout)
        self.assertNotIn("inherited", d2.stderr)

        # NO git change -- attempt 2 re-observes the IDENTICAL candidate,
        # mechanically inheriting attempt 1's settled verdict with no fresh
        # assurance request this pass. Unchanged-budget semantics: this
        # never consumes assurance/retry budget, so the same pass continues
        # straight on into attempt 3's execution.
        self._write_config(
            attempts=[
                {"outcome": "completed", "assurance": {"verdict": "rejected"}},
                {"outcome": "completed"},
            ]
        )
        d3 = self._dispatch(run_id)
        self.assertEqual(d3.returncode, 3, msg=d3.stdout + d3.stderr)
        self.assertIn("attempts=3", d3.stdout)
        self.assertIn("awaiting=execution-outcome", d3.stdout)
        self.assertIn(
            "warning: work 'work-1' inherited attempt 1's settled verdict (rejected) "
            "for its re-observed candidate",
            d3.stderr,
        )
        self.assertIn("STATE-DELIVERY item 8, verdict inheritance", d3.stderr)


class ScriptedDifferingIdSameFingerprintNoFalseWarningTest(unittest.TestCase):
    """Issue #295 (no-false-positive clause): a scripted candidate whose
    fingerprint happens to collide with an earlier, DIFFERENT candidate_id's
    settled fingerprint is never mistaken for inheritance -- the reducer's
    own `INV-006`/`INV-007`/`INV-008` gate requires the SAME `candidate_id`
    before it ever compares fingerprints, so this is an ordinary fresh
    observation, not a re-observation."""

    def test_matching_fingerprint_different_id_requests_fresh_assurance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "cfg.json"
            run_id = "scripted-same-fp-different-id"

            config_path.write_text(json.dumps({
                "max_attempts": 3,
                "attempts": {
                    "work-1": [
                        {
                            "candidate": {"id": "cand-A", "fingerprint": "fp-shared"},
                            "outcome": "completed",
                            "assurance": {"verdict": "rejected"},
                        }
                    ]
                },
            }), encoding="utf-8")
            d1 = _run_cli(
                root, "dispatch", "collision demo", "--config", str(config_path),
                "--journal", "./.orc", "--run-id", run_id,
            )
            self.assertEqual(d1.returncode, 3, msg=d1.stdout + d1.stderr)
            self.assertIn("attempts=2", d1.stdout)

            # Attempt 2 configures a DIFFERENT candidate_id that happens to
            # share the exact same fingerprint string as attempt 1's own
            # settled candidate. The reducer never even looks at the
            # fingerprint for a candidate_id it has not seen before -- this
            # is a brand-new candidate, so a fresh assurance is requested,
            # never an inherited verdict.
            config_path.write_text(json.dumps({
                "max_attempts": 3,
                "attempts": {
                    "work-1": [
                        {
                            "candidate": {"id": "cand-A", "fingerprint": "fp-shared"},
                            "outcome": "completed",
                            "assurance": {"verdict": "rejected"},
                        },
                        {
                            "candidate": {"id": "cand-B", "fingerprint": "fp-shared"},
                            "outcome": "completed",
                        },
                    ]
                },
            }), encoding="utf-8")
            d2 = _run_cli(
                root, "dispatch", "collision demo", "--config", str(config_path),
                "--journal", "./.orc", "--run-id", run_id,
            )
            self.assertEqual(d2.returncode, 3, msg=d2.stdout + d2.stderr)
            self.assertIn("awaiting=assurance-verdict", d2.stdout)
            self.assertNotIn("inherited", d2.stderr)


class WarnVerdictInheritanceUnitTest(unittest.TestCase):
    """Issue #295 (VerifyBoundaries309's attempt-2 rejection): a direct,
    adapter-independent unit test of `_warn_verdict_inheritance` itself --
    the real git/scripted `CandidatePort` adapters both derive `candidate_
    id` from a prefix of the fingerprint they compute (`cand-git-<fp[3:15]>`
    / `cand-<execution_id>-<fp[3:15]>`), so a genuine same-`candidate_id`-
    different-fingerprint re-observation cannot be constructed through a
    real `orc dispatch` -- exactly the shape `PORT-CANDIDATE` nonetheless
    permits for a different adapter (e.g. a stable PR-number id with a
    content-derived fingerprint). Hand-crafts the journal records the
    reducer would produce so the helper's own identity gate is exercised
    directly, independent of any specific adapter's id-derivation scheme."""

    @staticmethod
    def _settled(work_id: str, *, candidate_id: str, fingerprint: str, verdict: str) -> list[dict]:
        return [
            {
                "kind": "effect", "id": "FX-START-EXECUTION",
                "data": {"work_id": work_id, "attempt_number": 1},
            },
            {
                "kind": "fact", "id": "FACT-CANDIDATE-OBSERVED",
                "data": {"work_id": work_id, "candidate_id": candidate_id, "fingerprint": fingerprint},
            },
            {"kind": "fact", "id": "FACT-ASSURE-SETTLED", "data": {"work_id": work_id, "verdict": verdict}},
        ]

    @staticmethod
    def _observed(work_id: str, *, candidate_id: str, fingerprint: str) -> dict:
        return {
            "kind": "fact", "id": "FACT-CANDIDATE-OBSERVED",
            "data": {"work_id": work_id, "candidate_id": candidate_id, "fingerprint": fingerprint},
        }

    def test_same_id_different_fingerprint_never_warns_inherited(self) -> None:
        history_before_advance = self._settled("w1", candidate_id="cand-A", fingerprint="fp-1", verdict="rejected")
        new_records = [self._observed("w1", candidate_id="cand-A", fingerprint="fp-2")]
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            _warn_verdict_inheritance(new_records, history_before_advance)
        self.assertEqual(stderr.getvalue(), "")

    def test_same_id_same_fingerprint_warns_inherited(self) -> None:
        history_before_advance = self._settled("w1", candidate_id="cand-A", fingerprint="fp-1", verdict="rejected")
        new_records = [self._observed("w1", candidate_id="cand-A", fingerprint="fp-1")]
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            _warn_verdict_inheritance(new_records, history_before_advance)
        self.assertIn("inherited attempt", stderr.getvalue())
        self.assertIn("STATE-DELIVERY item 8, verdict inheritance", stderr.getvalue())


class ShowRealJournalFingerprintMismatchConflictTest(unittest.TestCase):
    """Issue #295 (VerifyBoundaries309's rejection of attempt 3, AGENTS.md
    rule 18): a same-`candidate_id`/different-fingerprint re-observation is
    structurally unreachable through any real `orc dispatch` -- every
    built-in `CandidatePort` adapter derives `candidate_id` from a prefix
    of its own fingerprint (`WarnVerdictInheritanceUnitTest`'s docstring
    above) -- but `PORT-CANDIDATE` nonetheless permits it for a different
    adapter, and the reducer must still resolve it as an unresolved
    candidate-observation conflict (`STATE-DELIVERY` item 9), never a
    mechanically inherited verdict. Hand-crafts a reducer-valid
    `JSONLJournal` history directly (bypassing every adapter, `orc_werk.
    core.facts.make_fact` / `orc_werk.core.effects.make_effect`) and drives
    the REAL `orc show` consumer against it, so a regression in
    `_settled_fingerprints_by_work`'s identity keying is caught at the
    observable CLI contract -- not just the internal helper's own unit
    tests, which stay green independent of `show.py`'s own rendering."""

    def test_reobserved_candidate_with_mismatched_fingerprint_shows_conflict_not_inherited(self) -> None:
        drid = "collision-show"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = JSONLJournal(root / ".orc")
            journal.append_fact(make_fact(FACT_WORK_CREATED, delivery_run_id=drid, work_id="w1"))
            journal.append_fact(make_fact(FACT_WORK_READY, delivery_run_id=drid, work_id="w1"))

            # Attempt 1: executes, observes candidate cand-A/fp-1, rejected
            # (attempt_number 1 < the reducer's schema-default budget of 3,
            # so this settles to READY rather than BLOCKED).
            journal.append_effect_record(
                make_effect(
                    FX_START_EXECUTION,
                    delivery_run_id=drid,
                    work_id="w1",
                    idempotency_key=f"{drid}|w1|1|FX-START-EXECUTION",
                    data={"attempt_number": 1},
                ),
                dispatch_result={"status": "ok"},
            )
            journal.append_fact(make_fact(FACT_EXEC_STARTED, delivery_run_id=drid, work_id="w1", execution_id="e1"))
            journal.append_fact(
                make_fact(
                    FACT_EXEC_SETTLED, delivery_run_id=drid, work_id="w1", execution_id="e1", outcome="completed"
                )
            )
            journal.append_fact(
                make_fact(
                    FACT_CANDIDATE_OBSERVED,
                    delivery_run_id=drid,
                    work_id="w1",
                    candidate_id="cand-A",
                    fingerprint="fp-1",
                    execution_id="e1",
                )
            )
            journal.append_fact(
                make_fact(
                    FACT_ASSURE_STARTED, delivery_run_id=drid, work_id="w1", assurance_id="a1", candidate_id="cand-A"
                )
            )
            journal.append_fact(
                make_fact(
                    FACT_ASSURE_SETTLED,
                    delivery_run_id=drid,
                    work_id="w1",
                    assurance_id="a1",
                    candidate_fingerprint="fp-1",
                    verdict="rejected",
                )
            )

            # Attempt 2: executes, re-observes the SAME candidate_id with a
            # DIFFERENT fingerprint -- a genuinely new/changed Candidate the
            # (hypothetical) adapter authored, never a re-vote on attempt
            # 1's already-rejected head.
            journal.append_effect_record(
                make_effect(
                    FX_START_EXECUTION,
                    delivery_run_id=drid,
                    work_id="w1",
                    idempotency_key=f"{drid}|w1|2|FX-START-EXECUTION",
                    data={"attempt_number": 2},
                ),
                dispatch_result={"status": "ok"},
            )
            journal.append_fact(make_fact(FACT_EXEC_STARTED, delivery_run_id=drid, work_id="w1", execution_id="e2"))
            journal.append_fact(
                make_fact(
                    FACT_EXEC_SETTLED, delivery_run_id=drid, work_id="w1", execution_id="e2", outcome="completed"
                )
            )
            journal.append_fact(
                make_fact(
                    FACT_CANDIDATE_OBSERVED,
                    delivery_run_id=drid,
                    work_id="w1",
                    candidate_id="cand-A",
                    fingerprint="fp-2",
                    execution_id="e2",
                )
            )
            del journal  # release the journal's own file handles before the subprocess re-reads it.

            result = _run_cli(root, "show", drid, "--journal", "./.orc")
            self.assertEqual(result.returncode, 3, msg=result.stdout + result.stderr)
            out = result.stdout
            self.assertIn("candidate-observation conflict", out)
            self.assertIn("STATE-DELIVERY item 9", out)
            self.assertNotIn("inherited", out)


if __name__ == "__main__":
    unittest.main()
