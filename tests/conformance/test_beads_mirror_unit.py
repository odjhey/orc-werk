"""Stub-`bd` unit/scenario tests for `BeadsMirror` (`TASK-M2-006`).

`BeadsMirror` is not a `PORT-WORK-GRAPH` implementation (module docstring,
`orc_werk.adapters.beads.mirror`), so it does not mix in
`WorkGraphConformanceMixin` (`tests/conformance/test_work_graph_conformance.
py`) -- that mixin drives `WorkGraphPort.create`/`ready`/`claim`/
`complete`/`block` directly, an interface this write-only observer does not
implement. Instead, this module drives the SAME topologies `CONF-WORK-001`
through `CONF-WORK-004` exercise (`_fanin_plan`/`_chain_plan`, imported
from that module so the fixtures never drift) through a real
`orc_werk.app.Orchestrator` + `MemoryWorkGraph` run (`tests.scenarios.
support.build_run`), with a stub-`bd` fake standing in for the real CLI,
and asserts the mirror's write-only projection stays faithful at each of
those tests' analogous transition points -- never predicting state ahead
of the kernel, never fabricating readiness/acceptance the kernel has not
itself committed.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from orc_werk.adapters.beads.mirror import BD_VERSION_PIN, BeadsMirror
from orc_werk.adapters.memory.journal import MemoryJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph
from orc_werk.adapters.scripted.assurance import ScriptedAssurance
from orc_werk.adapters.scripted.candidate import ScriptedCandidate
from orc_werk.adapters.scripted.execution import ScriptedExecution
from orc_werk.app.orchestrator import Orchestrator, RunConfig
from orc_werk.core.state import STATE_ACCEPTED, STATE_BLOCKED, STATE_EXECUTING, STATE_READY
from tests.conformance.support_beads_stub import install_stub, read_calls, verbs
from tests.conformance.test_work_graph_conformance import _chain_plan, _fanin_plan
from tests.scenarios.support import build_run, predicted_execution_id


class _StubBeadsCase(unittest.TestCase):
    """Base case: installs a fresh stub-`bd` binary + log file per test,
    wires a `BeadsMirror` at a throwaway workspace path (never touched --
    the stub never actually reads `-C`'s target), and cleans up the
    `ORC_BEADS_STUB_*` environment afterwards."""

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self._stub_bin = install_stub(self._tmp)
        self._log = self._tmp / "calls.jsonl"
        self._prior_env = dict(os.environ)
        os.environ["ORC_BEADS_STUB_LOG"] = str(self._log)
        os.environ.pop("ORC_BEADS_STUB_FAIL_VERBS", None)
        self.mirror = BeadsMirror(workspace=str(self._tmp / "workspace"), bd_bin=str(self._stub_bin))

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._prior_env)

    def calls(self) -> list[list[str]]:
        return read_calls(self._log)

    def verbs(self) -> list[str]:
        return verbs(self.calls())


class VersionPinTest(unittest.TestCase):
    def test_version_pin_recorded(self) -> None:
        self.assertEqual(BD_VERSION_PIN, "1.2.2")


class IdLabelConstructionTest(_StubBeadsCase):
    """Deterministic `--id <run_id>--<work_id>` + `--label run:<run_id>` +
    `--force` on every `create` (`INV-020`, the shared-DB label discipline
    the ratified mirror-mode posture depends on)."""

    def test_create_ids_labels_and_force(self) -> None:
        orch, journal, _wg = build_run(delivery_run_id="dr-idlabel", attempts_by_work={"w": []})
        orch.bootstrap(intent_id="dr-idlabel", text="intent text", plan={"works": [{"work_id": "w", "deps": []}]})
        projection = orch.projection()
        history = journal.history(delivery_run_id="dr-idlabel")

        report = self.mirror.project_run(
            delivery_run_id="dr-idlabel", history=history, projection=projection, intent_text="intent text"
        )
        self.assertFalse(report.degraded)

        create_calls = [c for c in self.calls() if c[3] == "create"]
        self.assertEqual(len(create_calls), 1)
        argv = create_calls[0]
        self.assertIn("--id", argv)
        self.assertEqual(argv[argv.index("--id") + 1], "dr-idlabel--w")
        self.assertIn("--force", argv)
        self.assertIn("--label", argv)
        self.assertEqual(argv[argv.index("--label") + 1], "run:dr-idlabel")
        self.assertIn("--description", argv)
        self.assertEqual(argv[argv.index("--description") + 1], "intent text")

    def test_dependency_first_creation_order_and_deps_flag(self) -> None:
        """`c` depends on `a`/`b` (`_fanin_plan`): `create` calls for `a`
        and `b` MUST precede `c`'s, and `c`'s call MUST carry `--deps`
        naming both upstream `bd` ids -- otherwise a real `bd create --deps
        <not-yet-created-id>` would fail (empirically confirmed, this
        task's recon)."""
        plan = _fanin_plan()
        orch, journal, _wg = build_run(delivery_run_id="dr-fanin", attempts_by_work={}, plan=plan)
        projection = orch.projection()
        history = journal.history(delivery_run_id="dr-fanin")

        report = self.mirror.project_run(
            delivery_run_id="dr-fanin", history=history, projection=projection, intent_text="fanin"
        )
        self.assertFalse(report.degraded)

        create_calls = [c for c in self.calls() if c[3] == "create"]
        created_ids = [c[c.index("--id") + 1] for c in create_calls]
        self.assertLess(created_ids.index("dr-fanin--a"), created_ids.index("dr-fanin--c"))
        self.assertLess(created_ids.index("dr-fanin--b"), created_ids.index("dr-fanin--c"))

        c_argv = next(c for c in create_calls if c[c.index("--id") + 1] == "dr-fanin--c")
        self.assertIn("--deps", c_argv)
        deps_value = c_argv[c_argv.index("--deps") + 1]
        self.assertEqual(set(deps_value.split(",")), {"dr-fanin--a", "dr-fanin--b"})


class BriefsProjectionTest(_StubBeadsCase):
    """Briefs -> `bd` issue descriptions at create (PR #49 adapter-owned-
    briefs ruling) -- a per-work brief, when supplied, wins over the
    run-level intent-text fallback."""

    def test_per_work_brief_wins_over_intent_fallback(self) -> None:
        plan = {"works": [{"work_id": "x", "deps": []}, {"work_id": "y", "deps": []}]}
        orch, journal, _wg = build_run(delivery_run_id="dr-briefs", attempts_by_work={}, plan=plan)
        projection = orch.projection()
        history = journal.history(delivery_run_id="dr-briefs")

        report = self.mirror.project_run(
            delivery_run_id="dr-briefs",
            history=history,
            projection=projection,
            briefs={"x": "specific brief for x"},
            intent_text="run-level intent",
        )
        self.assertFalse(report.degraded)

        create_calls = {c[c.index("--id") + 1]: c for c in self.calls() if c[3] == "create"}
        x_argv = create_calls["dr-briefs--x"]
        y_argv = create_calls["dr-briefs--y"]
        self.assertEqual(x_argv[x_argv.index("--description") + 1], "specific brief for x")
        self.assertEqual(y_argv[y_argv.index("--description") + 1], "run-level intent")


class StatusVocabularyTest(_StubBeadsCase):
    """Kernel state -> `bd` status/metadata mapping table (mapping doc)."""

    def _project(self, delivery_run_id: str, *, attempts_by_work: Mapping[str, Any]) -> tuple[Any, Any]:
        orch, journal, _wg = build_run(delivery_run_id=delivery_run_id, attempts_by_work=attempts_by_work)
        orch.bootstrap(intent_id=delivery_run_id, text="t")
        projection = orch.run()
        history = journal.history(delivery_run_id=delivery_run_id)
        report = self.mirror.project_run(
            delivery_run_id=delivery_run_id, history=history, projection=projection, intent_text="t"
        )
        return projection, report

    def test_ready_maps_to_open(self) -> None:
        # READY (undispatched) is only observable BEFORE `orch.run()`/
        # `.step()` ever advances the Work -- `run()` dispatches
        # immediately once nothing blocks it, so this reads the projection
        # right after `bootstrap()` instead of driving the loop at all.
        orch, journal, _wg = build_run(delivery_run_id="dr-ready", attempts_by_work={"work-1": []})
        projection = orch.projection()
        history = journal.history(delivery_run_id="dr-ready")
        self.assertEqual(projection.works["work-1"].state, STATE_READY)

        report = self.mirror.project_run(
            delivery_run_id="dr-ready", history=history, projection=projection, intent_text="t"
        )
        self.assertFalse(report.degraded)
        update_argv = next(c for c in self.calls() if c[3] == "update")
        self.assertIn("--status", update_argv)
        self.assertEqual(update_argv[update_argv.index("--status") + 1], "open")
        self.assertIn("--set-metadata", update_argv)
        self.assertIn("state=ready", update_argv)

    def test_executing_maps_to_in_progress(self) -> None:
        projection, report = self._project(
            "dr-executing", attempts_by_work={"work-1": [{"outcome": "completed"}]}
        )
        self.assertEqual(projection.works["work-1"].state, STATE_EXECUTING)
        self.assertFalse(report.degraded)
        update_argv = next(c for c in self.calls() if c[3] == "update")
        self.assertEqual(update_argv[update_argv.index("--status") + 1], "in_progress")
        self.assertIn("state=executing", update_argv)

    def test_accepted_updates_metadata_then_closes_with_reason(self) -> None:
        projection, report = self._project(
            "dr-accepted",
            attempts_by_work={"work-1": [{"outcome": "completed", "candidate": {"label": "A"}, "verdict": "accepted"}]},
        )
        self.assertEqual(projection.works["work-1"].state, STATE_ACCEPTED)
        self.assertFalse(report.degraded)
        self.assertIn("update", self.verbs())
        self.assertIn("close", self.verbs())
        close_argv = next(c for c in self.calls() if c[3] == "close")
        self.assertIn("--reason", close_argv)
        self.assertEqual(close_argv[close_argv.index("--reason") + 1], "accepted")
        self.assertEqual(close_argv[4], "dr-accepted--work-1")
        update_argv = next(c for c in self.calls() if c[3] == "update")
        self.assertIn("state=accepted", update_argv)

    def test_blocked_maps_to_blocked_status_with_reason_metadata(self) -> None:
        projection, report = self._project(
            "dr-blocked",
            attempts_by_work={
                "work-1": [
                    {"outcome": "completed", "candidate": {"label": "A"}, "verdict": "rejected"},
                    {"outcome": "completed", "candidate": {"label": "B"}, "verdict": "rejected"},
                    {"outcome": "completed", "candidate": {"label": "C"}, "verdict": "rejected"},
                ]
            },
        )
        self.assertEqual(projection.works["work-1"].state, STATE_BLOCKED)
        self.assertFalse(report.degraded)
        update_argv = next(c for c in self.calls() if c[3] == "update")
        self.assertEqual(update_argv[update_argv.index("--status") + 1], "blocked")
        self.assertIn("state=blocked", update_argv)
        self.assertIn("blocked_reason=retry-budget-exhausted", update_argv)
        # write-only echo, never a trigger: `close` is NEVER called for a
        # blocked Work.
        self.assertNotIn("close", self.verbs())


class ConfWorkAnalogsTest(_StubBeadsCase):
    """`CONF-WORK-001` through `CONF-WORK-004`'s applicable cases, applied
    to a write-only observer rather than a `WorkGraphPort` implementation
    (module docstring)."""

    def test_conf_work_001_analog_blocked_dependency_never_advances_dependent(self) -> None:
        """Fan-in plan (`_fanin_plan`): `a` blocked (retry-budget exhausted)
        MUST project as `bd` status `blocked`; `c` (depends on `a`, `b`)
        MUST NOT be projected as anything beyond its true, still-eligible-
        pending kernel state (`READY`, never `in_progress`/`accepted`) --
        the mirror never fabricates progress the kernel has not itself
        committed, exactly `CONF-WORK-001`'s "ready excludes blocked deps"
        applied to a projection instead of a readiness query."""
        plan = _fanin_plan()
        attempts_by_work = {
            "a": [
                {"outcome": "completed", "candidate": {"label": "A1"}, "verdict": "rejected"},
                {"outcome": "completed", "candidate": {"label": "A2"}, "verdict": "rejected"},
                {"outcome": "completed", "candidate": {"label": "A3"}, "verdict": "rejected"},
            ],
            "b": [{"outcome": "completed", "candidate": {"label": "B1"}, "verdict": "accepted"}],
        }
        orch, journal, _wg = build_run(delivery_run_id="dr-conf1", attempts_by_work=attempts_by_work, plan=plan)
        orch.bootstrap(intent_id="dr-conf1", text="t", plan=plan)
        projection = orch.run()
        history = journal.history(delivery_run_id="dr-conf1")

        self.assertEqual(projection.works["a"].state, STATE_BLOCKED)
        self.assertEqual(projection.works["c"].state, STATE_READY)

        report = self.mirror.project_run(
            delivery_run_id="dr-conf1", history=history, projection=projection, intent_text="t"
        )
        self.assertFalse(report.degraded)

        update_by_id = {c[4]: c for c in self.calls() if c[3] == "update"}
        a_argv = update_by_id["dr-conf1--a"]
        self.assertEqual(a_argv[a_argv.index("--status") + 1], "blocked")
        c_argv = update_by_id["dr-conf1--c"]
        self.assertEqual(c_argv[c_argv.index("--status") + 1], "open")
        self.assertIn("state=ready", c_argv)

    def test_conf_work_002_analog_dependent_advances_only_after_committed_completion(self) -> None:
        """Chain plan (`_chain_plan`, `w` -> `x`): mirror `w` while still
        `ASSURING` (not yet accepted) -- `x` must still project as `READY`/
        `open`. Only after `w` actually commits to `ACCEPTED` does a second
        `project_run` call ever show `x` advanced to `EXECUTING`/
        `in_progress` -- the mirror is never ahead of the kernel."""
        # Built directly (not `tests.scenarios.support.build_run`, which
        # hardcodes `ScriptedAssurance(pending=False)`, the M0 strict
        # default): this case needs `w` to rest, unsettled, at `ASSURING`
        # (no scripted verdict at all) rather than erroring -- the same
        # `pending=True` M1a-default posture `orc_werk.cli.config.
        # build_scripted_adapters` uses for real CLI dispatch.
        plan = _chain_plan()
        journal = MemoryJournal()
        work_graph = MemoryWorkGraph()
        execution = ScriptedExecution(
            script={"w": [{"outcome": "completed"}]}, capabilities=frozenset(), pending=True
        )
        candidate = ScriptedCandidate(
            subjects={
                predicted_execution_id(delivery_run_id="dr-conf2", work_id="w", attempt_number=1): {
                    "work_id": "w",
                    "subject_identity": {"label": "W"},
                }
            },
            current_by_work={},
        )
        assurance = ScriptedAssurance(script={}, pending=True)
        orch = Orchestrator(
            delivery_run_id="dr-conf2",
            journal=journal,
            work_graph=work_graph,
            execution=execution,
            candidate=candidate,
            assurance=assurance,
            config=RunConfig(),
        )
        orch.bootstrap(intent_id="dr-conf2", text="t", plan=plan)
        projection = orch.run()
        history = journal.history(delivery_run_id="dr-conf2")
        self.assertEqual(projection.works["w"].state, "ASSURING")
        self.assertEqual(projection.works["x"].state, STATE_READY)

        report = self.mirror.project_run(
            delivery_run_id="dr-conf2", history=history, projection=projection, intent_text="t"
        )
        self.assertFalse(report.degraded)
        update_by_id = {c[4]: c for c in self.calls() if c[3] == "update"}
        self.assertEqual(update_by_id["dr-conf2--x"][update_by_id["dr-conf2--x"].index("--status") + 1], "open")

    def test_conf_work_003_analog_duplicate_completion_projection_is_idempotent(self) -> None:
        """Re-projecting an already-`ACCEPTED` Work a second time (a
        redundant `orc dispatch` re-poll of an already-terminal run) issues
        the SAME `update` + `close --reason accepted` calls again, without
        the stub (standing in for `bd`'s own confirmed-idempotent `close`/
        `update` behavior, this task's live recon) ever needing to reject
        it as a conflict."""
        orch, journal, _wg = build_run(
            delivery_run_id="dr-conf3",
            attempts_by_work={"work-1": [{"outcome": "completed", "candidate": {"label": "A"}, "verdict": "accepted"}]},
        )
        orch.bootstrap(intent_id="dr-conf3", text="t")
        projection = orch.run()
        history = journal.history(delivery_run_id="dr-conf3")

        report1 = self.mirror.project_run(
            delivery_run_id="dr-conf3", history=history, projection=projection, intent_text="t"
        )
        report2 = self.mirror.project_run(
            delivery_run_id="dr-conf3", history=history, projection=projection, intent_text="t"
        )
        self.assertFalse(report1.degraded)
        self.assertFalse(report2.degraded)
        self.assertEqual(self.verbs().count("close"), 2)

    def test_conf_work_004_analog_not_applicable_no_claim_capability(self) -> None:
        """`CONF-WORK-004` (atomic claim) applies only when
        `CAP-WORK-ATOMIC-CLAIM` is advertised by a `WorkGraphPort`
        implementation. `BeadsMirror` implements no `WorkGraphPort`
        interface and advertises no `CAP-WORK-*` capability at all (module
        docstring) -- it has no `claim`/`capabilities` method to exercise,
        so this case is structurally not applicable, recorded here (and in
        `docs/adapters/beads/conformance.md`) rather than silently
        omitted."""
        self.assertFalse(hasattr(self.mirror, "claim"))
        self.assertFalse(hasattr(self.mirror, "capabilities"))


class DegradedMirrorTest(_StubBeadsCase):
    """Mirror failures MUST NEVER break the delivery loop (task card):
    `project_run` always returns a `MirrorReport` instead of raising, and
    keeps issuing subsequent `bd` calls after an earlier one failed (a
    best-effort desired-state sync, not a transaction)."""

    def test_a_failed_bd_call_is_recorded_not_raised(self) -> None:
        os.environ["ORC_BEADS_STUB_FAIL_VERBS"] = "create"
        orch, journal, _wg = build_run(delivery_run_id="dr-degraded", attempts_by_work={"work-1": []})
        orch.bootstrap(intent_id="dr-degraded", text="t")
        projection = orch.run()
        history = journal.history(delivery_run_id="dr-degraded")

        report = self.mirror.project_run(
            delivery_run_id="dr-degraded", history=history, projection=projection, intent_text="t"
        )
        self.assertTrue(report.degraded)
        self.assertEqual(len(report.errors), 1)
        # `MirrorCallResult.argv` includes the resolved `bd_bin` at index 0
        # (unlike the stub's own recorded log, which only sees `sys.argv[1:]`).
        self.assertEqual(report.errors[0].argv[4], "create")
        self.assertFalse(report.errors[0].ok)
        self.assertEqual(report.errors[0].returncode, 1)
        # the failed `create` call did not stop the subsequent `update`
        # call for the same Work from still being issued:
        self.assertIn("update", self.verbs())

    def test_missing_bd_binary_is_non_fatal(self) -> None:
        mirror = BeadsMirror(workspace=str(self._tmp / "workspace"), bd_bin="bd-does-not-exist-orcw-xyz")
        orch, journal, _wg = build_run(delivery_run_id="dr-missing-bin", attempts_by_work={"work-1": []})
        orch.bootstrap(intent_id="dr-missing-bin", text="t")
        projection = orch.run()
        history = journal.history(delivery_run_id="dr-missing-bin")

        report = mirror.project_run(
            delivery_run_id="dr-missing-bin", history=history, projection=projection, intent_text="t"
        )
        self.assertTrue(report.degraded)
        for call in report.calls:
            self.assertFalse(call.ok)

    def test_no_bootstrap_yet_is_an_honest_no_op(self) -> None:
        """No `FX-CREATE-WORK` effect record observed yet (a run that has
        never dispatched) is an honest no-op -- zero `bd` calls, not a
        degraded report."""
        from orc_werk.core.state import DeliveryProjection

        report = self.mirror.project_run(
            delivery_run_id="dr-never-bootstrapped",
            history=(),
            projection=DeliveryProjection(delivery_run_id="dr-never-bootstrapped"),
            intent_text="t",
        )
        self.assertFalse(report.degraded)
        self.assertEqual(report.calls, ())
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
