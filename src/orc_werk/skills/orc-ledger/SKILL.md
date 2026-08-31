---
name: orc-ledger
version: 3
description: Onboard to and operate within a repository whose delivery is tracked by an orc ledger (an .orc/ directory of run journals). Use when a session starts work in such a repo, when the user mentions orc runs, the ledger, dispatch, pending runs, settlements, or verdicts, or before recording anything into a run.
---

# Working with the orc delivery ledger

This repository tracks delivery through orc: durable run journals under
`./.orc/` that can be replayed. The ledger — not any document, summary, or
memory — is the ground truth for what work exists, what state it is in, and
what it needs.

Invoke the CLI as `orc`. Run `orc -h` for the local command reference,
`orc config-schema` for dispatch configuration, `orc validate` before using an
edited configuration, `orc record` for validated recording sugar, and `orc
verdict` to inspect assurance results.

## 1. Orient first — always

Run bare `orc`. It prints the live portfolio: every run, per-work state,
attempts, pending flags. **If any doc or your own recollection disagrees with
the journal, the journal wins.**

## 2. Resume, never duplicate

For each non-terminal run, `orc status <run>` prints a `next:` block — the
exact legal next command derived from the delivery state machine. A pending
run means work is in flight or awaiting a recorded outcome. **Never start a
parallel effort for work a run already owns.** When unsure of a run's state,
re-run its dispatch and read the output — re-dispatching the same run is
always safe (it is the resume, poll, and crash-recovery verb all at once).

## 3. Know your seat before recording anything

The seat-discipline requirements come from the external `PLAYBOOK-AGENT-CLI`,
canonical in the orc-werk repository/package; the essentials are
here so a fresh session needs no other file:

- You record **observations only** — never decisions. The kernel decides.
- **One seat per candidate**: either you record the execution settlement +
  candidate (ship seat) OR the assurance verdict (verify seat) — never both
  for the same candidate. No self-assurance, ever.
- **Candidates are externally resolvable identity** — a head sha, a PR
  number, a content hash. Never prose describing what you did.
- **Verifiers derive the candidate identity themselves** (e.g.
  `git rev-parse HEAD`, `gh pr view N --json headRefOid`) and record the
  verdict against the self-derived value. A mismatch with the recorded value
  is the system working: report it, do not reconcile it away. Substantive
  findings ride the verdict entry's `extensions`, as specified by the external
  `PLAYBOOK-AGENT-CLI`, canonical in the orc-werk repository/package.
- Exit codes: 0 all accepted · 1 blocked · 2 error · 3 pending (your seat's
  work may be done at exit 3 — read the output, not just the code).

## 4. Recording mechanics

Prefer `orc record <run-id> --work <work-id> --verdict <accepted|rejected>`
for assurance verdicts: it validates and atomically performs the same
merge-only backing-config update, then prints the resume command without
running it. Hand-editing remains legal; this verb is recording sugar, not a
new journal semantic.

Outcomes are recorded into the run's backing config (the JSON file named in
the run's `next:` affordance), then advanced by re-running the same dispatch
command. Merge-only edits: append your own work's attempt entries; never
touch sibling works' entries or the `plan` key. Concurrent dispatch of the
same run is forbidden — one party re-dispatches at a time. If no adapter
journals your seat, identify your model/tool, session reference, and role in
a small payload under your execution attempt entry's `extensions` key — it
transports losslessly into the settled fact and is visible via `orc
history`/`orc refs` (the external `PLAYBOOK-AGENT-CLI`, canonical in the
orc-werk repository/package, §2, "Executor identity when no adapter records
the seat").

## 5. New work

New work gets a new run: `orc dispatch "<intent>" --config <cfg>`. The
intent text is recorded verbatim in the durable journal — write it for a
reader with no context.

## 6. Depth on demand

- `orc report <run>` — the human story (timeline, dependency tree, verdicts,
  evidence) as a self-contained HTML file.
- `orc history <run>` — the seq-ordered record (paginated; `--limit 0` for
  everything).
- `orc report --index` — the HTML portfolio.
- The raw `.orc/*.jsonl` is portable JSON — `jq` and friends work directly.
