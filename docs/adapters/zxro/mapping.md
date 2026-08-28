---
id: ADAPTER-ZXRO-MAPPING
type: adapter-mapping
status: draft
authority: informative
description: Draft zxro mapping to canonical orchestration concepts.
---

# zxro mapping

Expected conceptual mappings to verify:

| Canonical | zxro concept | Note |
|---|---|---|
| Work execution lineage | Work + Turn | Turn is close to canonical Execution/attempt lineage |
| external runtime binding | turn/session/native-session binding | provider detail remains opaque |
| execution settlement | turn settlement | outcome must remain separate from acceptance |
| artifact refs | turn artifacts | candidate/evidence adapters interpret them |
| attention event | inbox event | optional AttentionPort mapping |

The kernel must preserve `INV-003`, `INV-017`, and provider opacity.
