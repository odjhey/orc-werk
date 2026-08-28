---
id: DOGFOOD-CORPUS
type: playbook
status: current
authority: informative
description: Growing corpus of user-level CLI dogfood scenarios, re-run after every major change by a dogfood checker agent.
---

# Dogfood scenario corpus

This is a living library of user-level CLI flows and judgment checks run
against the real `orc` CLI. It is process documentation (informative,
`PLAYBOOK-WATCHTOWER`-family): it constrains how dogfooding is done, never
what the product means — contracts under `docs/` own that.

## Purpose

`tests/scenarios` (the golden scenarios indexed at `docs/scenarios/README.md`,
`SCENARIOS-INDEX`) are executable contract specifications: they run under CI,
assert exact facts/decisions/effects, and exist to make a contract violation
turn the suite red. This corpus complements them and never duplicates their
role.

The distinction that matters:

- **`tests/scenarios`** answer "does the system conform to the contract?" —
  run by CI, judged by assertions, owned by the golden-scenario/conformance
  authority chain.
- **`dogfood/`** answers "how does this feel and behave to a human operator
  actually using the CLI?" — run by an agent that can read `status`/`history`
  output and judge whether it is legible, whether the real cause of a block
  is discoverable, whether a config mistake fails loud or silent. A dogfood
  scenario can pass its exit code and still be a FRICTION finding because the
  output was confusing or the root cause was buried.

A dogfood finding that turns out to be deterministic and contract-relevant
(a specific input reliably produces a specific wrong canonical outcome)
should graduate into a real conformance/scenario test — that is where it
gets permanent, CI-enforced protection. The corpus entry for it stays too,
kept for the user-level framing (the command a human actually typed, the
judgment call about legibility) that a contract-assertion test does not
capture.

## Scenario format

Each scenario lives at `dogfood/scenarios/DFS-0NN-<slug>/` and contains:

- `scenario.md` — frontmatter (`id: DFS-0NN`, `type: scenario`,
  `status: current`, `authority: informative`, one-line `description`) plus
  a body with:
  - **concern tags** (see vocabulary below);
  - **intent** — what real-world friction or behavior this scenario exists
    to catch;
  - **setup** — any preconditions (e.g. a pre-built journal fixture to copy
    into place before running commands);
  - **exact commands** — copy-pasteable, referencing this directory's
    `config.json`/fixtures by relative path;
  - **expected observable outcomes** — exit codes, `status`/`history`
    output, and specifically which journal records or fields are evidence
    (e.g. "`FACT-WORK-BLOCKED.reason` is `retry-budget-exhausted`" or
    "history seq count is unchanged after re-dispatch");
  - **judgment notes** — for the checker, where output *quality* matters
    and there is no single mechanical assertion (legibility, root-cause
    discoverability, whether a human could reconstruct what happened).
- `config.json` (and any auxiliary fixture files: alternate configs,
  pre-corrupted journal fixtures, etc.) — the CLI dispatch config(s) or
  journal fixtures the scenario's commands reference.

### Journal directory convention

Scenario commands read their config/fixtures from this repo
(`dogfood/scenarios/DFS-0NN-<slug>/...`, relative paths, read-only) but
**never write journals into the repo**. Every scenario's commands write to
a scratch journal directory outside the working tree, conventionally
`$DOGFOOD_SCRATCH/DFS-0NN` where `$DOGFOOD_SCRATCH` is a fresh directory
the checker creates per run (e.g. `mktemp -d`) and discards afterward. No
scenario uses the repo-relative default `.orc`, and no scenario commits a
journal fixture that was produced by a live run without hand-checking it
first (`dogfood/scenarios/DFS-009-journal-recovery/` is the one directory
that intentionally ships pre-built journal *fixtures*, not journals a
checker run produced).

## Concern tags

A small controlled vocabulary, used for selective runs. Each scenario
declares the tags it exercises; a change declares the concerns it touches;
the checker runs the union.

| Tag | Covers |
|---|---|
| `happy-path` | Nothing goes wrong; the straight-line flow. |
| `retry` | Rejection/failure followed by a further attempt. |
| `dag` | Multi-work plans, dependency edges, fan-in/fan-out. |
| `budget` | Retry-budget accounting and exhaustion. |
| `capability` | Capability advertisement/mismatch between policy and provider. |
| `idempotency` | Re-running an effect/dispatch must not duplicate it. |
| `journal-recovery` | Torn tails, corruption, missing/garbage journal targets. |
| `config-validation` | CLI dispatch-config load-time correctness. |
| `cli-errors` | Canonical error surfacing at the CLI boundary. |
| `cli-output` | Legibility/completeness of `status`/`history` output. |
| `adversarial` | Hostile or degenerate payloads (NaN, huge/unicode input, deep nesting). |
| `real-work` | A realistic end-to-end task, not a synthetic minimal example. |

## Process

1. **The corpus grows over time.** Every dogfooding session, every bug found
   by real usage, every user report may add a scenario. New scenarios are
   renumbered `DFS-0NN` sequentially; existing numbers are never reused or
   renumbered away once shipped.
2. **After every major merge, the watchtower dispatches a dogfood checker
   agent.** It pulls latest `master`, selects scenarios whose concern tags
   intersect the change's declared concerns (or all scenarios, for milestone
   closes), executes them against the real CLI, and reports one of PASS /
   BUG / FRICTION per scenario, with evidence (commands run, exit codes,
   relevant `status`/`history` excerpts).
3. **The checker only checks.** It is read-only and user-perspective: it
   never patches code, never amends docs, never opens a fix PR itself.
   Routing the healing — filing an issue, dispatching a fix PR, proposing a
   docs amendment — is the watchtower's job, per `PLAYBOOK-WATCHTOWER` and
   `DELIVERY-STANCE`.
4. **Expectations encode CORRECT behavior per current contracts**, not
   whatever `master` currently does. When a scenario's expected outcome and
   `master`'s actual behavior diverge because of a known bug, the scenario
   stays in the corpus as a known-failing entry that references its
   tracking issue (see DFS-007, DFS-009, DFS-010 below) rather than being
   softened to match the bug or deleted. A scenario failing against `master`
   for a referenced, already-filed reason is an expected BUG report, not
   corpus rot.

## Seeded scenarios (round 1)

Seeded from the round-1 dogfooding session (10 invented scenarios, 2 bugs
found, issues filed as #16-18). Round 1's confirmed bugs (NaN traceback,
`max_attempts: 0` falsy-drop, missing-path fallthrough, invisible history
extensions) were fixed by the round-1 fix PR, now merged and guarded by
`tests/scenarios/test_cli_dogfood_fixes.py`; the corresponding scenarios
(DFS-006, DFS-009 case 4a, DFS-011, DFS-012) encode that fixed behavior
as confirmed-correct. Where `master` still diverges from correct behavior
for a filed reason (#16-18), the scenario says so explicitly.

| ID | Scenario | Tags |
|---|---|---|
| [`DFS-001`](scenarios/DFS-001-happy-path-single-work/scenario.md) | Happy path, single work | `happy-path`, `cli-output` |
| [`DFS-002`](scenarios/DFS-002-reject-retry-accept/scenario.md) | Reject → retry → accept | `retry`, `cli-output` |
| [`DFS-003`](scenarios/DFS-003-diamond-dag-fanin/scenario.md) | Diamond DAG `a → b,c → d` | `dag` |
| [`DFS-004`](scenarios/DFS-004-budget-exhaustion-failures/scenario.md) | Budget exhaustion via execution failures | `budget` |
| [`DFS-005`](scenarios/DFS-005-budget-exhaustion-rejections-inconclusive/scenario.md) | Budget exhaustion via rejections, plus inconclusive | `budget` |
| [`DFS-006`](scenarios/DFS-006-max-attempts-extremes/scenario.md) | `--max-attempts`/config extremes: 1, very large, 0 | `budget`, `config-validation`, `cli-errors` |
| [`DFS-007`](scenarios/DFS-007-capability-mismatch/scenario.md) | Capability mismatch: resume-exact vs. best-effort | `capability`, `cli-errors` |
| [`DFS-008`](scenarios/DFS-008-idempotent-redispatch/scenario.md) | Idempotent re-dispatch over a completed journal | `idempotency` |
| [`DFS-009`](scenarios/DFS-009-journal-recovery/scenario.md) | Journal recovery: torn tail, corrupt middle, missing/garbage paths | `journal-recovery`, `cli-errors` |
| [`DFS-010`](scenarios/DFS-010-config-abuse/scenario.md) | Config abuse: invalid JSON, cycle, dup id, unknown dep, unknown key, missing attempts | `config-validation`, `cli-errors` |
| [`DFS-011`](scenarios/DFS-011-adversarial-payloads/scenario.md) | Adversarial payloads: NaN, unicode/emoji + 100k intent, deep nesting | `adversarial` |
| [`DFS-012`](scenarios/DFS-012-real-work-docs-page/scenario.md) | Real-work simulation: "write docs page" with structured candidate + assurance findings | `real-work`, `cli-output` |

Known open issues referenced by scenarios above: #16 (root cause masked as
budget exhaustion — DFS-007), #17 (config loader is fail-open where the
system is fail-closed — DFS-006, DFS-010), #18 (torn-tail healing is
content-blind — DFS-009).
