"""Packaged onboarding resources shipped with the `orc_werk` distribution
(TASK-M3D-001, `orc onboard`).

This subpackage exists to hold non-code resource files that `orc onboard`
copies into an adopting repository -- the orc-ledger skill content
(`skills/orc-ledger/SKILL.md`) -- so the installed package is the single
canonical origin `onboard` reads from (CLAUDE.md #9/#10, the task card's
first non-negotiable: never a second, hand-maintained copy of the six-rule
protocol embedded in Python source).

`skills/orc-ledger/SKILL.md` is a real file living in this package tree
(required so it packages reliably into an sdist/wheel via ordinary
`package-data`, without depending on a build backend's symlink-following
behavior); the repository's own `.agents/skills/orc-ledger/SKILL.md` is a
relative symlink pointing back at this exact file (`../../../src/orc_werk/
skills/orc-ledger/SKILL.md`, correctly resolving from the symlink's own
directory -- the issue #63 lesson), so there really is exactly one
authored copy on disk; `.claude/skills -> ../.agents/skills` (issue #63's
own fix) completes the chain Claude Code's own skill discovery already
depends on. `tests/scenarios/test_cli_onboard.py`'s canonical-origin test
enforces this by reading through the full chain and comparing bytes
against `importlib.resources`, so a fork would fail CI immediately.
"""

from __future__ import annotations
