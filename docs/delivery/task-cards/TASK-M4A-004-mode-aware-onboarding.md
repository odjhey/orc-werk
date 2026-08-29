---
id: TASK-M4A-004
type: task-card
status: current
authority: normative
description: orc onboard derives the repo's operating MODE from .orc/profile.json's adapter config and writes a mode declaration into the agents-block — retiring the hand-written "orc runs in scripted mode here" preamble.
implements: []
verifies: []
---

# TASK-M4A-004 — mode-aware agents-block

Design source: `M4-COCKPIT-AND-CLARITY` Phase M4a (operator direction,
2026-08-30). Composes with `TASK-M4A-001` (writes the profile) and
`TASK-M4C-001` (the role guide the declaration points at).

## The gap
Today, to onboard agents in a repo that uses orc WITHOUT the acp/no-mistakes
adapters, the operator hand-writes a preamble into the repo's agent
instructions — e.g. "orc runs in scripted mode only here: it records and
advances state, it never spawns or drives agents; dispatch configs must omit
or pin `execution`/`assurance` to `scripted`." `TASK-M4A-001`'s profile
closes the CONFIG half (scripted becomes the default; agents need not be
told to omit/pin). But the MODE DECLARATION half — telling an agent "this is
scripted mode, you are the work-doer, record settlements by hand" — is still
hand-written. This card retires it.

## Outcome
`orc onboard` DERIVES the repo's operating mode from `.orc/profile.json`'s
adapter configuration and writes a mode declaration into the agents-block it
already installs — generated, accurate, not asserted by hand.

Mode is derivable, not declared:
- **scripted mode** — `execution`/`assurance` adapters are `scripted` or
  absent: orc records and advances state; it does not spawn or drive agents;
  the invoking agent does the work and records the settlement/verdict by hand
  (`PLAYBOOK-AGENT-CLI`). This is the lower `PRODUCT-ADOPTION` rung.
- **adapter-driven mode** — `execution.adapter == "acp"` and/or
  `assurance.adapter == "no-mistakes"` (or a future assurance adapter): orc
  spawns/drives the seat via the adapter; the agent configures rather than
  performs. Higher rungs.

The written declaration states the mode, what the agent does in it, that
configs default via `.orc/profile.json` (no adapter blocks needed), and
points at `orc guide <role>` for the depth. Absent a profile, onboard writes
the neutral/scripted-default declaration (orc's incremental default).

## In scope
- `orc onboard` reads the profile (if present) and computes the mode; the
  agents-block gains the mode declaration (idempotent, never-clobber/`--force`
  like the rest of onboard; pure scaffolding — never touches a journal).
- Docs: `PRODUCT-ADOPTION` names the modes against the rungs; `orc onboard`
  reference updated.
- Tests: a scripted-pinned profile → scripted declaration; an acp/no-mistakes
  profile → adapter-driven declaration; no profile → neutral/scripted-default
  declaration; idempotent re-run; the declaration retires the operator's
  hand-written preamble (assert the generated text carries the mode + the
  "configs default via profile" + the guide pointer).

## Out of scope
Any adapter/core change (this is CLI-layer scaffolding + docs); a runtime
"mode" enforcement (the mode is descriptive, derived from config — orc does
not gate on it beyond the existing adapter validation).

## Acceptance
- In a scripted-only repo, `orc onboard` writes an agents-block that DECLARES
  scripted mode and the work-doer flow — the operator no longer hand-writes
  that preamble.
- In an adapter-driven repo, the declaration reflects that accurately.
- The declaration is generated from the profile, idempotent, and points at
  the role guide.
