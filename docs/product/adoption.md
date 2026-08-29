---
id: PRODUCT-ADOPTION
type: guide
status: current
authority: informative
description: Operator-facing adoption guide — when to use Orc Werk, prerequisites, and how to tailor-fit it.
---

# Adoption guide

This guide answers three questions an operator asks before adopting Orc Werk: when to use it, what must be true before it can be used, and where it is meant to be shaped to fit a deployment. It complements `PRODUCT-THESIS`, `PRODUCT-PRINCIPLES`, and `PRODUCT-BOUNDARIES` rather than restating them; read those first for the underlying contract. This guide is informative — it cites stable IDs for their normative content instead of duplicating it.

## 1. When to use it

Reach for Orc Werk when three conditions co-occur:

1. **Delegated work whose "done" cannot be taken at face value.** Acceptance must be separated from the executor's own claim and bound to the exact artifact produced (`INV-003`, candidate-bound assurance per `INV-005` through `INV-010`).
2. **Delivery that outlives a sitting.** Attempts, verdicts, and pending states must survive process exits and the operator's attention span, not just live in one terminal session (`P-008`, `PORT-JOURNAL`).
3. **Non-trivial structure.** Dependent work items, bounded retries, or multiple agents that need one authoritative record of what happened (`INV-004`, `INV-018` through `INV-020`, `INV-011`).

One-line positioning: CI verifies code; trackers hold intentions; Orc Werk durably and skeptically holds the delivery in between — attempts, candidates, verdicts.

### When NOT to use it

- A single task you watch to completion and review immediately yourself.
- Executors whose reports you already trust unconditionally — compilers, deterministic scripts, anything where a non-zero exit code is a sufficient verdict.
- Anywhere a TODO list or a CI pipeline already provides the guarantee you need. Orc Werk earns its keep at the seam between "an agent said it's done" and "someone/something independently agrees" — if that seam does not exist in your workflow, the product has nothing to add.

## 2. Prerequisites (the adoption ladder)

Orc Werk has no server, no daemon, no database, and no accounts. Every rung below is reached by adding a real provider behind a port, not by standing up infrastructure. Per run, the only prerequisites are an intent, optionally a plan, a journal directory, and an assurance source — someone or something willing to render a verdict. That last one is the prerequisite adopters most often forget, and the one the product exists to insist on: without it, `INV-003` has nothing to check execution's claim against.

| Rung | What it gives you | What it adds | Status |
|---|---|---|---|
| Simulator / spec-executor | Drives the pure delivery state machine end to end with in-memory/scripted providers; no real work, no real agents. | Python 3.11+ and this repo — nothing else. | Usable today (`M-001` M0 baseline) |
| Durable ledger for real, operator-recorded work | A real multi-work delivery run through `orc dispatch`/`status`/`history`, with the operator recording outcomes as they become known and the run surviving process exits between steps. | Pending/incremental dispatch mode (`TASK-M1-002`) | M1a |
| Multi-agent ledger | Ship and verify subagents record their own settlement, candidate, and assurance observations through the CLI instead of the operator transcribing on their behalf. | The agent CLI usage guidance playbook (`TASK-M1-006`), agents with shell access to the `orc` CLI | M1a+ |
| Autonomous orchestrator | Execution itself is automated — no human in the settlement-recording seat. | A real `PORT-EXECUTION` adapter (`TASK-M1-005`) plus the durability contract that governs what it must persist (`CONTRACT-DURABILITY`) | M1b |

Each rung is strictly additive: nothing on a lower rung is replaced, only the execution/recording seat moves further from the operator's own hands. Stopping at any rung is a legitimate, supported adoption point — there is no rung you are obligated to climb past.

The lower ledger rungs use **scripted mode**: with execution and assurance adapters scripted or absent, orc records and advances state while the invoking agent performs the work and records settlements and verdicts by hand. The higher, autonomous rung uses **adapter-driven mode**: an ACP execution adapter and/or a non-scripted assurance adapter drives its configured seat, so the invoking agent configures rather than performs that seat. `orc onboard` derives this mode from `.orc/profile.json`; an absent profile is the incremental scripted default.

### Installing the CLI, mechanically (`TASK-M3D-001`)

The rungs above describe capability; this is the literal install path for each:

- **Rung 1 (simulator/spec-executor) — zero install.** Clone or vendor this repository and either `pip install -e .` for a real `orc` command, or alias the module invocation with no install step at all: `alias orc='PYTHONPATH=src python3 -m orc_werk.cli'` (run from the repo root). This is the adoption ladder's own "Python 3.11+ and this repo — nothing else" promise, and it remains the permanent zero-install fallback at every rung above it — nothing below forces a real install.
- **Rung 2 (durable ledger for real work) — `pip install`, then `orc onboard`.** `pip install <path-to-a-checkout>` or `pip install <git-or-URL-source>` installs the package and its `orc` console script (`[project.scripts]`, `pyproject.toml`) onto `$PATH`, real going forward rather than an aliased module invocation. From there, `orc onboard [--path DIR]` mechanizes the adopting-repo scaffold this section used to describe as hand-work: it ensures a `.orc/` `.gitignore` entry, installs the orc-ledger skill (content read from THIS installed package — one canonical origin, never a second hand-maintained copy) resolvably under `.claude/skills`, writes (or `--print-agents-block` prints, writing nothing) the copy-pasteable `## Delivery ledger (orc)` block below into the target repo's `AGENTS.md`, and reports install verification honestly (`orc` on `$PATH` vs. module form, journal dir resolution, optional `bd` presence). Idempotent re-run; an operator-modified target is skip-with-note unless `--force`. See `docs/cli/README.md`'s `orc onboard` reference for the full flag/output detail.
- **Rungs 3–4 (multi-agent ledger, autonomous orchestrator)** — no additional install step: the same `orc` binary `onboard` verified, now driven by agents recording their own observations (`PLAYBOOK-AGENT-CLI`) or a real `PORT-EXECUTION` adapter, per the ladder table above.

## 3. Tailor-fitting (the customization surfaces)

Orc Werk is customized by *where* you plug into it, not by forking it. The surfaces below are listed in the order most adopters touch them.

### Adapters — the primary surface

Implement the five mandatory ports (`PORTS-INDEX`) against your own systems:

- your issue tracker as `PORT-WORK-GRAPH`;
- your runner or agents as `PORT-EXECUTION`;
- your review process — human or automated — as `PORT-ASSURANCE`;
- your storage as `PORT-JOURNAL`;
- your artifact identity as `PORT-CANDIDATE`.

The conformance suites (`CONF-WORK-001` through `CONF-WORK-004`, `CONF-EXEC-001` through `CONF-EXEC-004`, `CONF-CAND-001` through `CONF-CAND-003`, `CONF-ASSURE-001` through `CONF-ASSURE-004`, `CONF-JOURNAL-001` through `CONF-JOURNAL-003`, and `CONF-EXT-001` through `CONF-EXT-006` where applicable) are the acceptance tests: an adapter is fit for use when the applicable suites pass against it. Reusable, factory-parameterized versions of these suites already exist under `tests/conformance/` for exactly this purpose — a new adapter runs the same suite the reference in-memory/scripted adapters run, not a bespoke one. Provider vocabulary — API shapes, CLI flags, provider-native identifiers — stays inside your adapter and its `docs/adapters/` mapping doc (`INV-014`); it must never leak into core contracts or policy.

### Capability honesty

Advertise only the `CAP-*` capabilities (`CONTRACT-CAPABILITIES`) your adapter genuinely delivers. An unsupported stronger semantic must fail explicitly rather than silently degrade (`INV-013`), and a durability-bearing capability carries a durability obligation — it must not be claimed unless the durable evidence it implies can actually be persisted (`CONTRACT-CAPABILITIES`'s capability-durability rule, `CONTRACT-DURABILITY`).

### Extensions — domain payloads

Specialized semantics that are not required by the generic delivery state machine ride versioned extensions under `docs/extensions/`, per `CONTRACT-EXTENSIONS`. The registered extensions — `EXT-REVIEW-FINDINGS-V1` (`review-findings/v1`) and `EXT-EXECUTION-SESSION-V1` (`execution-session/v1`) — are the worked examples for how to add your own. Extensions never override canonical fields, and unknown extensions must transport losslessly, so independently-tailored deployments can still share a journal and ignore each other's private payloads. (`EXT-CREW-REPORT-V1` (`crew-report/v1`) was a third registered extension; it is now superseded — removed per the reference-first narrative doctrine, issue #100 part 2 — in favor of resolvable references carried by `execution-session/v1`/`evidence_refs` and surfaced via `orc refs`.)

### Durable ownership

If your deployment produces durable information that is not part of the canonical core — reports, provenance, configuration, anything else — give it an explicit owner per `CONTRACT-DURABILITY`. Silent loss of that information is a defect, not an acceptable simplification; `CONTRACT-DURABILITY`'s ownership matrix and Rozoro retirement ledger are the worked template for classifying non-core durable state as canonicalized, delegated, implementation-local, or intentionally dropped.

### Policy configuration

Retry budgets (`max_attempts`), required capability strengths (for example, resume exactness), and assurance requirements are policy inputs you set, not forks of the kernel (`P-007`, `INV-019`).

### Plans

Model your workflow's topology as the portable plan shape: works plus accepted-completion dependencies (`INV-015`, `INV-016`). This is how your dependency graph — whatever tool it lives in upstream — gets expressed to the kernel.

### Composition layer

The reference CLI's config format is explicitly non-normative, CLI-owned composition (`docs/playbooks/cli-usage.md`). Adopters are expected to build their own composition layer — their own CLI or service that wires their adapters into the app orchestrator. The app + core + ports layers (`ARCH-REPOSITORY-STRUCTURE`) are the product; the CLI is a reference consumer of it, not the boundary of what you may build.

### What you must not tailor

The canonical state machine, its invariants, the facts/decisions/effects vocabulary, and the portable record shapes are not customization surfaces. Cross-deployment interoperability and the product's guarantees exist precisely because these stay fixed across every adapter and extension. When one of them does not fit your case, that is a contract-change proposal upstream (`docs/README.md`'s authoring rules), not a local fork.

### Onboarding sessions in an adopting repository

`orc onboard [--path DIR]` (`TASK-M3D-001`) mechanizes this: it installs the
`orc-ledger` project skill into the adopting repository at
`.agents/skills/orc-ledger/SKILL.md` and links it resolvably under
`.claude/skills/orc-ledger`, and writes (or, with `--print-agents-block`,
just prints) the same six-rule content as a copy-pasteable
`## Delivery ledger (orc)` block for `AGENTS.md`-style files, including a
mode declaration derived from `.orc/profile.json` — the audience
issue #55's superseded onboarding-snippet idea was right for all along:
subagents in the adopting repo, distinct from the interactive-session skill
above. A fresh session (interactive, via the skill, or a subagent, via the
`AGENTS.md` block) then self-onboards the same way either surface teaches:
orient via bare `orc`, resume rather than duplicate pending runs, and follow
`PLAYBOOK-AGENT-CLI`'s seat discipline before recording. Both surfaces stay
at six rules because the CLI's affordances teach the rest in situ, and both
are sourced from the exact same packaged skill content — never two
maintained copies of the protocol.

## 4. Worked example — a fleet control tower (Rozoro)

Rozoro is a control-tower persona: an operator delegating parallel work to a fleet of coding agents, then watching, steering, and reaping what comes back. It is a useful worked example precisely because it is not itself an Orc Werk deployment — mapping it onto the four questions any adopter must answer (`PRODUCT-THESIS`) exposes both the fit and the honest gaps.

**Candidate.** The artifact a crew's report points at — a head sha or PR for repo work. For artifact-less tasks (research, a written recommendation), the written findings are themselves promoted to candidate. This is the central reframing a tower persona forces: a crew's own narration of its progress is a claim, not a fact — and only an accepted artifact satisfies `INV-003`. Orc Werk does not give that narration its own canonical field (`crew-report/v1`'s `claimed_verdict` was an early attempt at one; it is now superseded, per the reference-first narrative doctrine below); the claim lives wherever the crew's own tooling already keeps it, referenced rather than duplicated. The tower's job is to stop treating "the crew said done" as "done."

**Assurance.** The operator, a verifier crew member, or a validation pipeline, each wrapped as an `AssurancePort`. Nothing about assurance requires it to be human; the port boundary is what lets a tower swap a hasty human glance for a real verification pipeline without touching the rest of the model.

**Work.** Tower tasks map 1:1 onto `Work`, mostly as flat plans rather than deep dependency graphs. Claim-once-per-lineage *is* crew assignment: a crew member claiming a task is exactly `PORT-WORK-004`'s single-claimant discipline (a claim is once per Work lineage, in the reduced key form `INV-020` requires for idempotency). A crew sitting in "waiting"/"inputs needed" maps onto the pending state (`SCN-007`) — it is not a failure, it is a Work resting at `EXECUTING`/`ASSURING` for an outcome not yet observed. Steering a crew member — sending it a follow-up instruction mid-task — is the send operation, `CAP-EXEC-SEND`.

**Durable domain data.** `execution-session/v1` (registered, `EXT-EXECUTION-SESSION-V1`) covers session/resume provenance. A crew's own append-only turn narration was originally given a dedicated adapter-owned log (`crew-report/v1`, `EXT-CREW-REPORT-V1`) to close the open gate `CONTRACT-DURABILITY` recorded for M1b design time; this persona was exactly the design input that gate was waiting on. That specific extension is now superseded (operator ruling, issue #100 part 2, "reference-first narrative doctrine"): narrative content stays provider-owned, and the ledger journals a resolvable reference to it instead — `execution-session/v1` and assurance `evidence_refs` are the surviving instances of the pattern, surfaced read-only via `orc refs`. Crew "steering" still maps onto `CAP-EXEC-SEND`, unaffected by the removal. Work-spec briefs (the delegated task description a crew member starts from) are the multi-work delegated-brief case the same contract still leaves open.

### Honest misfits

Not everything about a tower experience is in scope for Orc Werk's kernel:

- **Live cockpit/panes.** Watching a crew member's terminal in real time is a feed; `PORT-JOURNAL` is a record. The journal replays what happened, it does not stream what is happening.
- **Fleet-wide dashboards.** A view spanning many crew members/runs at once is composition-layer aggregation over many individual run journals, not a kernel concern — the kernel's unit is one `DeliveryRun`.
- **Needs-action/ack workflows.** Surfacing "this crew member needs your attention" and tracking acknowledgement waits on the reserved attention model (`INV-017`, out of scope through M1 per the milestone ledger).

### Conclusion

A tower tool is not replaced by Orc Werk — it is split. State, acceptance, and durability move into the kernel (`Work`/`Execution`/`Candidate`/`Assurance`, the journal, candidate-bound acceptance); the cockpit and fleet-wide UX stay in the composition layer, built on top. An end user driving a tower adopts the kernel underneath it without ever needing to know the kernel's name.

## Related

- `PRODUCT-THESIS`
- `PRODUCT-PRINCIPLES`
- `PRODUCT-BOUNDARIES`
- `PORTS-INDEX`
- `CONFORMANCE-INDEX`
- `CONTRACT-EXTENSIONS`
- `CONTRACT-DURABILITY`
- `CONTRACT-CAPABILITIES`
- `M-001`
- `ARCH-REPOSITORY-STRUCTURE`
- `PLAYBOOK-CLI-USAGE`
