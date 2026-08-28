# Agent instructions

This repository is docs-driven and contract-first.

Before implementation:

1. Read `docs/README.md`.
2. Identify the canonical contract IDs governing the task.
3. Do not invent missing semantics in code.
4. Update/propose the canonical contract first when behavior is ambiguous.
5. Add or update a scenario/conformance requirement before implementation when behavior changes.
6. Provider-specific concepts stay in adapters and adapter docs.
7. `src/orc_werk/core` must remain importable and testable with the Python standard library only and zero integration dependencies.
8. Python is the v0.x reference implementation, not a product semantic. Do not persist Python objects, class names, exceptions, pickle payloads, or other language-specific shapes as canonical domain/protocol state.
9. Canonical serialized shapes must use portable JSON-compatible data with explicit schema/version semantics where persistence or interchange is involved.
10. Self-healing behavior must come from explicit journal replay, reconciliation, idempotent effects, bounded retry/replan policy, and capability-aware fallback—not implementation-language magic.
11. Run `python3 scripts/docs_check.py` before committing documentation changes.
