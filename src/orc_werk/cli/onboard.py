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
import hashlib
import importlib.resources
import importlib.util
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from orc_werk.cli.config import load_repo_profile
from orc_werk.cli.hyperlink import hyperlink_path
from orc_werk.cli.journal_reading import ORC_JOURNAL_DIR_ENV, resolve_journal_dir
from orc_werk.core.errors import validation_error

# --- Canonical-origin content -----------------------------------------------

_SKILL_PACKAGE = "orc_werk.skills"
_SKILL_RESOURCE = ("orc-ledger", "SKILL.md")
_CHANGELOG_RESOURCE = ("orc-ledger", "CHANGELOG.md")
_VERSION_RE = re.compile(r"^version: ([0-9]+)$", re.MULTILINE)
_CHANGELOG_ENTRY_RE = re.compile(
    r"^## v([0-9]+) -- [0-9]{4}-[0-9]{2}-[0-9]{2}$.*?^content-sha256: ([0-9a-f]{64})$",
    re.MULTILINE | re.DOTALL,
)


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


def packaged_skill_changelog_text() -> str:
    """The hash registry and release notes packaged beside ``SKILL.md``."""
    return (
        importlib.resources.files(_SKILL_PACKAGE)
        .joinpath(*_CHANGELOG_RESOURCE)
        .read_text(encoding="utf-8")
    )


def _skill_version(skill_text: str) -> int:
    match = _VERSION_RE.search(skill_text)
    if match is None:
        raise ValueError("orc-ledger SKILL.md has no integer frontmatter version")
    return int(match.group(1))


def _changelog_registry(changelog_text: str) -> dict[str, int]:
    return {digest: int(version) for version, digest in _CHANGELOG_ENTRY_RE.findall(changelog_text)}


def agents_block_text(
    skill_text: Optional[str] = None,
    *,
    profile: Optional[dict] = None,
    scripted_default: bool = True,
    agents_block: str = "slim",
    ledger: str = "local",
) -> str:
    """Build the adopter's agents block.

    ``full`` mechanically transforms the packaged skill; ``slim`` keeps that
    installed skill as the sole copy of its protocol and only points to it.
    Mode remains derived from the repository profile in both forms.
    """
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
    execution = profile.get("execution") or {} if profile is not None else {}
    assurance = profile.get("assurance") or {} if profile is not None else {}
    adapter_driven = execution.get("adapter", "scripted") == "acp" or assurance.get(
        "adapter", "scripted"
    ) != "scripted"
    if adapter_driven:
        mode = "ADAPTER-DRIVEN MODE"
        action = (
            "orc spawns/drives the seat via the configured adapter; you configure "
            "rather than perform."
        )
    else:
        mode = "SCRIPTED MODE (scripted default)" if scripted_default else "SCRIPTED MODE"
        action = (
            "orc records and advances state; it does not spawn or drive agents; "
            "you the agent do the work and record the settlement/verdict by hand "
            "(do the work by hand)."
        )
    locality = (
        "The ledger is operator-machine-local; resume from the primary checkout root."
        if ledger == "local"
        else "The ledger is committed and shared through the repository."
    )
    skill_pointer = (
        "Before touching the ledger, load the installed `orc-ledger` skill "
        "(`.claude/skills/orc-ledger`) — it is the canonical protocol."
    )
    declaration = (
        "### MODE DECLARATION\n\n"
        f"**{mode}.** {action}\n\n"
        "Dispatch configs default via profile `.orc/profile.json`; no adapter blocks need "
        "to be specified."
    )
    prefix = f"## Delivery ledger (orc)\n\n{declaration}\n\n{locality}"
    if agents_block == "full":
        return f"{prefix}\n\n{body}\n"
    return f"{prefix}\n\n{skill_pointer}\n"


BLOCK_BEGIN = "<!-- BEGIN ORC-LEDGER AGENTS BLOCK (orc onboard, TASK-M3D-001) -->"
BLOCK_END = "<!-- END ORC-LEDGER AGENTS BLOCK -->"


def _wrapped_block(block: str) -> str:
    return f"{BLOCK_BEGIN}\n{block.rstrip(chr(10))}\n{BLOCK_END}\n"


# --- Fixed target-repo paths -------------------------------------------------

GITIGNORE_ENTRY = ".orc/"
_SKILL_REL = Path(".agents") / "skills" / "orc-ledger" / "SKILL.md"
_CHANGELOG_REL = Path(".agents") / "skills" / "orc-ledger" / "CHANGELOG.md"
_CLAUDE_SKILL_LINK_REL = Path(".claude") / "skills" / "orc-ledger"
_CLAUDE_SKILL_LINK_TARGET = Path("..") / ".." / ".agents" / "skills" / "orc-ledger"
DEFAULT_AGENTS_FILE = "AGENTS.md"
_PROFILE_REL = Path(".orc") / "profile.json"
_STARTER_PROFILE = "{}\n"


# --- Step 1: gitignore --------------------------------------------------------


def _step_gitignore(target: Path, *, ledger: str) -> str:
    path = target / ".gitignore"
    if ledger == "committed":
        if not path.exists():
            return "gitignore: committed ledger selected; no `.orc/` entry written"
        existing = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()}
        if GITIGNORE_ENTRY in existing or GITIGNORE_ENTRY.rstrip("/") in existing:
            return (
                "gitignore: WARNING -- committed ledger selected but an existing `.orc/` "
                f"entry remains in {hyperlink_path(path.resolve())}; remove it explicitly to share the ledger"
            )
        return "gitignore: committed ledger selected; no `.orc/` entry written"
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


def _install_skill_file(
    target: Path, *, canonical: str, changelog: str, force: bool
) -> tuple[str, bool]:
    """Install the skill, returning its note and whether CHANGELOG must follow.

    A byte hash recorded in the canonical changelog proves that a differing
    file is an untouched prior release. Only that proof permits an automatic
    replacement; unknown content retains the existing never-clobber behavior.
    """
    path = target / _SKILL_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    new_version = _skill_version(canonical)
    if path.exists() and not path.is_symlink():
        current_bytes = path.read_bytes()
        canonical_bytes = canonical.encode("utf-8")
        if current_bytes == canonical_bytes:
            return f"skill: v{new_version} already installed -- skip", False
        old_hash = hashlib.sha256(current_bytes).hexdigest()
        old_version = _changelog_registry(changelog).get(old_hash)
        if old_version is not None and old_version < new_version:
            path.write_bytes(canonical_bytes)
            return (
                f"skill: upgraded v{old_version} -> v{new_version} "
                "(see .agents/skills/orc-ledger/CHANGELOG.md)",
                True,
            )
        if not force:
            return (
                f"skill: skip -- {hyperlink_path(path.resolve())} exists and differs from the package "
                "source (operator-modified); rerun with --force to overwrite",
                False,
            )
        path.write_bytes(canonical_bytes)
        return f"skill: overwritten (--force) at {hyperlink_path(path.resolve())}", True
    if path.is_symlink() and not path.exists():
        if not force:
            return (
                f"skill: skip -- {hyperlink_path(path)} is a dangling symlink (operator-modified); "
                "rerun with --force to replace it",
                False,
            )
        path.unlink()
    path.write_text(canonical, encoding="utf-8")
    return f"skill: installed at {hyperlink_path(path.resolve())}", True


def _install_skill_changelog(target: Path, *, canonical: str, force: bool) -> str:
    path = target / _CHANGELOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.is_symlink():
        if path.read_text(encoding="utf-8") == canonical:
            return f"skill changelog: already installed at {hyperlink_path(path.resolve())} -- skip"
        if not force:
            return (
                f"skill changelog: skip -- {hyperlink_path(path.resolve())} differs from the package "
                "source (operator-modified); rerun with --force to overwrite"
            )
        path.write_text(canonical, encoding="utf-8")
        return f"skill changelog: overwritten (--force) at {hyperlink_path(path.resolve())}"
    if path.is_symlink() and not path.exists():
        if not force:
            return f"skill changelog: skip -- {hyperlink_path(path)} is a dangling symlink (operator-modified); rerun with --force to replace it"
        path.unlink()
    path.write_text(canonical, encoding="utf-8")
    return f"skill changelog: installed at {hyperlink_path(path.resolve())}"


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
    changelog = packaged_skill_changelog_text()
    skill_note, replace_changelog = _install_skill_file(
        target, canonical=canonical, changelog=changelog, force=force
    )
    changelog_note = _install_skill_changelog(
        target, canonical=changelog, force=force or replace_changelog
    )
    return [skill_note, changelog_note, _install_skill_link(target, force=force)]


# --- Step 4: agents-onboarding block -------------------------------------------


def _step_agents_block(
    target: Path,
    *,
    agents_file: str,
    force: bool,
    profile: Optional[dict],
    scripted_default: bool,
    agents_block: str,
    ledger: str,
) -> str:
    wrapped = _wrapped_block(
        agents_block_text(
            profile=profile,
            scripted_default=scripted_default,
            agents_block=agents_block,
            ledger=ledger,
        )
    )
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

    installed_skill = target / _SKILL_REL
    try:
        installed_version = f"v{_skill_version(installed_skill.read_text(encoding='utf-8'))}"
    except (OSError, UnicodeError, ValueError):
        installed_version = "unknown"
    lines.append(f"  installed orc-ledger skill version: {installed_version}")

    orc_on_path = shutil.which("orc")
    if orc_on_path:
        lines.append(f"  orc console script on PATH: found ({orc_on_path})")
    else:
        lines.append(
            "  orc console script on PATH: absent -- install the package console script; "
            "then run `orc -h` for the local command reference"
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
    target = Path(args.path or ".")
    if args.print_agents_block:
        # Prints only, writes nothing -- derive the declaration from the
        # target profile when present, but perform no scaffold step.
        profile = load_repo_profile(target / ".orc")
        print(
            _wrapped_block(
                agents_block_text(
                    profile=dict(profile) if profile is not None else None,
                    agents_block=args.agents_block,
                    ledger=args.ledger,
                )
            ),
            end="",
        )
        return 0

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

    profile_was_absent = not (target / _PROFILE_REL).exists()

    print(f"onboard: {hyperlink_path(target)}")
    print(f"ledger: {args.ledger} -- " + (
        "operator-machine-local; resume from the primary checkout root"
        if args.ledger == "local"
        else "committed and shared through the repository"
    ))
    print(_step_gitignore(target, ledger=args.ledger))
    print(_step_profile(target, force=args.force))
    profile = load_repo_profile(target / ".orc")
    for line in _step_skill(target, force=args.force):
        print(line)
    print(
        _step_agents_block(
            target,
            agents_file=args.agents_file,
            force=args.force,
            profile=dict(profile) if profile is not None else None,
            scripted_default=profile_was_absent or profile == {},
            agents_block=args.agents_block,
            ledger=args.ledger,
        )
    )
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
    "packaged_skill_changelog_text",
    "packaged_skill_text",
]
