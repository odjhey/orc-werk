---
id: REPORT-2026-09-05-PSTACK-GRADED-VERDICTS
type: report
status: current
authority: informative
description: Assessment of pstack's graded verification verdicts against Orc Werk's assurance contract, with a draft assurance-depth/v1 extension proposal and open core questions.
---

# pstack graded verdicts — assessment and proposal

Assessment scout report (2026-09-05) on the **pstack** Cursor plugin's graded
verification verdicts, requested to see what Orc Werk's ledger should learn
from it. Source: <https://github.com/cursor/plugins/tree/main/pstack>,
specifically `pstack/skills/poteto-mode/playbooks/orchestrate.md`
("Verification") and `pstack/skills/poteto-mode/scripts/orch/store.ts`.

This report is evidence and analysis, not contract. Durable conclusions are
proposed as the draft extension `EXT-ASSURANCE-DEPTH-V1` and as questions for
operator ruling; nothing here changes a current contract.

## 1. What pstack does

pstack's Orchestrate playbook runs multi-agent programs over stacked PRs and
records verification in a TSV ledger, one row per verdict, keyed by
`(PR number, head SHA)`. The verdict enumeration is:

```text
live-ui-verified | unit-test-verified | type-check-only | verifier-blocked | verifier-failed
```

Its governing rules, verbatim from `orchestrate.md`:

> CI green is an input to a verdict, not a verdict. Behavioral work needs
> better than `type-check-only`. `verifier-blocked` is not a pass; respawn
> when the environment heals. `verifier-failed` gets a fix unit, not a
> re-verify. A worker may self-report; a verifier overrides it on the same
> key. A new head SHA voids the row, so re-verify after restack. The ledger
> answers "was this verified", not memory and not the transcript.

Assignment: a worker may self-report; a verifier on a different model family
overrides on the same key (mechanically, an upsert). Evidence is a required
CLI argument. Consumption: the coordinator lands only ledger-verified units,
with `unit-test-verified` or better as the done floor, and must confirm at
close that every landed PR has a verdict for its current head SHA.

## 2. Mapping against Orc Werk

| pstack concept | Orc Werk today | Assessment |
|---|---|---|
| Ledger keyed on `(PR, head SHA)`; new SHA voids the row | Candidate fingerprint on every settlement (`INV-007`), non-transferable (`INV-008`), invalidated on change (`INV-010`), verifier derives identity itself (`SCN-013`) | **Already stronger.** Nothing to import. |
| Worker self-reports, verifier overrides on the same key | Ship seat records `--outcome`; verify seat records `--verdict`; one seat per candidate, no self-assurance (`PLAYBOOK-AGENT-CLI`) | **Already stricter.** Orc forbids what pstack merely overrides. |
| `--evidence` is mandatory | `evidence_refs` optional; `SHOULD` in the playbook | Playbook-level difference only; not a contract gap. |
| `verifier-failed` → new fix unit, not a re-verify | `rejected` → `DEC-RETRY` (new Execution, new candidate) or `DEC-BLOCK` | **Equivalent.** `SCN-002`. |
| `verifier-blocked` → not a pass; re-verify the same unit when the environment heals | `inconclusive` → `DEC-BLOCK` → terminal `BLOCKED` (`STATE-DELIVERY`); `orc record --verdict` does not accept `inconclusive` | **Divergence.** See §4 Q1. |
| `live-ui-verified` / `unit-test-verified` / `type-check-only` as ordered grades with a per-work floor | No analog. `accepted` is `accepted` whether the verifier ran the thing or read the diff | **Gap. Import as an extension.** §3. |
| Verdict currency via `git patch-id` (rebase keeps the verdict if the patch is unchanged) | Ledger: fingerprint equality only, a rebase is a new candidate. Watchtower tooling: `scripts/watch_pr.py` already classifies `REBASED` (verdict carries) vs `STALE-VERDICT` by `git patch-id --stable` | **Already practiced, outside the ledger.** Whether to promote it into a CandidatePort adapter is §4 Q2. |
| Verifier on a different model family from the worker | `executor-identity/v1` records seat model/session; no policy uses it | Policy idea; recordable today with no new contract. |

Two lessons carry over cleanly; one is a contract gap; one is a core question.

## 3. Proposal: `assurance-depth/v1`

**Selection rule check** (`CONTRACT-EXTENSIONS`, `P-010`): evaluation depth is
useful to workflows that run several kinds of verification, but the generic
delivery state machine executes identically without it. It is therefore an
extension, not a core field, and MUST NOT touch the canonical verdict
(`EXT-003`, `EXT-007`).

**Generalization, not import.** pstack's grade names are code-and-UI
specific and its enumeration mixes method with outcome (`…-blocked`,
`…-failed` sit beside `…-verified`). Orc Werk already separates outcome
(canonical verdict) from everything else and already has the independence
discipline from `EXT-REVIEW-FINDINGS-V1` (severity, disposition, confidence
are never collapsed). The proposed extension therefore carries **one
dimension**, method depth, with adapter-generic names:

| pstack | `assurance-depth/v1` | canonical verdict |
|---|---|---|
| `live-ui-verified` | `depth: live` | `accepted` |
| `unit-test-verified` | `depth: test` | `accepted` |
| `type-check-only` | `depth: static` | `accepted` |
| `verifier-failed` | `depth: <whatever method found it>` | `rejected` |
| `verifier-blocked` | *(omitted)* | `inconclusive` |

"Live" means the candidate's real surface, whatever that is for the work: a
CLI, a rendered document, a deployed service. `live > test > static` is a
documented total order so extension-aware policy can state floors
("behavioral work needs `test` or better"; "docs work is complete at
`static`"). The kernel never branches on it.

Draft documents: `docs/extensions/assurance-depth/v1/` (`EXT-ASSURANCE-DEPTH-V1`,
schema, semantics, examples), `SCN-020` (opacity and lossless transport),
and `CONF-EXT-008`. All carry `status: draft`.

### Suggested implementation card (for the watchtower to size and schedule)

If the draft is ratified, the implementation is small and mirrors the
`assurance-context/v1` delivery (PR #160):

1. Promote the four extension docs, `SCN-020`, and `CONF-EXT-008` from `draft` to `current`; register in `docs/extensions/README.md` under registered extensions.
2. `orc record --verdict` gains `--depth {live,test,static}` (and optional `--surface`, `--derivation-ref`), emitting `assurance-depth/v1` on the assurance entry exactly as `--finding` emits `review-findings/v1`.
3. `orc verdict`, `orc show`, and the HTML report render `depth` next to the verdict when present.
4. `tests/scenarios/test_extension_lossless_transport.py` gains an `assurance-depth/v1` case (`SCN-020`); `tests/conformance/test_extension_producer_conformance.py` gains a validator for the `--depth` emission path.
5. `PLAYBOOK-AGENT-CLI` §4 gains a SHOULD item: record the depth you actually reached; never record a depth for work you did not do; a green status badge is `static`.
6. The `orc-ledger` skill's recording section mentions `--depth` in one line.

Zero `src/orc_werk/core` changes. The `CONF-EXT-006` core-ignorance test
already covers the new key generically.

## 4. Open questions for operator ruling (not changed by this proposal)

**Q1 — `inconclusive` is terminal; pstack's `verifier-blocked` is not.** *RULED 2026-09-05: option B, recorded as `ADR-0006` (`STATE-DELIVERY` item 11, `INV-021`, `SCN-021`).*
Today an `inconclusive` verdict blocks the Work (`STATE-DELIVERY`,
`reason: assurance-inconclusive`), and the verify seat's record verb offers
only `accepted|rejected`, so a verifier facing a broken environment has no
honest verb and no re-verify path short of the operator abandoning the
attempt (`DEC-ABANDON-ATTEMPT`, which spends retry budget and demands a new
Execution to produce a candidate that then inherits nothing, because
inheritance covers only `accepted`/`rejected`). pstack's rule — blocked is
not a pass, re-verify the *same* candidate when the environment heals —
suggests an `ASSURING → ASSURING` re-request on `inconclusive` (a
`DEC-REQUEST-ASSURANCE` row, bounded by an assurance-attempt budget analogous
to `INV-019`). That is a state-machine revision with its own scenario, out of
scope here; the observation is that the current terminal treatment penalizes
honesty and quietly pushes verifiers toward recording `rejected` for
environment failures, which then burns the *ship* seat's retry budget for a
defect that was never in the candidate.

**Q2 — Rebase-stable candidate identity.** pstack keeps a verdict across a
rebase when `git patch-id` is unchanged. Orc's watchtower already does the
same thing operationally: `scripts/watch_pr.py` classifies a PR whose head
moved as `REBASED` ("verdict carries") when the stable patch-id is unchanged
and `STALE-VERDICT` otherwise. That classification lives in operator tooling
and is never written into the ledger, whose fingerprint stays exact by design
(`INV-006`, `ADR-0002`) — correct for the core. The open question is only
whether the Git CandidatePort adapter should offer a patch-id-based
`subject_identity` as an *opt-in adapter policy* so the ledger's inheritance
(`SCN-009`) could carry a verdict across a content-identical rebase; that is
an adapter question for `docs/adapters/git/`, recorded here so it is not
re-discovered.

**Q3 — Where a depth floor lives.** A per-Work minimum depth is policy
configuration. `TASK-M2-005` (policy parameterization) is deferred; if it is
revived, "required assurance depth" is a natural first parameter, consumed
by extension-aware application policy after the canonical observation is
recorded — never by the kernel.

## 5. What not to import

- pstack's TSV ledger and CLI. Orc's journal is the stronger design (append-only Facts, replay, Decisions with basis).
- Worker self-report with verifier override. Orc's one-seat-per-candidate rule is deliberately stricter.
- Outcome values inside the depth enumeration. See §3.
- pstack's vocabulary (`live-ui-verified`, "unit", "type-check"). Adapter- and domain-specific; the research lineage document records the source and the generalized names above are what Orc uses.
