---
id: PRODUCT-ADOPTION
type: guide
status: current
authority: informative
description: Operator-facing adoption guide — when to use Orc Werk, prerequisites, and how to tailor-fit it.
---

# Adoption guide

This guide answers three questions an operator asks before adopting Orc Werk: when to use it, what must be true before it can be used, and where it is meant to be shaped to fit a deployment. It complements `PRODUCT-THESIS`, `PRODUCT-PRINCIPLES`, and `PRODUCT-BOUNDARIES` rather than restating them; read those first for the underlying contract. This guide is informative — it cites stable IDs for their normative content instead of duplicating it.

**To onboard an AGENT to an adopting repo**, point it at `docs/playbooks/agent-onboarding.md` (`PLAYBOOK-AGENT-ONBOARDING`) instead — a single, imperative, top-to-bottom executable entry point covering install, `orc onboard`, the day-to-day dispatch/record loop, and optional ergo coexistence wiring. The rest of this document is the operator-facing why: when to adopt, the ladder, the customization surfaces.

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
| Multi-repo portfolio cockpit | After one repository has adopted its own ledger, several repositories project deliveries onto one shared board while retaining separate local journals. | The same `mirror.workspace` in every repo, a distinct `mirror.project` per repo, and the board read-back recipes in `PLAYBOOK-PORTFOLIO-COCKPIT` | M4a |
| Autonomous orchestrator | Execution itself is automated — no human in the settlement-recording seat. | Dormant since 0.5.0 (`ADR-0005` removed the `acp` `ExecutionPort` adapter that reached this rung at `TASK-M1-005`); reopening is a fresh spike gated on a stable, contractually versioned settlement/liveness API from a target provider — see the dormant-registry entry in `docs/delivery/M4-cockpit-and-clarity.md`. The durability contract that would govern what a future adapter must persist (`CONTRACT-DURABILITY`) is unaffected. | Dormant (previously M1b) |

Each rung is strictly additive: nothing on a lower rung is replaced, only the execution/recording seat moves further from the operator's own hands or expands to a shared view. Stopping at any rung is a legitimate, supported adoption point — there is no rung you are obligated to climb past.

For multi-repo adoption, start with one repository and its own local journal. Then configure every participating repository with the same Beads `mirror.workspace` and a distinct `mirror.project`; keep each repository's journal local with `ORC_JOURNAL_DIR` (or its local `./.orc` default). Read the combined board with `bd` itself, never through an Orc cross-project reader. `PLAYBOOK-PORTFOLIO-COCKPIT` gives the runnable project, all-project, and per-run recipes.

The lower ledger rungs use **scripted mode**: with execution and assurance adapters scripted or absent, orc records and advances state while the invoking agent performs the work and records settlements and verdicts by hand. As of 0.5.0, execution itself stays external and pushes its observation in (`ADR-0005`); the currently-live **adapter-driven mode** is assurance-only — a non-scripted assurance adapter (for example, command assurance) drives its configured seat, so the invoking agent configures rather than performs that seat. (The autonomous orchestrator rung's own adapter-driven execution seat is dormant — see the table above.) `orc onboard` derives this mode from `.orc/profile.json`; an absent profile is the incremental scripted default.

### Installing the CLI, mechanically (`TASK-M3D-001`)

The rungs above describe capability; this is the literal install path for each:

- **Rung 1 (simulator/spec-executor) — zero install.** Clone or vendor this repository and either `pip install -e .` for a real `orc` command, or alias the module invocation with no install step at all: `alias orc='PYTHONPATH=src python3 -m orc_werk.cli'` (run from the repo root). This is the adoption ladder's own "Python 3.11+ and this repo — nothing else" promise, and it remains the permanent zero-install fallback at every rung above it — nothing below forces a real install. The alias form is invisible to non-shell callers — `command -v orc` fails and a spawned child process (for example Node's `spawnSync('orc')`) gets `ENOENT`/a null status, because a shell alias is never inherited by a spawned process — so automation should probe the module form (`python3 -m orc_werk.cli`) as a fallback and treat an unresolvable `orc` as a loud failure, never a silently skipped step (issue #238; `orc onboard`'s own PATH-vs-module verification output names this directly).
- **Rung 2 (durable ledger for real work) — `pip install`, then `orc onboard`.** `pip install <path-to-a-checkout>` or `pip install <git-or-URL-source>` installs the package and its `orc` console script (`[project.scripts]`, `pyproject.toml`) onto `$PATH`, real going forward rather than an aliased module invocation. From there, `orc onboard [--path DIR]` mechanizes the adopting-repo scaffold this section used to describe as hand-work: it installs the orc-ledger skill (content read from THIS installed package — one canonical origin) resolvably under `.claude/skills`, writes a slim mode/locality/skill-pointer block into `AGENTS.md`, and reports install verification honestly. Ledger placement is explicit: `--ledger local` is the default and adds `.orc/` to `.gitignore`; `--ledger committed` leaves `.gitignore` unchanged and warns if an existing ignore entry conflicts. Use `--agents-block full` only for an agent harness that cannot load the installed skill. `--print-agents-block` prints the selected block without writing. Idempotent re-run; an operator-modified target is skip-with-note unless `--force`. See `docs/cli/README.md`'s `orc onboard` reference for full flag and output detail.
- **Higher rungs (multi-agent ledger, multi-repo cockpit, autonomous orchestrator)** — no additional Orc install step: the same `orc` binary `onboard` verified, now driven by agents recording their own observations (`PLAYBOOK-AGENT-CLI`), configured to project multiple repos into one board (`PLAYBOOK-PORTFOLIO-COCKPIT`), or backed by a real `PORT-EXECUTION` adapter, per the ladder table above.

For both the rung-1 checkout/module path and rung-2 package install, `orc version` reports which install form is actually running, including checkout git identity when available.

The distributed `orc-ledger` skill is versioned: its installed frontmatter names the version, and the `CHANGELOG.md` installed alongside it explains what changed and why. Re-running `orc onboard` automatically upgrades a stale, unmodified copy while preserving an operator-modified copy unless `--force` is explicit; the verification report prints the installed skill version. Maintainers ship every skill behavior change with a version bump and changelog rationale, and the test suite enforces that discipline.

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
`.claude/skills/orc-ledger`, and writes (or, with `--print-agents-block`, just prints) a slim
`## Delivery ledger (orc)` block for `AGENTS.md`-style files. The block carries
the mode derived from `.orc/profile.json`, the selected ledger locality, and a
pointer requiring agents to load the installed skill before touching the
ledger. This keeps the skill as the one protocol copy and avoids loading it in
every unrelated session. Harnesses without skill support can select
`--agents-block full`; that compatibility form mechanically derives the six
rules from the packaged skill rather than maintaining another copy. The skill
is self-contained, names `orc -h`, `orc config-schema`, `orc validate`, and
`orc verdict` as local references, and marks upstream Orc Werk stable-ID
citations as external.

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
- `PLAYBOOK-PORTFOLIO-COCKPIT`
