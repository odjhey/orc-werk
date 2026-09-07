"""Packaged `.omp/` scaffold templates shipped with the `orc_werk`
distribution (`TASK-M5-007`, `orc onboard --omp`).

This subpackage exists for the same reason `orc_werk.skills` does: it holds
non-code resource files that `orc onboard` copies into an adopting
repository, so the installed package -- not a second, hand-maintained copy
embedded in `orc_werk.cli.onboard`'s own Python source -- is the one
canonical origin the scaffold step reads from.

**Unlike** the skill's chain, this repository's own `.omp/agents/
{scout,ship,verify}.md`, `.omp/config.yml`, and `.omp/RULES.md` are NOT
symlinks back to the files in this subpackage. Those five files are
orc-werk's OWN live seat definitions, ratified by `ADR-0007` and owned by
`TASK-M5-004`/`TASK-M5-005`; they are edited directly as this repository's
delivery seats evolve (for example the `V7` verify-model reorder recorded
in `docs/delivery/seat-reliability.md`). Wiring a real symlink chain there
would mean every future operator edit to orc-werk's own seat files
silently becomes what the next package release scaffolds into every
adopting repo -- exactly the coupling the skill's chain relies on being
safe for the harness-independent `orc-ledger` protocol text, but wrong
here: `.omp/agents/ship.md`'s and `.omp/agents/verify.md`'s `model:`
frontmatter pins orc-werk-account-specific model families (`ADR-0007`'s
`V7` ruling), which must not silently drift onto an adopter who has no
reason to run the same accounts.

So the templates below are a second, DELIBERATELY independent, authored
copy of the pilot's agent *shape* (frontmatter fields, tool boundaries,
protocol steps) -- not a byte-for-byte mirror of whatever this repository's
own `.omp/agents/*.md` currently pin. Each template's `model:` field
carries orc-werk's own pilot default (per `TASK-M5-007`'s card: templating
per-repo model choices is out of scope, so the default ships as-is, same
as the skill's own operator-modification model) plus a leading frontmatter
comment telling the adopter to pick models available in their own account
and keep `ship`/`verify` on different model families before first use --
so a fresh adopter is told, not silently left to discover a spawn failure.
"""

from __future__ import annotations
