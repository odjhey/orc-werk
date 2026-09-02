"""`BeadsMirror` (`TASK-M2-006`): a write-only projection of one
`DeliveryRun`'s journal-derived run/work state and briefs into a shared,
label-scoped `bd` (Beads) database.

**Not a `PORT-WORK-GRAPH` implementation.** This adapter claims no
conformance to that port and implements none of its interface
(`create`/`ready`/`claim`/`complete`/`block`). It is a pure observer: every
public entry point reads `MemoryWorkGraph`/journal-derived state
(`JournalPort.history`, `DeliveryProjection`) and issues `bd` CLI
subprocess calls; nothing it writes to `bd` is ever read back by this
module or any caller, and no `bd` state ever feeds a dispatch decision.
`bd`-native ready/claim/dependency logic driving real dispatch decisions
("authority graduation") is a dormant, unbuilt future path recorded on
issue #47 -- explicitly out of scope here.

All `bd` vocabulary (CLI flags, id/label discipline, status/metadata
mapping) stays in this module and `docs/adapters/beads/mapping.md`, per
`INV-014` and `docs/adapters/README.md`. Full design rationale, the
empirical recon this module's choices are pinned to, and the status/
metadata vocabulary table live in that mapping doc -- this module's
comments cover *why the code does what it does*, not a restatement of the
recon.

Design summary (full rationale: the mapping doc):

- Direct `bd --json <verb>` CLI subprocess invocations, one process per
  operation -- matching the historical acp/no-mistakes adapter pattern
  those since-removed adapters established (`ADR-0005`). No daemon, no
  streams, synchronous ops (`bd` is the "easy instance" of this pattern
  per the task card).
- Deterministic `--id <delivery_run_id>--<work_id>` on every `bd create`
  (`INV-020` replay-stable naming; `bd`'s own generated ids are random).
  `bd create --id <id>` REQUIRES `--force` whenever `<id>` does not start
  with the target database's own configured prefix (confirmed empirically,
  this task's recon) -- every create call therefore always passes
  `--force`.
- `--label run:<delivery_run_id>` on every `bd create` -- the shared-DB
  isolation discipline the ratified mirror-mode posture (issue #47)
  depends on. `update`/`close` calls address the run-qualified unique id
  directly and do not strip labels (verified against real bd 1.2.2), so
  create-time application persists -- see the mapping doc's "Label
  discipline" section.
- `bd create --graph` is NOT used, despite being named in the task card's
  inherited design: empirically (this task's recon), `bd create --graph`
  1.2.2's graph-plan JSON schema has no per-node `id` field (silently
  dropped, ids are always `bd`-auto-generated) and `--parent`/`--id` are
  mutually exclusive flags -- both structurally incompatible with the
  deterministic-id requirement above, which is also non-negotiable. This
  adapter instead issues one `bd create --id ... --force --label ... --deps
  ...` call per Work, in dependency-first (topological) order, plus a
  `bd close`/`bd update` call per Work reflecting current state -- the
  same "direct CLI invocation, subprocess-per-operation" model, applied to
  the primitives that actually support this adapter's id/label discipline.
  See the mapping doc's "`--graph` was evaluated and rejected" section.
- `bd close --reason accepted` mirrors the kernel's own `DEC-ACCEPT`/
  `FACT-WORK-COMPLETED` -- a write-only echo, never a trigger. Block state
  is projected via `bd`'s own builtin `blocked` status (an exact-name
  match, confirmed by `bd statuses`) plus `--set-metadata blocked_reason=
  ...` -- also write-only.
- Never reaches past the `bd` CLI into Dolt (`bd`'s underlying storage).
- Workspace guard (`_workspace_owns_database`): `bd -C <dir>` WALKS UP to
  the nearest ancestor `.beads` database when `<dir>` has none of its own
  (confirmed empirically) -- `project_run` therefore refuses to spawn any
  `bd` subprocess at all unless `<workspace>/.beads` exists, degrading
  the whole projection instead (never a walk-up write into a database
  the operator did not configure). See the mapping doc's "Workspace
  guard" section.
- Mirror failures never raise: `project_run` always returns a
  `MirrorReport` whose `degraded` flag/`.errors` record which `bd`
  invocations failed. The caller (`orc_werk.cli.main.cmd_dispatch`)
  decides how to surface a degraded mirror (a stderr note, never a
  non-zero exit or a blocked dispatch) -- mirror failures MUST NEVER break
  the delivery loop.
"""

from __future__ import annotations

import shutil
import os.path
import subprocess
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

from orc_werk.core.effects import FX_CREATE_WORK
from orc_werk.core.serialization import KIND_EFFECT
from orc_werk.core.state import (
    STATE_ACCEPTED,
    STATE_ASSURING,
    STATE_BLOCKED,
    STATE_EXECUTING,
    STATE_READY,
    DeliveryProjection,
)
from orc_werk.ports.work_graph import validate_plan

# Recon pin (this task, `docs/adapters/beads/mapping.md`): `bd version` ==
# 1.2.2 (Homebrew) at implementation time. Informative only, matching the
# acp adapter's `ACPX_VERSION_PIN` precedent -- this adapter shells out to
# whatever `bd` is actually on `PATH`/configured, never version-gates at
# runtime.
BD_VERSION_PIN = "1.2.2"

_RUN_LABEL_PREFIX = "run:"
_PROJECT_LABEL_PREFIX = "project:"

# bd's own builtin status vocabulary (`bd statuses`) this adapter maps
# canonical Work states onto. STATE_ACCEPTED is deliberately absent here --
# it is projected via `bd close --reason accepted`, not `--status`.
_STATUS_BY_STATE: Mapping[str, str] = {
    STATE_READY: "open",
    STATE_EXECUTING: "in_progress",
    STATE_ASSURING: "in_progress",
    STATE_BLOCKED: "blocked",
}

_DEFAULT_TIMEOUT_S = 20.0


@dataclass(frozen=True)
class MirrorCallResult:
    """One `bd` subprocess invocation's outcome. `argv` never includes the
    `bd` binary's own resolved absolute path beyond what was configured --
    recorded verbatim for degraded-mirror diagnostics."""

    argv: tuple[str, ...]
    ok: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class MirrorReport:
    """Write-only outcome of one `BeadsMirror.project_run` call. Never
    raised as an exception by `project_run` itself -- always returned, so a
    degraded mirror can never break the delivery loop."""

    delivery_run_id: str
    calls: tuple[MirrorCallResult, ...] = field(default_factory=tuple)

    @property
    def degraded(self) -> bool:
        return any(not call.ok for call in self.calls)

    @property
    def errors(self) -> tuple[MirrorCallResult, ...]:
        return tuple(call for call in self.calls if not call.ok)


def _bd_id(delivery_run_id: str, work_id: str) -> str:
    return f"{delivery_run_id}--{work_id}"


def _extract_plan(history: Iterable[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """The run's `PORT-WORK-001` plan, read from the durable `FX-CREATE-
    WORK` effect record (`data.plan`) -- never from a caller-supplied plan
    variable, so this stays a pure projection of journal-derived state
    (module docstring) regardless of whether this is a first dispatch or a
    later re-dispatch/resume. `None` when no such record exists yet (the
    run has not bootstrapped) -- an honest "nothing durable to project
    yet", not an error."""
    for record in history:
        if record.get("kind") == KIND_EFFECT and record.get("id") == FX_CREATE_WORK:
            return record.get("data", {}).get("plan")
    return None


def _topological_order(plan: Mapping[str, Any]) -> list[str]:
    """Dependency-first ordering of `plan["works"]` (deps before
    dependents) so every `bd create --deps ...` call names an
    already-created `bd` id. Safe to call only after `validate_plan` has
    already proven the plan acyclic -- no cycle guard here beyond the
    cheap `visiting` marker, which exists as defense-in-depth, not as this
    function's own validation duty."""
    works = plan["works"]
    deps_by_id = {entry["work_id"]: [d["work_id"] for d in entry.get("deps", [])] for entry in works}
    order: list[str] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(work_id: str) -> None:
        if work_id in visited or work_id in visiting:
            return
        visiting.add(work_id)
        for dep_id in deps_by_id.get(work_id, []):
            visit(dep_id)
        visiting.discard(work_id)
        visited.add(work_id)
        order.append(work_id)

    for entry in works:
        visit(entry["work_id"])
    return order


class BeadsMirror:
    """Write-only Beads mirror for one shared, `bd`-initialized workspace.

    `workspace` is the directory `bd init` was already run in (this
    adapter never runs `bd init` itself -- provisioning the shared
    database is an operator/deployment concern, matching the same
    "adapter never `no-mistakes init`s a repo" precedent the now-removed
    `no-mistakes` adapter established (`ADR-0005`)).
    Every invocation passes `-C <workspace>` so `bd` resolves the intended
    database regardless of this process's own cwd -- but `-C` alone is NOT
    containment (`bd` walks up to an ancestor `.beads` when `workspace`
    has none), so `project_run` additionally guards that
    `<workspace>/.beads` actually exists before spawning anything (see
    `_workspace_owns_database`).
    """

    BD_VERSION_PIN = BD_VERSION_PIN

    def __init__(
        self,
        *,
        workspace: str,
        bd_bin: str = "bd",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        project: Optional[str] = None,
    ) -> None:
        self._workspace = workspace
        self._bd_bin = bd_bin
        self._timeout_s = timeout_s
        self._project = project

    # -- public API ---------------------------------------------------------

    def project_run(
        self,
        *,
        delivery_run_id: str,
        history: Sequence[Mapping[str, Any]],
        projection: DeliveryProjection,
        briefs: Optional[Mapping[str, str]] = None,
        intent_text: Optional[str] = None,
    ) -> MirrorReport:
        """Project one run's current topology, briefs, and per-Work state
        into `bd`. Idempotent and safe to call on every dispatch (including
        every re-dispatch/poll of an already-fully-mirrored run): `bd
        create --id <existing>` is itself an upsert (confirmed empirically
        -- re-creating an existing id updates title/description/labels in
        place rather than erroring or duplicating), and `bd update`/`bd
        close` are unconditionally safe to re-issue against an issue
        already in the target state (also confirmed empirically -- closing
        an already-closed issue, or updating an already-closed issue's
        metadata, both succeed with exit 0). This adapter therefore always
        re-syncs full current state rather than diffing against
        previously-observed state -- the same "always re-derive, never
        trust in-process memory as the correctness path" discipline the
        now-removed acp/no-mistakes adapters established for their own
        settled observations (`ADR-0005`).

        Never raises on a `bd` invocation failure -- every failure is
        recorded in the returned `MirrorReport` instead (module
        docstring's non-fatal guarantee). DOES let a plan-validation
        failure raise (`validate_plan`'s `CoreError`): a plan that reaches
        this point already malformed is a real upstream bug (the
        orchestrator validates the identical plan before this is ever
        called), not a `bd`-side degradation, and is not something a
        write-only mirror should silently swallow.
        """
        plan = _extract_plan(history)
        if plan is None:
            # Nothing durable to project yet (bootstrap has not run) --
            # honest no-op, not a degraded call.
            return MirrorReport(delivery_run_id=delivery_run_id, calls=())

        # Plan-validation pre-flight (mirrors PORT-WORK-001's validate_plan
        # discipline before any external write, per the task card) --
        # deliberately NOT wrapped in the non-fatal bd-call handling above.
        validate_plan(plan)

        # Workspace guard (PR #81 fix round, mapping doc "Workspace guard"):
        # `bd -C <dir>` WALKS UP the directory tree when `<dir>` has no
        # `.beads` of its own and silently operates on the nearest
        # ancestor's database (confirmed empirically against real bd
        # 1.2.2) -- a misconfigured/uninitialized `workspace` could
        # therefore write into a database the operator never configured
        # (e.g. a repo checkout's own real one). Fail closed BEFORE any
        # subprocess is spawned: the whole projection degrades to a no-op
        # with one synthesized failed call explaining why -- same
        # non-fatal surfacing as any other degraded mirror, never a
        # walk-up write.
        if not self._workspace_owns_database():
            return MirrorReport(
                delivery_run_id=delivery_run_id,
                calls=(
                    MirrorCallResult(
                        argv=(self._bd_bin, "--json", "-C", self._workspace),
                        ok=False,
                        returncode=-1,
                        stderr=(
                            f"workspace guard: {self._workspace!r} has no .beads directory "
                            "(bd -C would walk UP to an ancestor database -- refusing to "
                            "write outside the configured workspace; run 'bd init' there first)"
                        ),
                    ),
                ),
            )

        label = f"{_RUN_LABEL_PREFIX}{delivery_run_id}"
        briefs = briefs or {}
        deps_by_work = {
            entry["work_id"]: [dep["work_id"] for dep in entry.get("deps", [])] for entry in plan["works"]
        }

        calls: list[MirrorCallResult] = []
        for work_id in _topological_order(plan):
            calls.append(
                self._create_work(
                    delivery_run_id=delivery_run_id,
                    work_id=work_id,
                    dep_work_ids=deps_by_work.get(work_id, []),
                    label=label,
                    brief=briefs.get(work_id) or intent_text or "",
                )
            )

        for work_id, work_projection in projection.works.items():
            calls.extend(
                self._project_state(
                    delivery_run_id=delivery_run_id,
                    work_id=work_id,
                    state=work_projection.state,
                    attempt_number=work_projection.attempt_number,
                    claim_ref=work_projection.claim_ref,
                    blocked_reason=work_projection.blocked_reason,
                )
            )

        return MirrorReport(delivery_run_id=delivery_run_id, calls=tuple(calls))

    # -- per-operation helpers ------------------------------------------------

    def _workspace_owns_database(self) -> bool:
        """`<workspace>/.beads` exists as a directory -- the containment
        guard against `bd -C`'s ancestor walk-up (see `project_run`'s
        guard comment and the mapping doc's "Workspace guard" section). A
        plain existence check is deliberately sufficient: this adapter's
        contract is "the operator already ran `bd init` in `workspace`"
        (class docstring), and `bd init` always creates `.beads` there;
        anything else fails closed rather than reproducing `bd`'s own
        discovery logic here."""
        return os.path.isdir(os.path.join(self._workspace, ".beads"))

    def _create_work(
        self,
        *,
        delivery_run_id: str,
        work_id: str,
        dep_work_ids: Sequence[str],
        label: str,
        brief: str,
    ) -> MirrorCallResult:
        argv = [
            "create",
            "--id",
            _bd_id(delivery_run_id, work_id),
            "--force",
            "--label",
            label,
        ]
        if self._project is not None:
            argv += ["--label", f"{_PROJECT_LABEL_PREFIX}{self._project}"]
        argv += [
            "--title",
            work_id,
            "--description",
            brief,
        ]
        if dep_work_ids:
            argv += ["--deps", ",".join(_bd_id(delivery_run_id, dep) for dep in dep_work_ids)]
        return self._invoke(argv)

    def _project_state(
        self,
        *,
        delivery_run_id: str,
        work_id: str,
        state: str,
        attempt_number: int,
        claim_ref: Optional[str],
        blocked_reason: Optional[str],
    ) -> list[MirrorCallResult]:
        bd_id = _bd_id(delivery_run_id, work_id)
        metadata = [f"state={state.lower()}", f"attempt_number={attempt_number}"]
        if claim_ref:
            metadata.append(f"claim_ref={claim_ref}")

        if state == STATE_ACCEPTED:
            update_argv = ["update", bd_id]
            for kv in metadata:
                update_argv += ["--set-metadata", kv]
            calls = [self._invoke(update_argv)]
            calls.append(self._invoke(["close", bd_id, "--reason", "accepted"]))
            return calls

        if state == STATE_BLOCKED and blocked_reason:
            metadata.append(f"blocked_reason={blocked_reason}")

        argv = ["update", bd_id]
        status = _STATUS_BY_STATE.get(state)
        if status is not None:
            argv += ["--status", status]
        for kv in metadata:
            argv += ["--set-metadata", kv]
        return [self._invoke(argv)]

    # -- subprocess plumbing --------------------------------------------------

    def _invoke(self, argv: Sequence[str]) -> MirrorCallResult:
        full_argv = [self._bd_bin, "--json", "-C", self._workspace, *argv]
        if shutil.which(self._bd_bin) is None and "/" not in self._bd_bin:
            return MirrorCallResult(
                argv=tuple(full_argv),
                ok=False,
                returncode=-1,
                stderr=f"bd binary not found on PATH: {self._bd_bin!r}",
            )
        try:
            proc = subprocess.run(
                full_argv, capture_output=True, text=True, timeout=self._timeout_s
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return MirrorCallResult(argv=tuple(full_argv), ok=False, returncode=-1, stderr=str(exc))
        return MirrorCallResult(
            argv=tuple(full_argv),
            ok=proc.returncode == 0,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )


__all__ = ["BD_VERSION_PIN", "BeadsMirror", "MirrorCallResult", "MirrorReport"]
