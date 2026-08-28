---
id: ADAPTER-BEADS-CONFORMANCE
type: conformance-report
status: current
authority: informative
description: Beads mirror (BeadsMirror) conformance status -- CONF-WORK analogs, not the WorkGraphPort suite itself.
---

# Beads conformance

`BeadsMirror` (`TASK-M2-006`) does not implement `WorkGraphPort` and is
therefore not a subject of the `CONF-WORK-001` through `CONF-WORK-004`
suite as literally written (`tests/conformance/
test_work_graph_conformance.py`'s `WorkGraphConformanceMixin` drives
`create`/`ready`/`claim`/`complete`/`block` directly -- an interface this
write-only observer does not have). The applicable-cases requirement
(task card acceptance: "the stub-`bd` `PATH` fake driving the applicable
`CONF-WORK-001` through `CONF-WORK-004` suite's applicable cases") is
satisfied by driving the SAME fixture topologies
(`_fanin_plan`/`_chain_plan`, imported from that same test module) through
a real `Orchestrator` + `MemoryWorkGraph` run and asserting the mirror's
projection stays faithful at each transition -- see
`tests/conformance/test_beads_mirror_unit.py`'s `ConfWorkAnalogsTest`.

| Requirement | Status | Evidence |
|---|---|---|
| `CONF-WORK-001` (ready excludes blocked deps) -- analog | pass (applied to projection faithfulness, not a readiness query) | `test_conf_work_001_analog_blocked_dependency_never_advances_dependent` |
| `CONF-WORK-002` (dependents unlock only after committed completion) -- analog | pass (mirror never ahead of the kernel) | `test_conf_work_002_analog_dependent_advances_only_after_committed_completion` |
| `CONF-WORK-003` (duplicate completion is idempotent) -- analog | pass | `test_conf_work_003_analog_duplicate_completion_projection_is_idempotent` |
| `CONF-WORK-004` (atomic claim, only when `CAP-WORK-ATOMIC-CLAIM` is advertised) | not applicable | `test_conf_work_004_analog_not_applicable_no_claim_capability` -- `BeadsMirror` advertises no `CAP-WORK-*` capability (`docs/adapters/beads/capabilities.md`), so this requirement's own gating condition is never met. |

## Additional coverage (not `CONF-WORK-*`, task-card-specific)

| Area | Evidence |
|---|---|
| Deterministic `--id`/`--label` construction | `tests/conformance/test_beads_mirror_unit.py::IdLabelConstructionTest` |
| Dependency-first creation order + `--deps` | `IdLabelConstructionTest::test_dependency_first_creation_order_and_deps_flag` |
| Briefs -> `bd` descriptions (per-work override + intent-text fallback) | `BriefsProjectionTest` |
| Status/metadata vocabulary (`READY`/`EXECUTING`/`ASSURING`/`BLOCKED`/`ACCEPTED`) | `StatusVocabularyTest` |
| Degraded-mirror non-fatality (a failed `bd` call never raises, never stops subsequent calls) | `DegradedMirrorTest` |
| CLI wiring: absent `mirror` config is zero behavior change; a configured mirror never changes `orc dispatch`'s exit code or stdout even when degraded | `tests/scenarios/test_cli_beads_mirror_wiring.py::MirrorWiringSmokeTest` |
| One live sandbox smoke against real `bd` 1.2.2 (skipped when `bd` is absent, e.g. `ci-required`) | `tests/conformance/test_beads_mirror_live_smoke.py` |

Version pin: `bd` `1.2.2` (`docs/adapters/beads/mapping.md`).
