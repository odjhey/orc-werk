---
id: PLAYBOOK-ENGINEERING-METHOD
type: playbook
status: current
authority: informative
description: Cross-cutting engineering method for the agents in this workflow (how we write instructions, diagnose, verify, design, and record), distilled from external-skill audits and our own practice. Distinct from orc CLI functionality.
---

# Engineering method

This playbook is the durable home for **method** — how the agents in this
workflow write instructions, diagnose problems, verify work, generate designs,
and keep records. It is deliberately separate from `PLAYBOOK-WATCHTOWER` (the
orc-specific delivery operating model) and from orc CLI functionality: these
disciplines transcend orc and apply to any agent working in this loop. Reach for
it when authoring a brief, playbook, scenario, or the skill; when a shipper hits
a bug; when a verifier reviews; when a contested design goes to the operator.

Provenance: distilled from two external-skill audits (`davidondrej/skills`,
`mattpocock/skills`, `~/notes/2026-08-30-*.md`) cross-checked against this
repository's own practice (`~/notes/2026-08-28-*.md`). The individual sources are
cited per discipline. `PLAYBOOK-WATCHTOWER` carries the delivery-pipeline rules
that reference this method; `DELIVERY-STANCE` carries the values it serves.

## 1. Writing agent-facing instructions

Every brief, scenario, definition of done, playbook, and skill is read and
executed by an agent. Write for that reader.

- **Completion criteria have two independent levers: clarity and demand.** A
  fuzzy bound causes premature completion (the agent drifts to feeling done);
  demand ("every modified model accounted for") forces more work than a vague
  ask ("produce a change list"). Fix order: sharpen the bound first (cheap);
  only split the sequence to hide later steps if the bound is irreducibly fuzzy
  and you actually observe the rush, and hiding works only across a real context
  boundary (a scout to ship hand-off or a subagent dispatch), never an inline
  instruction. This is the authoring complement to the reward-hacking clause in
  `PLAYBOOK-WATCHTOWER`: that clause forbids gaming the bar; this makes the bar
  exhaustive so there is less to game.
- **Two loads.** An always-loaded line (a folder `CLAUDE.md`/`AGENTS.md` entry,
  a skill description) spends context on every turn; a doc a human must remember
  exists spends the human as an index. An always-loaded line must earn its slot
  by beating the model's default behavior. Settle a "does this line say
  anything?" dispute by running the doc, not by debating it.
- **Prompt the positive.** A prohibition drags the forbidden behavior into
  context and makes it more available ("do not think of an elephant"). State the
  target behavior positively; keep a prohibition only for an unphraseable
  positive, and even then pair it with the positive target. State a security
  allowlist as what is permitted; the writer/exec denylist stays the hard
  backstop, not the framing.
- **Leading words.** Reuse a word already in the model's pretraining (*tight*,
  *red*, *tracer bullet*) as a bare, repeated token rather than spelling out a
  sentence; it recruits priors for free and anchors behavior. Stable IDs anchor
  *references*; leading words anchor *behavior*.
- **Environment is a source of truth; a doc that restates it is a cache.** Cache
  only the expensive or unfindable fact (the unwritten convention, the reason
  behind a choice, the gotcha no config confesses). Leave one-file, one-command
  facts to the environment where they cannot go stale. The decay mode is
  *sediment*: stale layers accumulate because adding feels safe and removing
  feels risky. When a sentence names nothing the reader would not already do,
  delete the whole sentence, not a few words.

Source: `mattpocock/skills` writing-for-agents.

## 2. Diagnosing a problem

- **The red-capable-command gate.** You may not form a hypothesis until you can
  name one command, already run at least once, that drives the real code path
  and asserts the *exact* reported symptom (not "runs without erroring"). No
  red-capable command, no diagnosis. This is the bug-specific instance of
  stop-and-report: it turns the maxim into a checkable artifact-gate.
- **Rank hypotheses before testing any.** Write 3 to 5 falsifiable hypotheses,
  each as a prediction ("if X is the cause, changing Y makes the symptom
  disappear"). Show the ranking to the operator for cheap re-ranking, but
  proceed while they are away — direction is theirs, the legwork is yours.
- **Tag instrumentation for a clean exit.** Mark every debug probe with a unique
  token (for example `[DEBUG-a4f2]`) so cleanup is a single grep, enforced in
  the completion checklist.
- **A missing seam is itself a finding.** If no correct seam exists to write the
  regression test that would catch the bug, that absence is the finding — flag
  the architecture rather than write a shallow, false-confidence test.
- **Verify a fix on both sides.** A fix claim needs the baseline to reproduce
  the symptom twice (with state reset between attempts) *and* the patched build
  to clear it twice under the same state check. No twice-reproduced baseline
  means there is no baseline — do not claim the fix works. When verification
  contradicts expectation, suspect the observation method before the system.

Source: `mattpocock/skills` diagnosing-bugs; `cursor/plugins` pstack benny.

## 3. Verifying work

Extends the adversarial verification in `PLAYBOOK-WATCHTOWER` (independent
identity derivation, run-the-claims, hunt tautological tests, mutation smoke).

- **Two axes, never merged.** Review on two separated axes: *Spec* (does it match
  the originating intent) and *Standards* (repo conventions plus a fixed
  code-smell baseline). Report them side by side and never rerank across axes, so
  a spec-faithful but convention-breaking change (or the reverse) cannot have one
  axis mask the other.
- **Carry a smell baseline.** Keep a fixed named-probe library (mysterious name,
  speculative generality, shotgun surgery, and the like) that the verifier
  applies even when the repo docs are silent — a portable checklist of judgment
  calls, distinct from tooling-enforced lint.
- **Name the one safety fact, and grade the evidence.** Most scary changes are
  safe because of a *single* fact; identify it and spend the effort proving that
  fact rather than enumerating maybes. Grade every load-bearing claim on the
  evidence ladder — asserted → cited at file:line → failure path walked → ran
  the real code → reproduced in the running system — say where each claim
  stopped, and mark anything below "ran the real code" as unproven. A green
  gate is an *input* to a verdict, never the verdict.
- **Publish dismissals; cap the musts.** Triage findings into act-on and
  dismissed, and ship the dismissed list *with one-line rationales* — it is the
  operator's override channel, not noise. More than a handful of must-fix
  findings means the filter failed. One asymmetry: a lone security or
  correctness finding earns extra scrutiny, never the consensus discount.

Source: `mattpocock/skills` code-review; `cursor/plugins` pstack blast-radius,
interrogate.

## 4. Generating a design for a contested decision

When a contested design or contract decision is headed to the operator, generate
before you price.

- **Constraint-differentiated generation.** Spawn several explorers, each given
  an *orthogonal forcing function* — minimize the interface, maximize
  flexibility, optimize the common caller, ports and adapters — rather than
  several neutral explorers. Divergent priors produce genuinely different designs
  instead of variations on the first idea.
- **Compare on pre-declared axes, then recommend.** Score the candidates on axes
  named before generation, and deliver one opinionated recommendation, not a
  menu. Then consequence-price the recommendation (options, named costs,
  mitigations) for the operator per `PLAYBOOK-WATCHTOWER`. The operator wants a
  strong read they can veto, not a survey.
- **Graft from the losers; read divergence as a brief smell.** Mine the losing
  candidates for one or two portable ideas and fold them into the winner by
  hand, keeping the rejection notes — they are the highest-signal part of the
  record. Wild divergence across candidates means the framing was
  under-specified: reframe and regenerate, never average. Convergence means
  ship the consensus and skip the graft.

Source: `mattpocock/skills` design-it-twice; `cursor/plugins` pstack arena.
Compose with our fan-out habit.

## 5. Artifacts and records

- **Two artifact tiers, opposite precision.** A durable spec dwells for weeks and
  stays path-free and code-free (paths and snippets go stale), *except* a single
  snippet that encodes a decision more precisely than prose can (a state machine,
  a schema, a type shape). A just-in-time dispatch brief is the inverse:
  command-exact, with ordered required-reading and per-step fallbacks. Do not
  dilute a brief toward durability, and do not make a spec command-exact. Know
  which tier you are writing.
- **Decisions emit checkable invariants.** A ruling that changes behavior should
  enumerate the invariants it creates so tooling can enforce them (for example
  "the plugin version tracks package.json; bump together"), not only narrate the
  choice.
- **Supersede in place, with evidence.** Revise a decision by appending a dated
  update carrying verification evidence (the exact command, version, observed
  output), and mark the superseded claim rather than deleting it — the evolution
  is signal.
- **Reconcile every new rule against the invariant stated nearby.** A convention
  added without checking the invariant a few lines above ships a contradiction to
  every site that copies it. Cross-read a new rule against its neighbors, the
  same way `PLAYBOOK-WATCHTOWER`'s bidirectional check cross-reads a diff against
  its contract.
- **Hand off state, not instructions.** A hand-off doc records what is true
  ("auth is implemented; logout is not"), carries a *Traps and dead ends*
  section, and tells the next reader to verify every claim against the artifact
  rather than trusting it. Reference other artifacts by name and link; never
  restate their content.
- **Stamp provenance on a captured item.** A backlog entry, deferred-decision, or
  finding carries where it came from — repo, session, date — so it stays
  traceable months later.
- **Encode a lesson at the strongest rung available.** When several mechanisms
  would enforce a lesson, pick the strongest: unrepresentable state, then a
  CI-failing check, then a canonical helper, then a runtime check, and prose
  last — because agents template off whatever guard the surrounding code shows,
  so a weak guard becomes the next copy's pattern. Capturing without routing,
  and fixing without generalizing, are the named failure modes.
- **Audit the trail against the transcript at hand-off.** Before handing off,
  reconcile the recorded decision trail with what actually happened: cut
  aspirational entries, add unlogged pivots — fix the log, not the story. The
  record's truthfulness is itself a deliverable.

Sources: `mattpocock/skills` to-spec, ADR-0002, changesets; `davidondrej/skills`
handoff, save-idea; `cursor/plugins` pstack encode-lessons-in-structure,
show-me-your-work; our own reference-first doctrine.

## Relationship to the other docs

- `PLAYBOOK-WATCHTOWER` — the orc-specific delivery operating model (roles,
  pipeline, sizing, dormant-feature lifecycle, merge routine). It references this
  method; this method stays orc-agnostic.
- `DELIVERY-STANCE` — the bars and values this method serves (contract fidelity,
  falsifiability, heal-while-using, dogfood-feedback-is-the-backlog).
- `PLAYBOOK-AGENT-CLI` — the ship and verify seat recording protocol.
