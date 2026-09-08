---
id: PLAYBOOK-PRACTICE-ADOPTION
type: playbook
status: current
authority: informative
description: Run the Orc Werk seat protocol by hand with a tracker, an executor, an independent verifier, and a plain evidence store — no Python, no orc CLI, no OMP, GitHub, or Beads required.
---

# Practice-only adoption playbook

This playbook runs the same seat protocol `PRODUCT-THESIS` and
`ORCHESTRATION-CONTRACT` define — durable, replayable, candidate-bound
delivery with independent acceptance — using tools you already have: a
tracker of any kind, a text file, and a second pair of eyes. It requires
none of: Python, the `orc` CLI, OMP, GitHub, or Beads.

This is one of four adoption entry points; see `PRODUCT-ADOPTION`'s
"Choose your entry point" section for how this path compares to the
reference Python CLI, custom composition around it, or building an
independent implementation (`PLAYBOOK-IMPLEMENTERS-GUIDE`).

**What this buys you, and what it does not.** Following this playbook gets
you the seat protocol's *discipline* — candidate-bound acceptance,
independent verdicts, a durable record, seat separation. It does not get
you a conforming Orc Werk implementation. A conforming implementation
mechanically enforces those guarantees against forgetting, editing history,
or self-assurance; a human following a checklist enforces them only by
continuing to follow the checklist. Section 4 below states, line by line,
which guarantee is which. **A manual checklist is not a conforming kernel,
and this playbook does not claim otherwise.**

## 1. Map your existing tools onto the canonical roles

You do not adopt new infrastructure for this path — you name four things
you already have.

| Canonical role | Contract | What plays it here | Examples |
|---|---|---|---|
| Work graph / tracker | `PORT-WORK-GRAPH` | Wherever you already write down "what needs doing" — one line is enough | A sticky note, a spreadsheet row, a plain-text TODO, an existing issue tracker, a notebook page |
| Executor | `PORT-EXECUTION` | Whoever or whatever does the work and can honestly say when it's done | You, a colleague, an AI assistant, a script you run by hand |
| Independent verifier | `PORT-ASSURANCE` | A **different** person or process than the executor, who looks at the exact result and judges it | A colleague who did not do the work, a second reading of your own work after a full day's gap (weak, see below), a checklist a third party runs |
| Evidence store / journal | `PORT-JOURNAL` | An append-only plain-text record nobody edits after the fact | A single markdown or text file you only ever append to, one dated line per event; a physical notebook; a `git log` of a file you only ever append to |
| Candidate identity | `PORT-CANDIDATE` | Whatever exact, comparable thing the verifier will judge | A git commit sha, a file's checksum, a URL to a specific artifact, a PR number pinned to a specific commit — anything two people can independently compute and compare (`INV-006`) |

None of these need to be special-purpose software. The whole point of ports
(`PORTS-INDEX`) is that the roles are fixed and the fillers are not.

## 2. Walk one real work through the whole lifecycle

Pick one real, small piece of work you are about to do anyway. Do not
rehearse this on a fake task — the fresh-session recovery step in 2.6 only
proves anything against a real gap in time and memory.

### 2.1 Intent

Write the intent down verbatim, dated, in your evidence store, before
starting. This is the practice-only analog of `FACT-INTENT-SUBMITTED`
(`PROTOCOL-FACTS`) — an immutable record of what was asked for, so nobody
later reconstructs the ask from memory.

```text
2026-09-08 09:00  INTENT: fix the off-by-one in the weekly report's date range
```

### 2.2 Candidate identity, chosen in advance

Before the executor starts, agree what "the exact thing to be judged" will
be. For code, this is almost always a version-control commit sha; for a
document, a specific file hash or URL; for anything else, name it now. This
mirrors `INV-006` — candidate identity must support exact equality — and
means the verifier in 2.4 is never grading a moving target.

### 2.3 Ship observation (the executor pushes, nobody polls)

When the executor believes the work is done, they write a dated line naming
the exact candidate — never "it's basically done" or "should be fine," an
exact, checkable reference. This is the practice-only analog of
`FACT-EXEC-SETTLED`: an external party (the executor) pushes its own
observation into the record; nobody watches the executor work and infers
completion for them (`ADR-0005` — this is the one piece of Orc Werk's model
you get for free just by writing this down instead of assuming it).

```text
2026-09-08 10:40  SHIP: work done, candidate = commit a1b2c3d (fix-report-range branch)
```

### 2.4 Independently bound verdict

The verifier — a genuinely different person or process than the executor —
independently derives the candidate identity themselves (checks out
`a1b2c3d` themselves, computes the file hash themselves, opens the exact
URL themselves) rather than trusting the executor's description of it. This
is the practice-only analog of `INV-007`/`INV-008`: evidence is bound to the
exact candidate fingerprint, and evidence produced against a different
candidate never counts for this one. The verifier then writes one of three
honest verdicts, with the evidence for it:

```text
2026-09-08 14:15  VERDICT: candidate a1b2c3d — ACCEPTED — ran the report on
                  three sample weeks, all date ranges correct, reviewed the diff
2026-09-08 14:15  VERIFIER: <name, different from the executor>
```

The three verdicts and when to use each (mirroring `PROTOCOL-DECISIONS`'
verdict vocabulary):

- **accepted** — you checked, and it is correct.
- **rejected** — you checked, and it is wrong; say what's wrong, so the next
  attempt is targeted, not a blind retry.
- **inconclusive** — you could not tell either way (you couldn't reproduce
  the environment, the description was ambiguous, you ran out of time to
  check properly). This is the honest answer when you genuinely do not
  know — write it down as inconclusive rather than guessing toward accepted
  or silently saying nothing. Silence looks identical to "nobody has looked
  yet," which is a materially different fact worth distinguishing.

Neither `rejected` nor `inconclusive` is acceptance (`INV-009`) — the work
is not done until an `accepted` verdict exists against this exact candidate.

### 2.5 Acceptance

Only after the accepted verdict is written do you cross the work off as
done. Write the closing line:

```text
2026-09-08 14:20  ACCEPTED: work complete, candidate a1b2c3d
```

Nothing before this line means "done" — not the executor saying so (2.3),
not time passing, not the absence of complaints.

### 2.6 Fresh-session recovery

This is the step that actually tests whether your evidence store is doing
its job, and it is the one most manual practices skip. Wait until you have
genuinely forgotten the details — a day is enough for most small tasks — or
hand the file to someone who was never involved. Using **only** the
evidence-store file, with no memory and no side-channel conversation,
answer:

- What was asked for?
- What was actually shipped, and what's its exact identity?
- Who verified it, and are they a different person from who shipped it?
- What is the current state — done, rejected-and-waiting-on-a-retry, or
  still open?

If any answer requires asking someone or remembering something not written
down, the evidence store has a gap — the practice-only analog of a
conforming `PORT-JOURNAL`'s `load_projection` (`PORT-JOURNAL-005`)
reconstructing state from history alone. Fix the gap in your own recording
habit, not by adding software.

## 3. A short worked example, laid out end to end

The five lines from §2, kept together, are what a complete practice-only
record looks like for one work item:

```text
2026-09-08 09:00  INTENT: fix the off-by-one in the weekly report's date range
2026-09-08 10:40  SHIP: work done, candidate = commit a1b2c3d (fix-report-range branch)
2026-09-08 14:15  VERDICT: candidate a1b2c3d — ACCEPTED — ran the report on
                  three sample weeks, all date ranges correct, reviewed the diff
2026-09-08 14:15  VERIFIER: <name, different from the executor>
2026-09-08 14:20  ACCEPTED: work complete, candidate a1b2c3d
```

If the verdict had instead been `REJECTED`, the next entry would be a new
`SHIP` line naming a new candidate (a new commit), never a silent edit of
the rejected candidate's own line — history is never rewritten, only
appended to (the practice-only analog of `INV-004`: a retry is a new
attempt, not an overwrite of the old one).

## 4. Manual discipline versus mechanical enforcement

This is the section that keeps this playbook honest about what it is. Every
guarantee below is real and worth having; only the right column tells you
whether something enforces it or whether you have to keep choosing to do
it.

| Guarantee | In a conforming kernel (e.g. the reference `orc` CLI) | In this practice-only path |
|---|---|---|
| No self-assurance | Not mechanically enforced by the kernel itself either — it is a seat-discipline rule (`PLAYBOOK-WATCHTOWER`, `orc-ledger` skill), same as here | **Manual.** Nothing stops you grading your own work except your own decision not to. Pick a real second person or process every time. |
| History is append-only, never edited | Mechanically enforced: `PORT-JOURNAL-002`'s immutability, `CONTRACT-STORAGE-CONCURRENCY`'s atomic-append rules, `CONF-JOURNAL-002` | **Manual.** A text file lets you edit any past line. Use a mechanism that makes editing hard to do by accident — a notebook, a write-once log, a version-controlled file you only ever `git commit` after appending, never amend. |
| Candidates compare exactly, not "close enough" | Mechanically enforced: `INV-006` (exact fingerprint equality), `CONF-CAND-001`/`002` | **Manual.** You must actually check out the exact commit / compute the exact hash yourself, not eyeball a description. Nothing stops a sloppy comparison but your own care. |
| Evidence is bound to the one candidate it evaluated | Mechanically enforced: `INV-007`/`INV-008`, `CONF-ASSURE-003` | **Manual.** Write the exact candidate identity on every verdict line; never let a verdict outlive the candidate it was written against. |
| Rejected/inconclusive never silently becomes accepted | Mechanically enforced: `INV-009`, `CONF-ASSURE-002`/`004` | **Manual.** Only write `ACCEPTED` on its own dedicated line, only once, only after an honest accepted verdict exists. |
| One claimant per work at a time | Mechanically enforced: `PORT-WORK-004`'s atomic claim, `INV-020` | **Manual.** You have to actually check nobody else already started the same item before you start it — nothing arbitrates a race for you. |
| Deterministic replay from history alone | Mechanically enforced: `PORT-JOURNAL-005`, `CONF-JOURNAL-003` | **Manual, and only as good as your notes.** Section 2.6's fresh-session test is how you find out whether this held. |
| Retry/assurance budgets are bounded and counted | Mechanically enforced: `INV-018`/`INV-019`/`INV-021`, `ADR-0006` | **Manual, optional.** Decide up front how many retries you'll allow before escalating (asking someone, changing approach) and actually stop there — nothing counts for you. |
| Crash/process-restart durability | Mechanically enforced at a stated durability level (`CONTRACT-STORAGE-CONCURRENCY` §9) | **As durable as your storage.** A paper notebook survives a laptop crash; an unsaved text buffer does not. Choose accordingly. |

The left column is not a to-do list for this playbook to somehow catch up
on — it is the precise reason a conforming implementation exists at all.
When the manual discipline above starts costing more attention than it is
worth (frequent retries, multiple concurrent works, more than one or two
executors), that is the signal to climb the adoption ladder
(`PRODUCT-ADOPTION`) rather than add more paper process.

## 5. When to move on

- **More than one work at a time, or dependencies between them** — the
  reference Python CLI's scripted mode gives you a durable, replayable
  ledger for free; see `PRODUCT-ADOPTION`'s adoption ladder, rung 1
  ("simulator/spec-executor," zero install beyond a checkout) and rung 2
  ("durable ledger for real work").
- **You want the mechanical guarantees from §4's left column without
  writing Python or installing anything you don't control** — see
  `PLAYBOOK-IMPLEMENTERS-GUIDE` for what a from-scratch, non-Python
  implementation must reproduce, with worked portable record examples and
  an observable verification checklist.
- **Your team already runs Python** — `PRODUCT-ADOPTION`'s install section
  and `docs/playbooks/agent-onboarding.md` are the direct path.

## Related

- `PRODUCT-THESIS`
- `PRODUCT-ADOPTION`
- `ORCHESTRATION-CONTRACT`
- `PROTOCOL-FACTS`
- `PROTOCOL-DECISIONS`
- `PORTS-INDEX`
- `PLAYBOOK-IMPLEMENTERS-GUIDE`
- `PLAYBOOK-WATCHTOWER`
- `ADR-0005`
