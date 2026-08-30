"""GitDiffCandidate (`TASK-M1-005`): `PORT-CANDIDATE` adapter that
fingerprints a real `git` worktree/ref instead of a scripted subject.

`subject_identity` shape (adapter-owned, opaque to the core per
`PORT-CANDIDATE`):

```python
{
  "repo_path": "<configured repository path>",  # present unless disabled
  "head_sha": "<git rev-parse of the identified ref>",
  "diff_digest": "sha256:<truncated-hex>",  # digest of `git diff <ref>` output,
                                             # via the shared fingerprint_of helper
}
```

Field rationale:

- `head_sha` pins the exact commit the candidate is relative to --
  necessary because `git diff` alone is relative and two different base
  commits with textually-identical diffs are not the same candidate.
- `diff_digest` (not the raw diff text) captures uncommitted worktree
  state -- both staged and unstaged changes relative to `head_sha` --
  compactly. `subject_identity` is an identity payload, not an artifact
  store (the same "ref over content" posture `execution-session/v1`'s
  `transcript_ref` takes for the same reason); a short digest is a
  deterministic identity fact, the same size regardless of diff size, and
  never risks the `Candidate` shape becoming a de facto artifact carrier.
- `repo_path` disambiguates candidates across repositories/worktrees. It
  is included by default (this adapter's target use is one Work per one
  configured worktree, so it does not create false negatives in the
  intended usage) and deliberately participates in the fingerprint.
  Callers who want cross-path identity MAY construct with
  `include_repo_path=False`.
- `extensions`, when present, carries adapter-local observation provenance
  and never participates in identity or fingerprinting.

Fingerprinting reuses `orc_werk.adapters.scripted.candidate.fingerprint_of`
-- the same canonical-JSON sha256 helper every other adapter uses, rather
than a second hashing scheme (`CONF-CAND-001`/`CONF-CAND-002` need only
that `subject_identity` be deterministic content; the actual digest
algorithm is shared, not adapter-specific).

Declining (`PORT-CAND-002`'s "never a stale or guessed candidate"): this
adapter returns `None` from `identify()`/`current()` whenever the
requested ref cannot be safely resolved -- not a git repository, an
unborn/empty repository (no commits yet), a `git` binary that cannot be
run, or a requested ref that does not resolve. It never raises for these
cases (`PORT-CAND-001` frames "no assurable subject" as a valid outcome,
not an error); it does raise the canonical `ERR_VALIDATION` for malformed
caller input (a non-portable `artifact_refs`), which is a contract
violation rather than an environmental "can't tell" condition.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from orc_werk.adapters.scripted.candidate import fingerprint_of
from orc_werk.core.errors import validation_error
from orc_werk.core.models import Candidate
from orc_werk.core.portable import is_portable
from orc_werk.ports.candidate import (
    CANDIDATE_COMPARISON_DIFFERENT,
    CANDIDATE_COMPARISON_SAME,
    CandidatePort,
)


class GitDiffCandidate(CandidatePort):
    def __init__(
        self,
        *,
        repo_path: str,
        git_bin: str = "git",
        include_repo_path: bool = True,
        settle_interval: float = 0.05,
        quiescence_retries: int = 3,
        head_reader: Optional[Callable[[str, Path], Optional[str]]] = None,
        lock_present: Optional[Callable[[Path], bool]] = None,
        settle_wait: Callable[[float], None] = time.sleep,
    ) -> None:
        if settle_interval < 0:
            raise ValueError("settle_interval must be non-negative")
        if quiescence_retries < 1:
            raise ValueError("quiescence_retries must be at least 1")
        self._repo_path = repo_path
        self._git_bin = git_bin
        self._include_repo_path = include_repo_path
        self._settle_interval = settle_interval
        self._quiescence_retries = quiescence_retries
        self._head_reader = head_reader
        self._lock_present_hook = lock_present
        self._settle_wait = settle_wait

    def capabilities(self) -> frozenset[str]:
        # CONTRACT-CAPABILITIES defines no CandidatePort capability ids as
        # of this writing (mirrors ScriptedCandidate).
        return frozenset()

    # -- identify / current -------------------------------------------------

    def identify(
        self, *, execution_id: str, artifact_refs: Optional[Mapping[str, Any]] = None
    ) -> Optional[Candidate]:
        if artifact_refs is not None and not is_portable(dict(artifact_refs)):
            raise validation_error(
                "artifact_refs must be portable/JSON-compatible", artifact_refs=artifact_refs
            )
        ref = "HEAD"
        if artifact_refs:
            requested_ref = artifact_refs.get("ref")
            if requested_ref is not None:
                if not isinstance(requested_ref, str) or not requested_ref:
                    raise validation_error(
                        "artifact_refs['ref'] must be a non-empty string",
                        artifact_refs=artifact_refs,
                    )
                ref = requested_ref

        subject_identity = self._subject_identity(ref, confirm_quiescence=True)
        if subject_identity is None:
            # PORT-CAND-001: no assurable subject -- not an error.
            return None

        fingerprint = self._fingerprint(subject_identity)
        candidate_id = f"cand-git-{fingerprint[3:15]}"
        return Candidate(
            id=candidate_id,
            work_id=self._work_id_placeholder(execution_id),
            execution_id=execution_id,
            subject_identity=subject_identity,
            fingerprint=fingerprint,
        )

    def current(self, *, work_id: str) -> Optional[Candidate]:
        subject_identity = self._subject_identity("HEAD")
        if subject_identity is None:
            # PORT-CAND-002: decline explicitly rather than guess.
            return None
        fingerprint = self._fingerprint(subject_identity)
        candidate_id = f"cand-git-{fingerprint[3:15]}"
        return Candidate(
            id=candidate_id,
            work_id=work_id,
            execution_id=f"git-diff-worktree:{work_id}",
            subject_identity=subject_identity,
            fingerprint=fingerprint,
        )

    def compare(self, *, candidate_a: Candidate, candidate_b: Candidate) -> str:
        if candidate_a.fingerprint == candidate_b.fingerprint:
            return CANDIDATE_COMPARISON_SAME
        return CANDIDATE_COMPARISON_DIFFERENT

    # -- git plumbing -------------------------------------------------------

    @staticmethod
    def _fingerprint(subject_identity: Mapping[str, Any]) -> str:
        # Identity is the established Git subject tuple. Adapter-local
        # extensions are observation provenance, never identity material.
        identity = {key: value for key, value in subject_identity.items() if key != "extensions"}
        return fingerprint_of(identity)

    @staticmethod
    def _work_id_placeholder(execution_id: str) -> str:
        # identify() is not handed a work_id by PORT-CAND-001; the
        # returned Candidate.work_id is synthesized bookkeeping derived
        # only from execution_id, matching ScriptedCandidate's precedent
        # of treating execution_id as the join key for subject lookup.
        return execution_id

    def _subject_identity(
        self, ref: str, *, confirm_quiescence: bool = False
    ) -> Optional[dict[str, Any]]:
        repo_path = Path(self._repo_path)
        if not repo_path.is_dir():
            return None

        initial_head = self._read_head(ref, repo_path)
        if initial_head is None:
            return None
        head_sha = initial_head
        advanced = False
        if confirm_quiescence:
            for _ in range(self._quiescence_retries):
                # Observation gate only: neither duration nor wall-clock
                # values enter INV-020 idempotency-key material or candidate data.
                self._settle_wait(self._settle_interval)
                later_head = self._read_head(ref, repo_path)
                if later_head is None:
                    return None
                if later_head != head_sha:
                    advanced = True
                stable = later_head == head_sha
                head_sha = later_head
                if stable and not self._index_lock_present(repo_path):
                    break

        # Pin the diff to the selected observation. Reading the moving ref
        # here would reopen the exact race the confirmation closed.
        diff_text = self._git(["diff", "--no-color", head_sha], cwd=repo_path)
        if diff_text is None:
            return None
        digest = fingerprint_of(diff_text)  # reuse the shared digest helper for the diff text too
        subject_identity: dict[str, Any] = {
            "head_sha": head_sha,
            "diff_digest": digest.replace("fp-", "sha256:", 1),
        }
        if self._include_repo_path:
            subject_identity["repo_path"] = str(repo_path)
        if advanced and head_sha != initial_head:
            note = "worktree advanced during identification; bound the final observed head"
            subject_identity["extensions"] = {
                "git-candidate-identification/v1": {
                    "worktree_advanced": True,
                    "initial_head": initial_head,
                    "bound_head": head_sha,
                    "note": note,
                }
            }
            print(
                "note: worktree advanced during candidate identification "
                f"({initial_head}..{head_sha}); bound {head_sha}",
                file=sys.stderr,
            )
        return subject_identity

    def _read_head(self, ref: str, repo_path: Path) -> Optional[str]:
        if self._head_reader is not None:
            value = self._head_reader(ref, repo_path)
        else:
            value = self._git(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=repo_path)
        return value.strip() if value is not None else None

    def _index_lock_present(self, repo_path: Path) -> bool:
        if self._lock_present_hook is not None:
            return self._lock_present_hook(repo_path)
        lock_path = self._git(["rev-parse", "--git-path", "index.lock"], cwd=repo_path)
        if lock_path is None:
            return False
        path = Path(lock_path.strip())
        if not path.is_absolute():
            path = repo_path / path
        return path.exists()

    def _git(self, args: list[str], *, cwd: Path) -> Optional[str]:
        try:
            proc = subprocess.run(
                [self._git_bin, *args], cwd=cwd, capture_output=True, text=True
            )
        except OSError:
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout


__all__ = ["GitDiffCandidate"]
