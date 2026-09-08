---
id: ADAPTER-OMP
type: adapter
status: current
authority: informative
description: Oh My Pi (OMP) — the delivery harness hosting orc-werk's own ship/verify/scout seats; not a PORT-EXECUTION/PORT-ASSURANCE adapter orc drives.
---

# OMP adapter

Oh My Pi (OMP) is the coding-agent harness — agent frontmatter (`model`,
`tools`, `output`), the `task` subagent-spawn tool, `tool_call` hooks,
`hub` peer messaging, and session/transcript storage — that hosts
orc-werk's own ship, verify, and scout seats (`ADR-0007`). A ship or verify
agent running under OMP is an **external executor pushing its own
observations** into the ledger through the ordinary `orc`/`orc record` CLI,
exactly as a human operator typing the same commands would (`ADR-0005`'s
push-recording model). OMP changes *who occupies a seat and how strongly
its boundaries are enforced* (agent frontmatter and tool restriction
instead of prose, GitHub branch protection on `master` instead of a bare
convention for the one rule that needs an action-decidable rung; no
`tool_call` hook ships anywhere in this repository — `capabilities.md`'s
findings table and `ADR-0007`'s 2026-09-07 hook-retirement amendment
record why); it does not change what a seat is allowed to record or how
the kernel decides.

## What this is not

OMP is **not** a `PORT-EXECUTION` or `PORT-ASSURANCE` implementation.
`src/orc_werk/adapters/` has no OMP module, and none is planned: per
`T3`/`ADR-0005`, orc never spawns an OMP task and never pull-observes one.
Every Fact an OMP-run seat produces arrives through the exact same
config-entry/`orc record` observation path as any other external executor
— there is no OMP-specific ingestion code path in the kernel to adapt.

Consequently:

- OMP advertises **no** canonical `CAP-*` capability (`capabilities.md`) —
  there is no Port for it to implement one against.
- OMP is not a subject of the `CONF-WORK-*`, `CONF-EXEC-*`, `CONF-ASSURE-*`,
  or `CONF-CAND-*` conformance suites; the only canonical surface it
  touches is the `executor-identity/v1` extension (`conformance.md`).

## Skill frontmatter and OMP's strict YAML parser

OMP's own skill/config loader parses frontmatter with a strict YAML
parser. Authoring the packaged `orc-ledger` skill's frontmatter
`description` for OMP specifically (`docs/delivery/watchtower-operations.md`'s
Conventions section keeps the harness-independent "what + when, never a
how-summary" half of this rule; this is the OMP-specific mechanism
underneath it, moved here per issue #282): no colon-space (`: `) in an
unquoted value — OMP's parser reads it as a nested mapping and the skill
silently fails to load. Single-quote the value and double inner
apostrophes if a mid-sentence colon is unavoidable. The same
colon-space caution applies to any doc frontmatter OMP's own tooling
might strict-parse, not only the packaged skill.

## Scope of this directory

- [`mapping.md`](mapping.md) — the OMP-concept-to-canonical-concept
  mapping (agent definition, subagent spawn, structured output schema,
  session/transcript) and the full `executor-identity/v1` field mapping,
  moved and expanded from the former `PLAYBOOK-AGENT-CLI` §2 prose
  (`TASK-M5-002`).
- [`capabilities.md`](capabilities.md) — the canonical `CAP-*` guarantees
  OMP-as-harness can actually prove (none), plus the harness-level
  seat-discipline guarantees `TASK-M5-001`'s capability test evidences,
  and named limitations where it does not.
- [`conformance.md`](conformance.md) — applicable `CONF-*` status, linked
  to `TASK-M5-001`'s capability-test evidence.

## Related

- `ADR-0007` — the decision that adopts OMP as the primary delivery
  harness, including the isolation ruling (ship seats use a git worktree
  + PR, never OMP `isolated` merge-on-completion) and the `T3`/`ADR-0005`
  no-hook-writes-`.orc` ruling.
- `EXT-EXECUTOR-IDENTITY-V1`
- `docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`) — the
  harness-independent seat discipline (roles, no self-assurance, recording
  mechanics) this directory does not restate.
- `TASK-M5-001` — the capability-test report this directory's honest
  capability claims are sourced from.
