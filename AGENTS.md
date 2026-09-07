# Agent instructions

This repository is docs-driven and contract-first.

Before implementation:

1. Read `docs/README.md`.
2. Identify the canonical contract IDs governing the task.
3. Do not invent missing semantics in code.
4. Docs are part of the product contract: amend the doc first, code follows (nother-guide hard rule 1, pinned `aa1fc24`). Update/propose the canonical contract first when behavior is ambiguous.
5. Add or update a scenario/conformance requirement before implementation when behavior changes.
6. Provider-specific concepts stay in adapters and adapter docs.
7. Specialized semantics that are not required by the generic delivery state machine belong in versioned extensions under `docs/extensions/`; extensions must satisfy `CONTRACT-EXTENSIONS` and must not override canonical core fields.
8. `src/orc_werk/core` must remain importable and testable with the Python standard library only and zero integration dependencies.
9. Python is the v0.x reference implementation, not a product semantic. Do not persist Python objects, class names, exceptions, pickle payloads, or other language-specific shapes as canonical domain/protocol state.
10. Canonical serialized shapes must use portable JSON-compatible data with explicit schema/version semantics where persistence or interchange is involved.
11. Self-healing behavior must come from explicit journal replay, reconciliation, idempotent effects, bounded retry/replan policy, and capability-aware fallback—not implementation-language magic.
12. Run `python3 scripts/docs_check.py` before committing documentation changes.
13. Contract-level ambiguity: stop and report. Local ambiguity: decide and record (nother-guide hard rule 2).
14. One task, one worktree, one branch. Ship agents never merge (nother-guide hard rule 3; mechanics: `docs/delivery/watchtower-operations.md`, `PLAYBOOK-WATCHTOWER`).
15. The local gate is `bash scripts/check.sh`. Run it before reporting done (nother-guide hard rule 4).
16. Every implementation change receives adversarial verification. No agent verifies its own work (nother-guide hard rule 5).
17. Every PR body or report carries "Ambiguities encountered" (state "none" if none) (nother-guide hard rule 6).
18. A refusal is a signal, not an obstacle. Never delete, skip, weaken, or narrow a test, gate, or check to make it pass (nother-guide hard rule 7).
19. A skipped check is loud and counted — `scripts/check.sh`'s final line is `check: green. NOT covered: <list|none>` (nother-guide hard rule 8).
20. Record before destroy: persist intent and evidence before killing a run/session; record the result afterwards; settle the work outcome before teardown, via `orc record` (nother-guide hard rule 9).
21. Proceed on the reversible; pause on the irreversible. A parked question carries a default (nother-guide hard rule 10; full autonomy contract: `PLAYBOOK-WATCHTOWER` §Autonomy and operator interaction).

Rules 13–21 are `nother-guide`'s ten hard rules (pinned reference, commit
`aa1fc24` of `nother-guide/starter-checklist.md`), integrated by content
rather than appended as a second list: rule 1 of that list is merged into
rule 4 above; rules 2–10 had no equivalent among the original twelve and
are stated here as rules 13–21.

## Delivery workflow

Implementation ("ship") agents work in isolated git worktrees under
`.worktrees/<branch-name>` (gitignored), one branch/PR per task card. This
keeps concurrent task cards from colliding in a single checkout and keeps
`master` untouched while work is in flight. PRs are reviewed and merged by
the watchtower session — implementation agents open PRs but do not merge
them.

The local gate is `bash scripts/check.sh`; CI mirrors it exactly via the
single required `ci-required` status check (see
`.github/workflows/ci-required.yml`), so a green `scripts/check.sh` locally
means a green PR remotely.

**Oh My Pi (OMP) is the primary delivery harness for these seats**
(`ADR-0007`). Seat boundaries — model, tools, effort, result schema — are
declared as OMP agent definitions rather than re-taught by prose:
`.omp/agents/scout.md` (recon), `.omp/agents/ship.md` (implementation),
and `.omp/agents/verify.md` (adversarial audit), configured project-wide
by `.omp/config.yml`. `.omp/extensions/orc-seat.ts` does not exist in
this repository's `e102e1e` baseline; `TASK-M5-005` is scoped to add it,
enforcing exactly one guard: a structural, cwd/path-derived fence on
`edit`/`write` file paths, keeping a ship seat's writes inside its own
worktree. It will not attempt to block `yield` before a record, deny `gh
pr merge`, or deny verify-role push/commit/comment, as an earlier design
intended — a `tool_call` hook receives only the bare command string,
never argv or process identity, so every guard deciding by matching that
text was defeated by the shell (established when `task-m5-005`'s attempt
1 was rejected by six reproduced-in-system escapes). Per the 2026-09-07
operator ruling, those three invariants moved rung instead: no direct
push to `master` is GitHub branch protection (applied 2026-09-07);
record-before-yield is enforced structurally only for the paths that
reach `ACCEPTED`/`BLOCKED` through bound assurance — the cancellation
path is a disclosed, unenforced escape from that rung (issue #293); merge
authority has no enforcement rung at all — every seat authenticates as
the same GitHub identity, so it remains seat-discipline prose plus
after-the-fact ledger detection. At `e102e1e`, before the fence exists,
all of this is enforced by convention via `.omp/RULES.md` and the seat
definitions' own prose. `.omp/RULES.md` is the sticky, always-loaded
statement of these invariants for any OMP session working this
repository. Harness-specific mechanics for OMP live in
`docs/adapters/omp/` (`ADAPTER-OMP`); a future harness swap changes that
directory, never this file's rules.

A project skill onboards fresh sessions to the delivery ledger:
`.claude/skills/orc-ledger` (source: `.agents/skills/orc-ledger/SKILL.md`) —
orient via bare `orc`, resume-don't-duplicate, seat discipline, recording
mechanics. The adoption guide (`PRODUCT-ADOPTION`) tells adopting repos to
copy the same skill.

The full operating model — seats (watchtower/scout/ship/verify), pipeline,
task sizing, audit trail, and conventions — is documented in
`docs/delivery/watchtower-operations.md` (`PLAYBOOK-WATCHTOWER`).

Deliveries themselves are tracked in the orc ledger (`.orc/` runs, one
journal per `DeliveryRun`) — the durable record of what was dispatched,
attempted, and settled, independent of GitHub's own PR/issue state.
Dispatch/settle/verify against that ledger per
`docs/playbooks/agent-cli-usage.md` (`PLAYBOOK-AGENT-CLI`).
