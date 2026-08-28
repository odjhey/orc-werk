# Agent instructions

This repository is docs-driven and contract-first.

Before implementation:

1. Read `docs/README.md`.
2. Identify the canonical contract IDs governing the task.
3. Do not invent missing semantics in code.
4. Update/propose the canonical contract first when behavior is ambiguous.
5. Add or update a scenario/conformance requirement before implementation when behavior changes.
6. Provider-specific concepts stay in adapters and adapter docs.
7. The core must remain importable/testable with zero integration dependencies.
8. Run `python3 scripts/docs_check.py` before committing documentation changes.
