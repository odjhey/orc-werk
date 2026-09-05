# orc-ledger skill changelog

## v5 -- 2026-09-05

- Teach `orc record --verdict inconclusive` (`ADR-0006`, #264): the honest verify-seat verdict when you cannot decide or could not evaluate. It spends the run's assurance budget (`max_assurance_attempts`, `INV-021`), never the ship seat's retry budget -- within budget the kernel re-requests assurance of the same candidate, exhausted the Work blocks with `reason: assurance-inconclusive`.

content-sha256: 68509c3d11a09cfb6e40214820e55b354aa5ec06958a1538ea2852726c8a473c

## v4 -- 2026-09-02

- Teach `orc record --outcome completed|failed` (#223) as the ship-seat recording sugar, parallel to the existing `--verdict` verify-seat sentence: validates, appends the attempt entry atomically (merge-only), auto-emits `executor-identity/v1` with the seat's role, prints the resume command without running it.
- Demote hand-editing to the explicit fallback for when no verb fits; the manual executor-identity payload is now framed as the no-verb fallback, since the record verbs emit it automatically.

content-sha256: 58e3c509883be7822e0f2ace37f09c507ae8a2276fdeed0b1836ef215a77047d

## v3 -- 2026-08-31

- Prefer `orc record` for validated assurance-verdict recording while retaining hand-editing as legal merge-only config recording.
- Include `orc record` in the command orientation for discoverability.

content-sha256: 9da2c4a403d36146fdf90d556cb1ad6be86da3780bab9af616957fb805977943

## v2 -- 2026-08-30

- Fix #166 by keeping the installed skill as the canonical protocol behind the new slim default agents block, avoiding duplicated instructions.
- Fix #167 by making adopter guidance self-contained, naming local CLI references, marking the orc-werk playbook as external, and using plainer wording.

content-sha256: 9f84d8160cf8de4069b251af80a3c8d5237fdb9dc8fc61d756c879ca08c860dd

## v1 -- 2026-08-30

- Initial versioned release: the six-rule ledger onboarding skill (orient/resume/seat/record/dispatch/depth) as shipped through M4.

content-sha256: 7afc14a36e5c027a22c750c0b4eb54a319d3b9724aa5450527f9d1b81d0bdad7
