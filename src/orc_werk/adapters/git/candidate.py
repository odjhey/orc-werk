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
  intended usage) and deliberately participates in the fingerprint like
  every other `subject_identity` field -- excluding it selectively would
  mean inventing a second, adapter-private fingerprint scheme diverging
  from the shared `fingerprint_of` helper for no real benefit at this
  milestone. Callers who want cross-path identity MAY construct with
  `include_repo_path=False`.

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
from pathlib import Path
from typing import Any, Mapping, Optional

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
    ) -> None:
        self._repo_path = repo_path
        self._git_bin = git_bin
        self._include_repo_path = include_repo_path

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

        subject_identity = self._subject_identity(ref)
        if subject_identity is None:
            # PORT-CAND-001: no assurable subject -- not an error.
            return None

        fingerprint = fingerprint_of(subject_identity)
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
        fingerprint = fingerprint_of(subject_identity)
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
    def _work_id_placeholder(execution_id: str) -> str:
        # identify() is not handed a work_id by PORT-CAND-001; the
        # returned Candidate.work_id is synthesized bookkeeping derived
        # only from execution_id, matching ScriptedCandidate's precedent
        # of treating execution_id as the join key for subject lookup.
        return execution_id

    def _subject_identity(self, ref: str) -> Optional[dict[str, Any]]:
        repo_path = Path(self._repo_path)
        if not repo_path.is_dir():
            return None
        head_sha = self._git(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=repo_path)
        if head_sha is None:
            return None
        diff_text = self._git(["diff", "--no-color", ref], cwd=repo_path)
        if diff_text is None:
            return None
        digest = fingerprint_of(diff_text)  # reuse the shared digest helper for the diff text too
        subject_identity: dict[str, Any] = {
            "head_sha": head_sha.strip(),
            "diff_digest": digest.replace("fp-", "sha256:", 1),
        }
        if self._include_repo_path:
            subject_identity["repo_path"] = str(repo_path)
        return subject_identity

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
