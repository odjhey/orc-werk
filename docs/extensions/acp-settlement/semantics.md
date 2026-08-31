---
id: EXT-ACP-SETTLEMENT-V1-SEMANTICS
type: contract
status: current
authority: normative
version: 1
description: Emission and interpretation rules for acp-settlement/v1.
---

# `acp-settlement/v1` semantics

The ACP adapter emits this extension in either of two cases: when it determines an execution settlement is `failed` because the outstanding result is unobservable under the ACP mapping's corroboration rule (`unobservability`), or when it reports `running` because a recorded result is followed by continued or ambiguous activity and therefore is not terminal-quiescent (`suppression`). It emits the extension beside, not inside, `execution-session/v1`.

A `suppression` payload explains why a result was not accepted as a settlement candidate. It MUST NOT turn that candidate into a settlement; subsequent polling and corroborated unobservability determine the attempt's fate.

The payload explains an adapter observation; it does not determine canonical behavior. Canonical `state` and `outcome` remain authoritative, and this extension cannot override them (`EXT-003`). It is never the sole carrier of any canonical outcome, identity, evidence binding, or other canonical information (`EXT-007`).

Consumers MAY display, retain, or ignore these opaque diagnostics. Ignoring the extension MUST NOT change interpretation of the enclosing settlement. Generic core and cross-provider policy MUST NOT infer new settlement semantics from its fields.
