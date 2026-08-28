---
id: ADAPTER-ZXRO
type: adapter
status: draft
authority: informative
description: Planned zxro adapter for durable execution/attention composition.
---

# zxro adapter

zxro is expected to contribute durable Work/Turn binding, per-turn artifacts, settlement facts, and optional attention semantics. It must not redefine canonical Work or acceptance semantics.

Likely seams:

- Execution metadata/binding support around `PORT-EXECUTION`;
- optional future AttentionPort;
- artifact references consumed by `PORT-CANDIDATE` and `PORT-ASSURANCE` adapters.
