"""`orc onboard [--path DIR] [--print-agents-block] [--force] [--agents-file
NAME] [--journal JOURNAL]` (`TASK-M3D-001`, `M3-HARDEN-THE-LOOP` Phase M3d):
mechanically scaffolds an adopting repository -- the hand-work
`docs/product/adoption.md` (`PRODUCT-ADOPTION`) currently documents as a
manual copy ("Copy the `orc-ledger` project skill ... into the adopting
repository"). Five steps, each independently idempotent and each reported
honestly:

1. **gitignore** -- ensure a `.orc/` entry exists in the target repo's
   `.gitignore` (create the file if absent, append the entry if the file
   exists without it, skip-with-note if already present). Append-only:
   never rewrites a line that is already there, so this step alone is
   always safe to re-run without `--force`.
2. **repo-default profile** -- write an empty starter at
   `.orc/profile.json` under the same never-clobber/`--force` discipline.
   This is scaffolding only; it never creates or writes a journal.
3. **skill install** -- copy the orc-ledger skill's content into the
   target repo at `.agents/skills/orc-ledger/SKILL.md`, and link
   `.claude/skills/orc-ledger` to it (`../../.agents/skills/orc-ledger`,
   correctly relative to the symlink's own directory -- the issue #63
   lesson) so Claude Code's project-skill discovery resolves it directly,
   mirroring the convention `PRODUCT-ADOPTION`'s "Onboarding sessions in
   an adopting repository" section already documents. **Canonical origin**
   (the task card's first non-negotiable): the copied content is read from
   THIS installed package (`orc_werk.skills`, via `importlib.resources`),
   never a second copy hand-maintained in this module's own source. In the
   orc-werk repository itself, `src/orc_werk/skills/orc-ledger/SKILL.md`
   is the one real, authored file; `.agents/skills/orc-ledger/SKILL.md` is
   a relative symlink to it (see `src/orc_werk/skills/__init__.py`'s
   docstring for the full chain and why a real file, not a
   packaging-time-only symlink, was chosen for the packaged copy).
4. **agents-onboarding block** -- a copy-pasteable `## Delivery ledger
   (orc)` block for an `AGENTS.md`-style file (default target
   `AGENTS.md`, `--agents-file` to override), wrapped in HTML-comment
   markers so a re-run can detect and compare it. `agents_block_text`
   derives this block from the SAME packaged `SKILL.md` content step 2
   installs -- a mechanical transform (strip YAML frontmatter, drop the
   H1 title, keep everything else verbatim) rather than a second
   hand-maintained copy of the six-rule protocol. `--print-agents-block`
   prints this block to stdout ONLY and performs no other step, writes no
   file -- for pasting into whatever agent-instructions file a repo
   already uses instead of the default `AGENTS.md` target.
5. **install verification** -- honestly reports what resolved: `orc` on
   `$PATH` (`shutil.which`) vs. this interpreter's own ability to import
   `orc_werk` (module form); the journal directory `--journal`/
   `$ORC_JOURNAL_DIR`/`./.orc` (`orc_werk.cli.journal_reading.
   resolve_journal_dir`) would resolve to, anchored at `--path`; and the
   optional `bd` binary's presence (Beads mirror, noted-optional, never
   required). Fabricates nothing: every line names the exact mechanism
   checked and its found/absent outcome.

**Idempotence and the never-clobber rule** (the task card's second
non-negotiable): every step compares what it would write against what is
already there. An exact match is a `skip` note (no write, no diff). A
mismatch against something this command did not create -- an
operator-modified `.gitignore` line is impossible by construction (append-
only, never rewritten), but the skill file, the `.claude/skills` link, and
the agents-block CAN already hold different content -- is `skip-with-note`
by default (never a hard failure; the note names exactly what to do:
rerun with `--force`) unless `--force` is given, which overwrites/replaces
it in place, also reported.

Pure scaffolding: this module never touches a delivery journal, never
imports `orc_werk.app`/`orc_werk.core` beyond the shared canonical-error
helpers, and raises only for genuine usage errors (`--path` missing or not
a directory) -- every raise carries `next` guidance (issue #94).
"""

from __future__ import annotations

import argparse
import importlib.resources
import importlib.util
import os
import shutil
from pathlib import Path
from typing import Optional

from orc_werk.cli.hyperlink import hyperlink_path
from orc_werk.cli.journal_reading import ORC_JOURNAL_DIR_ENV, resolve_journal_dir
from orc_werk.core.errors import validation_error

# --- Canonical-origin content -----------------------------------------------

_SKILL_PACKAGE = "orc_werk.skills"
_SKILL_RESOURCE = ("orc-ledger", "SKILL.md")


def packaged_skill_text() -> str:
    """The orc-ledger skill's canonical content, read from THIS installed
    package -- the one place `onboard` (and `agents_block_text` below) ever
    reads it from. Never re-implemented, never embedded as a Python string
    literal elsewhere in this module (the task card's canonical-origin
    non-negotiable)."""
    return (
        importlib.resources.files(_SKILL_PACKAGE)
        .joinpath(*_SKILL_RESOURCE)
        .read_text(encoding="utf-8")
    )


def agents_block_text(skill_text: Optional[str] = None) -> str:
    """Derive the copy-pasteable `## Delivery ledger (orc)` block from the
    packaged `SKILL.md` content: strip the YAML frontmatter, drop the `#
    Working with the orc delivery ledger` H1 title, and keep every other
    line verbatim (the intro paragraph plus the six numbered sections) --
    already written context-free (`docs/README.md`'s spirit: this text
    names the repo's own ledger convention, not orc-werk-specific
    knowledge). A mechanical transform, not a second hand-authored copy of
    the six-rule protocol -- `tests/scenarios/test_cli_onboard.py`'s
    canonical-origin test re-derives this from the packaged source and
    diffs it against what `onboard` actually wrote/printed, so a fork
    (someone hand-editing the block's text in this module instead of
    `SKILL.md`) fails that test immediately."""
    text = skill_text if skill_text is not None else packaged_skill_text()
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
            lines = lines[end + 1 :]
        except ValueError:
            pass
    while lines and not lines[0].strip():
        lines = lines[1:]
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines = lines[1:]
    body = "\n".join(lines).rstrip("\n")
    return f"## Delivery ledger (orc)\n\n{body}\n"


BLOCK_BEGIN = "<!-- BEGIN ORC-LEDGER AGENTS BLOCK (orc onboard, TASK-M3D-001) -->"
BLOCK_END = "<!-- END ORC-LEDGER AGENTS BLOCK -->"


def _wrapped_block(block: str) -> str:
    return f"{BLOCK_BEGIN}\n{block.rstrip(chr(10))}\n{BLOCK_END}\n"


# --- Fixed target-repo paths -------------------------------------------------

GITIGNORE_ENTRY = ".orc/"
_SKILL_REL = Path(".agents") / "skills" / "orc-ledger" / "SKILL.md"
_CLAUDE_SKILL_LINK_REL = Path(".claude") / "skills" / "orc-ledger"
_CLAUDE_SKILL_LINK_TARGET = Path("..") / ".." / ".agents" / "skills" / "orc-ledger"
DEFAULT_AGENTS_FILE = "AGENTS.md"
_PROFILE_REL = Path(".orc") / "profile.json"
_STARTER_PROFILE = "{}\n"


# --- Step 1: gitignore --------------------------------------------------------


def _step_gitignore(target: Path) -> str:
    path = target / ".gitignore"
    if not path.exists():
        path.write_text(GITIGNORE_ENTRY + "\n", encoding="utf-8")
        return f"gitignore: created {hyperlink_path(path.resolve())} with `{GITIGNORE_ENTRY}` entry"
    text = path.read_text(encoding="utf-8")
    existing = {line.strip() for line in text.splitlines()}
    if GITIGNORE_ENTRY in existing or GITIGNORE_ENTRY.rstrip("/") in existing:
        return f"gitignore: `{GITIGNORE_ENTRY}` already present in {hyperlink_path(path.resolve())} -- skip"
    sep = "" if (not text or text.endswith("\n")) else "\n"
    path.write_text(text + sep + GITIGNORE_ENTRY + "\n", encoding="utf-8")
    return f"gitignore: appended `{GITIGNORE_ENTRY}` entry to {hyperlink_path(path.resolve())}"


# --- Step 2: repo-default profile ---------------------------------------------


def _step_profile(target: Path, *, force: bool) -> str:
    path = target / _PROFILE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == _STARTER_PROFILE:
            return f"profile: starter already present at {hyperlink_path(path.resolve())} -- skip"
        if not force:
            return (
                f"profile: skip -- {hyperlink_path(path.resolve())} exists and differs from the starter "
                "(operator-modified); rerun with --force to overwrite"
            )
        path.write_text(_STARTER_PROFILE, encoding="utf-8")
        return f"profile: overwritten (--force) at {hyperlink_path(path.resolve())}"
    path.write_text(_STARTER_PROFILE, encoding="utf-8")
    return f"profile: created starter at {hyperlink_path(path.resolve())}"


# --- Step 3: skill install -----------------------------------------------------


def _install_skill_file(target: Path, *, canonical: str, force: bool) -> str:
    path = target / _SKILL_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.is_symlink():
        current = path.read_text(encoding="utf-8")
        if current == canonical:
            return f"skill: already installed and matches the package source at {hyperlink_path(path.resolve())} -- skip"
        if not force:
            return (
                f"skill: skip -- {hyperlink_path(path.resolve())} exists and differs from the package "
                "source (operator-modified); rerun with --force to overwrite"
            )
        path.write_text(canonical, encoding="utf-8")
        return f"skill: overwritten (--force) at {hyperlink_path(path.resolve())}"
    if path.is_symlink() and not path.exists():
        # A dangling symlink left over from something else: never silently
        # replace without --force either.
        if not force:
            return (
                f"skill: skip -- {hyperlink_path(path)} is a dangling symlink (operator-modified); "
                "rerun with --force to replace it"
            )
        path.unlink()
    path.write_text(canonical, encoding="utf-8")
    return f"skill: installed at {hyperlink_path(path.resolve())}"


def _install_skill_link(target: Path, *, force: bool) -> str:
    link_path = target / _CLAUDE_SKILL_LINK_REL
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink():
        current_target = Path(os.readlink(link_path))
        if current_target == _CLAUDE_SKILL_LINK_TARGET:
            return f"skill: {hyperlink_path(link_path)} already links to the installed skill -- skip"
        if not force:
            return (
                f"skill: skip -- {hyperlink_path(link_path)} is a symlink to a different target "
                "(operator-modified); rerun with --force to relink"
            )
        link_path.unlink()
        link_path.symlink_to(_CLAUDE_SKILL_LINK_TARGET)
        return f"skill: relinked (--force) {hyperlink_path(link_path)} -> {_CLAUDE_SKILL_LINK_TARGET}"
    if link_path.exists():
        if not force:
            return (
                f"skill: skip -- {hyperlink_path(link_path.resolve())} already exists and is not the "
                "expected symlink (operator-modified); rerun with --force to replace it"
            )
        if link_path.is_dir():
            shutil.rmtree(link_path)
        else:
            link_path.unlink()
        link_path.symlink_to(_CLAUDE_SKILL_LINK_TARGET)
        return f"skill: replaced (--force) {hyperlink_path(link_path)} -> {_CLAUDE_SKILL_LINK_TARGET}"
    link_path.symlink_to(_CLAUDE_SKILL_LINK_TARGET)
    return f"skill: linked {hyperlink_path(link_path)} -> {_CLAUDE_SKILL_LINK_TARGET} (resolvable via .claude/skills)"


def _step_skill(target: Path, *, force: bool) -> list[str]:
    canonical = packaged_skill_text()
    return [
        _install_skill_file(target, canonical=canonical, force=force),
        _install_skill_link(target, force=force),
    ]


# --- Step 4: agents-onboarding block -------------------------------------------


def _step_agents_block(target: Path, *, agents_file: str, force: bool) -> str:
    wrapped = _wrapped_block(agents_block_text())
    path = target / agents_file
    if not path.exists():
        path.write_text(wrapped, encoding="utf-8")
        return f"agents-block: created {hyperlink_path(path.resolve())} with the Delivery ledger block"
    text = path.read_text(encoding="utf-8")
    if BLOCK_BEGIN not in text:
        sep = "" if (not text or text.endswith("\n\n")) else ("\n" if text.endswith("\n") else "\n\n")
        path.write_text(text + sep + wrapped, encoding="utf-8")
        return f"agents-block: appended the Delivery ledger block to {hyperlink_path(path.resolve())}"
    start = text.index(BLOCK_BEGIN)
    end = text.index(BLOCK_END) + len(BLOCK_END)
    current_block = text[start:end] + "\n"
    if current_block == wrapped:
        return f"agents-block: already present and up to date in {hyperlink_path(path.resolve())} -- skip"
    if not force:
        return (
            f"agents-block: skip -- {hyperlink_path(path.resolve())} has a Delivery ledger block that "
            "differs from the canonical content (operator-modified); rerun with --force to replace it"
        )
    new_text = text[:start] + wrapped.rstrip("\n") + text[end:]
    path.write_text(new_text, encoding="utf-8")
    return f"agents-block: replaced (--force) in {hyperlink_path(path.resolve())}"


# --- Step 5: install verification ----------------------------------------------


def _verify(target: Path, *, journal_flag: Optional[str]) -> list[str]:
    lines = ["verification:"]

    orc_on_path = shutil.which("orc")
    if orc_on_path:
        lines.append(f"  orc console script on PATH: found ({orc_on_path})")
    else:
        lines.append(
            "  orc console script on PATH: absent -- module form still works: "
            "PYTHONPATH=<path-to-orc-werk-src> python3 -m orc_werk.cli"
        )

    module_found = importlib.util.find_spec("orc_werk") is not None
    lines.append(
        f"  orc_werk importable as a module in this interpreter: {'yes' if module_found else 'no'}"
    )

    raw_journal_dir = resolve_journal_dir(journal_flag)
    if raw_journal_dir.is_absolute():
        journal_dir = raw_journal_dir.resolve()
    else:
        journal_dir = (target / raw_journal_dir).resolve()
    if journal_flag:
        source = "--journal"
    elif os.environ.get(ORC_JOURNAL_DIR_ENV):
        source = ORC_JOURNAL_DIR_ENV
    else:
        source = "default ./.orc"
    lines.append(f"  journal dir resolves to: {hyperlink_path(journal_dir)} (source: {source})")

    bd_on_path = shutil.which("bd")
    if bd_on_path:
        lines.append(f"  bd (optional Beads mirror): found ({bd_on_path})")
    else:
        lines.append("  bd (optional Beads mirror): absent -- noted optional, never required")

    return lines


# --- CLI entry point -------------------------------------------------------


def cmd_onboard(args: argparse.Namespace) -> int:
    if args.print_agents_block:
        # Prints only, writes nothing (the task card's third
        # non-negotiable) -- every other step (gitignore, skill install,
        # verification) is skipped entirely for this invocation.
        print(_wrapped_block(agents_block_text()), end="")
        return 0

    target = Path(args.path or ".")
    if not target.exists():
        raise validation_error(
            f"--path does not exist: {args.path}",
            path=args.path,
            next_steps=[f"mkdir -p {args.path} first, or pass an existing directory"],
        )
    if not target.is_dir():
        raise validation_error(
            f"--path is not a directory: {args.path}",
            path=args.path,
            next_steps=["pass a directory, not a file"],
        )
    target = target.resolve()

    print(f"onboard: {hyperlink_path(target)}")
    print(_step_gitignore(target))
    print(_step_profile(target, force=args.force))
    for line in _step_skill(target, force=args.force):
        print(line)
    print(_step_agents_block(target, agents_file=args.agents_file, force=args.force))
    for line in _verify(target, journal_flag=args.journal):
        print(line)

    print("next:")
    print(f"  - orc dispatch \"<intent text>\" --config <path-to-dispatch-config.json> --journal {target / '.orc'}")
    print(f"  - orc --journal {target / '.orc'}  # or: cd {target} && orc")
    return 0


__all__ = [
    "BLOCK_BEGIN",
    "BLOCK_END",
    "DEFAULT_AGENTS_FILE",
    "GITIGNORE_ENTRY",
    "agents_block_text",
    "cmd_onboard",
    "packaged_skill_text",
]
