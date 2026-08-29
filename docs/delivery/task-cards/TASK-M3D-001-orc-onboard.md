---
id: TASK-M3D-001
type: task-card
status: current
authority: normative
description: orc onboard — mechanical adopting-repo scaffold (gitignore, skill install, agents-block, install verification); one canonical skill origin.
implements: []
verifies: []
---

# TASK-M3D-001 — `orc onboard`

Design source: `M3-HARDEN-THE-LOOP` Phase M3d. Details firm up at
dispatch. Non-negotiables carried from the phase note:

- One canonical origin for the skill/protocol content: the installed
  package ships it; `onboard` copies from there — never a second
  maintained copy of the six-rule protocol.
- Idempotent re-run; never silently overwrites operator-modified
  files (diff-and-refuse-with-note, or skip-with-note).
- The agents-onboarding block is printable to stdout as well as
  writable — an adopter pastes it into whatever agent-instructions
  file their repo uses.
- Install verification is honest: reports what resolved (`orc` on
  PATH vs module form, journal dir, optional `bd`), fabricates
  nothing.
- `PRODUCT-ADOPTION` amended in the same PR: per-rung install story
  (pip install path/URL → console script; alias fallback), `onboard`
  as the rung-2 entry step.

## Acceptance (firmed at dispatch)

A clean scratch repo goes from nothing to a working incremental-mode
delivery (dispatch → pending → recorded settlement → verdict → exit 0)
by following only what `orc onboard` installed and printed — verified
by an agent given no other reading.
