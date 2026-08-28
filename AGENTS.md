# Agent instructions

This repository is docs-driven and contract-first.

Before implementation:

1. Read `docs/README.md`.
2. Identify the canonical contract IDs governing the task.
3. Do not invent missing semantics in code.
4. Update/propose the canonical contract first when behavior is ambiguous.
5. Add or update a scenario/conformance requirement before implementation when behavior changes.
6. Provider-specific concepts stay in adapters and adapter docs.
7. Specialized semantics that are not required by the generic delivery state machine belong in versioned extensions under `docs/extensions/`; extensions must satisfy `CONTRACT-EXTENSIONS` and must not override canonical core fields.
8. `src/orc_werk/core` must remain importable and testable with the Python standard library only and zero integration dependencies.
9. Python is the v0.x reference implementation, not a product semantic. Do not persist Python objects, class names, exceptions, pickle payloads, or other language-specific shapes as canonical domain/protocol state.
10. Canonical serialized shapes must use portable JSON-compatible data with explicit schema/version semantics where persistence or interchange is involved.
11. Self-healing behavior must come from explicit journal replay, reconciliation, idempotent effects, bounded retry/replan policy, and capability-aware fallback—not implementation-language magic.
12. Run `python3 scripts/docs_check.py` before committing documentation changes.

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
