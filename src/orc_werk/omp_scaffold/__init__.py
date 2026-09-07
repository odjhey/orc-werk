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

So the templates below are an authored copy of the live seats' *shape*
(frontmatter fields, tool boundaries, protocol steps), generalized in a
small, enumerated set of places: account-specific `model:` pins get an
adopter-facing disclaimer comment, and orc-werk-repo-specific text (the
`master` branch name, `scripts/check.sh`'s path, this repo's own
incident notes) is reworded to something portable to an unknown adopter.

**The invariant: every other byte matches, and drift is mechanically
caught.** This is not a fork free to diverge --
`tests/scenarios/test_cli_onboard.py`'s `PackagedScaffoldDriftTest` diffs
each file here against its live `.omp/` counterpart and fails the build on
any difference that is not one of the substitutions enumerated in that
test's `_ADOPTER_SUBSTITUTIONS` table. A protocol or safety edit to a live
`.omp/agents/*.md` seat (tool boundaries, recording steps, `RULES.md`'s
invariants) that is not also propagated here breaks that test, naming the
file and the substitution that no longer matches -- the fix is to update
the template to match, or, if the new difference really is an intended
adopter-facing generalization, to add it to the allowlist.
"""

from __future__ import annotations
