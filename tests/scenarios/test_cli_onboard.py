"""`orc onboard` (`TASK-M3D-001`): tests for `orc_werk.cli.onboard`.

Mixed shape, matching `test_cli_show.py`/`test_cli_refs.py`'s precedent:
in-process unit coverage of the pure content-derivation helpers
(`packaged_skill_text`, `agents_block_text`) and the scaffold steps
(`cmd_onboard` called directly against a fresh `tempfile.TemporaryDirectory`
-- never this repo's own live files), plus a few subprocess-driven CLI
invocations for the install-verification honesty checks, where controlling
`$PATH` precisely (found vs. absent `orc`/`bd`) is the whole point of the
test and only a real subprocess environment can do that cleanly.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orc_werk.cli.onboard import (
    BLOCK_BEGIN,
    BLOCK_END,
    GITIGNORE_ENTRY,
    OMP_AGENT_NAMES,
    agents_block_text,
    cmd_onboard,
    omp_scaffold_agent_text,
    omp_scaffold_config_text,
    omp_scaffold_rules_text,
    packaged_skill_changelog_text,
    packaged_skill_text,
)
from orc_werk.core.errors import CoreError

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _packaged_skill_version() -> str:
    """The version the packaged skill declares — derived, not pinned, so a
    skill bump does not require editing these onboard assertions in lockstep."""
    for line in packaged_skill_text().splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("no version line in packaged skill frontmatter")


def _frontmatter_model(text: str) -> str:
    """The `model:` field's raw value out of an OMP agent template's
    frontmatter fence."""
    lines = text.splitlines()
    assert lines[0].strip() == "---"
    end = lines.index("---", 1)
    for line in lines[1:end]:
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError("no model: field in frontmatter")


def _model_families(model_field: str) -> list[str]:
    """Each comma-separated resolution-preference entry's model family --
    the segment before the first `/` (e.g. "anthropic" out of
    "anthropic/claude-sonnet-5:medium")."""
    return [entry.strip().split("/", 1)[0] for entry in model_field.split(",")]


def _run_cli(cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {"PYTHONPATH": str(SRC)}
    if env:
        full_env.update(env)
    full_env.setdefault("PATH", "/usr/bin:/bin")
    return subprocess.run(
        [sys.executable, "-m", "orc_werk.cli", *args],
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _namespace(**kwargs) -> argparse.Namespace:
    defaults = dict(
        path=".", print_agents_block=False, force=False, agents_file="AGENTS.md",
        journal=None, agents_block="slim", ledger="local", omp=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _onboard(**kwargs) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exit_code = cmd_onboard(_namespace(**kwargs))
    return exit_code, buf.getvalue()


# ---------------------------------------------------------------------------
# Canonical-origin property: the packaged skill content is the ONE source
# both the repo's own SKILL.md (via the symlink chain) and the
# agents-onboarding block are derived from -- never a second, hand-
# maintained copy of the six-rule protocol (the task card's first
# non-negotiable). These tests would fail if someone forked the content.
# ---------------------------------------------------------------------------


class CanonicalOriginTest(unittest.TestCase):
    def test_packaged_skill_text_matches_the_repos_own_symlink_chain(self):
        # .claude/skills/orc-ledger/SKILL.md is the exact path Claude
        # Code's own project-skill discovery reads (.claude/skills ->
        # ../.agents/skills, issue #63's fix; .agents/skills/orc-ledger/
        # SKILL.md -> ../../../src/orc_werk/skills/orc-ledger/SKILL.md).
        # It must read the identical bytes `importlib.resources` reads from
        # the installed package -- there is exactly one authored file.
        via_claude_skills = (REPO_ROOT / ".claude" / "skills" / "orc-ledger" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(via_claude_skills, packaged_skill_text())

    def test_agents_skills_symlink_target_resolves_from_its_own_directory(self):
        # The issue #63 lesson, pinned as a regression: a relative symlink
        # target resolves from the SYMLINK's own directory, not the
        # process cwd or the ultimate target's directory.
        link = REPO_ROOT / ".agents" / "skills" / "orc-ledger" / "SKILL.md"
        self.assertTrue(link.is_symlink())
        resolved = link.resolve()
        self.assertEqual(resolved, (REPO_ROOT / "src" / "orc_werk" / "skills" / "orc-ledger" / "SKILL.md").resolve())

    def test_packaged_skill_frontmatter_is_strict_parse_safe(self):
        # The packaged SKILL.md is loaded by adopters' agents, some behind
        # STRICT YAML parsers (e.g. Pi's). A colon-space (": ") in an
        # unquoted frontmatter value is read as a nested mapping, so the
        # skill is *silently skipped* during discovery -- uninstallable,
        # unlisted, no error (the exact failure mode mattpocock/skills hit
        # and fixed in their fix-yaml-frontmatter-colons changeset; the
        # sharper lesson is that the failure is a silent skip, so assert
        # validity, not just lint). This backs the skill-description
        # authoring guard (PLAYBOOK-WATCHTOWER, Conventions) with an
        # executable check: a "---"-fenced flat block with name +
        # description keys and no unquoted colon-space in any value.
        # stdlib-only (PyYAML is not a dependency).
        lines = packaged_skill_text().splitlines()
        self.assertEqual(lines[0].strip(), "---", "SKILL.md must open with a YAML frontmatter fence")
        end = lines.index("---", 1)
        keys = {}
        for line in lines[1:end]:
            self.assertRegex(line, r"^[a-z][a-z0-9_-]*: ", f"non key:value frontmatter line: {line!r}")
            key, _, value = line.partition(": ")
            keys[key] = value
            if not (value.startswith("'") or value.startswith('"')):
                self.assertNotIn(
                    ": ", value,
                    f"unquoted colon-space in a frontmatter value silently breaks strict YAML "
                    f"discovery -- quote the value or rephrase: {line!r}",
                )
        self.assertEqual(keys.get("name"), "orc-ledger", "frontmatter must carry name: orc-ledger")
        self.assertIn("description", keys, "frontmatter must carry a description (the routing surface)")

    def test_agents_block_derived_from_packaged_skill_text(self):
        skill_text = packaged_skill_text()
        block = agents_block_text(skill_text, agents_block="full")
        self.assertTrue(block.startswith("## Delivery ledger (orc)"))
        for section in (
            "1. Orient first",
            "2. Resume, never duplicate",
            "3. Know your seat",
            "4. Recording mechanics",
            "5. New work",
            "6. Depth on demand",
        ):
            self.assertIn(section, block)
        # the YAML frontmatter and the H1 title are gone
        self.assertNotIn("name: orc-ledger", block)
        self.assertNotIn(f"version: {_packaged_skill_version()}", block)
        self.assertNotIn("# Working with the orc delivery ledger", block)
        # but the ledger's own intro paragraph (context-free content) survives
        self.assertIn("This repository tracks delivery through orc", block)

    def test_agents_block_is_a_live_derivation_not_a_frozen_copy(self):
        # A caller-supplied skill_text that diverges from the packaged one
        # produces a divergent block -- proves `agents_block_text` actually
        # transforms its input rather than returning a string literal that
        # could silently drift from SKILL.md (a fork would fail this).
        forked = packaged_skill_text().replace("Orient first", "FORKED SECTION TITLE")
        self.assertIn("FORKED SECTION TITLE", agents_block_text(forked, agents_block="full"))
        self.assertNotIn("FORKED SECTION TITLE", agents_block_text(agents_block="full"))


# ---------------------------------------------------------------------------
# Scaffold behavior: fresh install, idempotent re-run, operator-modified
# not clobbered without --force, --print-agents-block writes nothing.
# ---------------------------------------------------------------------------


class OnboardScaffoldTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = Path(self._tmp.name)

    def test_first_run_installs_every_step(self):
        exit_code, output = _onboard(path=str(self.target))
        self.assertEqual(exit_code, 0)

        gitignore = (self.target / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(GITIGNORE_ENTRY, gitignore.splitlines())
        self.assertEqual((self.target / ".orc" / "profile.json").read_text(encoding="utf-8"), "{}\n")

        skill_path = self.target / ".agents" / "skills" / "orc-ledger" / "SKILL.md"
        self.assertEqual(skill_path.read_text(encoding="utf-8"), packaged_skill_text())
        changelog_path = self.target / ".agents" / "skills" / "orc-ledger" / "CHANGELOG.md"
        self.assertEqual(changelog_path.read_text(encoding="utf-8"), packaged_skill_changelog_text())

        # skill installed and RESOLVABLE: readable at the .claude/skills
        # discovery path a fresh Claude Code session would use.
        link_path = self.target / ".claude" / "skills" / "orc-ledger"
        self.assertTrue(link_path.is_symlink())
        self.assertEqual((link_path / "SKILL.md").read_text(encoding="utf-8"), packaged_skill_text())

        agents_md = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(BLOCK_BEGIN, agents_md)
        self.assertIn(BLOCK_END, agents_md)
        self.assertIn("## Delivery ledger (orc)", agents_md)

        self.assertIn("gitignore: created", output)
        self.assertIn("profile: created starter", output)
        self.assertIn("skill: installed", output)
        self.assertIn("skill: linked", output)
        self.assertIn("agents-block: created", output)
        self.assertIn("verification:", output)
        self.assertIn(f"installed orc-ledger skill version: v{_packaged_skill_version()}", output)
        self.assertIn("next:", output)

    def test_scripted_profile_declares_work_doer_mode_and_retires_preamble(self):
        profile = self.target / ".orc" / "profile.json"
        profile.parent.mkdir()
        profile.write_text(
            json.dumps({"execution": {"adapter": "scripted"}, "assurance": {"adapter": "scripted"}}),
            encoding="utf-8",
        )
        _onboard(path=str(self.target))
        block = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("SCRIPTED MODE", block)
        self.assertIn("do the work by hand", block)
        self.assertIn("configs default via profile `.orc/profile.json`", block.lower())
        self.assertIn("load the installed `orc-ledger` skill", block)

    def test_real_assurance_profile_declares_adapter_driven_mode(self):
        profile = self.target / ".orc" / "profile.json"
        profile.parent.mkdir()
        profile.write_text(
            json.dumps(
                {
                    "candidate": {"adapter": "git", "repo_path": str(self.target)},
                    "assurance": {
                        "adapter": "command",
                        "script": "scripts/assure.sh",
                        "cwd": str(self.target),
                    },
                }
            ),
            encoding="utf-8",
        )
        _onboard(path=str(self.target))
        block = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("ADAPTER-DRIVEN MODE", block)
        self.assertIn("you configure rather than perform", block)
        self.assertIn("load the installed `orc-ledger` skill", block)

    def test_absent_profile_declares_scripted_default_mode(self):
        _onboard(path=str(self.target))
        block = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("SCRIPTED MODE (scripted default)", block)
        self.assertIn("load the installed `orc-ledger` skill", block)

    def test_default_agents_block_is_slim_and_names_locality_and_skill(self):
        _, output = _onboard(path=str(self.target))
        block = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("MODE DECLARATION", block)
        self.assertIn("operator-machine-local", block)
        self.assertIn("load the installed `orc-ledger` skill", block)
        self.assertNotIn("## 1. Orient first", block)
        self.assertIn("ledger: local", output)

    def test_full_agents_block_mechanically_inlines_the_skill_protocol(self):
        _onboard(path=str(self.target), agents_block="full")
        block = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## 1. Orient first", block)
        self.assertIn("## 6. Depth on demand", block)
        transformed = agents_block_text(
            packaged_skill_text(), agents_block="full", ledger="local"
        )
        self.assertIn(transformed, block)

    def test_committed_ledger_writes_no_ignore_entry_and_reports_shared_placement(self):
        _, output = _onboard(path=str(self.target), ledger="committed")
        self.assertFalse((self.target / ".gitignore").exists())
        block = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("ledger is committed and shared", block)
        self.assertIn("ledger: committed -- committed and shared", output)
        self.assertIn("no `.orc/` entry written", output)

    def test_committed_ledger_warns_without_removing_existing_ignore(self):
        (self.target / ".gitignore").write_text(".orc/\n", encoding="utf-8")
        _, output = _onboard(path=str(self.target), ledger="committed")
        self.assertEqual((self.target / ".gitignore").read_text(encoding="utf-8"), ".orc/\n")
        self.assertIn("WARNING", output)
        self.assertIn("remove it explicitly", output)

    def test_all_adopter_emitted_text_has_no_unresolved_or_unmarked_references(self):
        _, output = _onboard(path=str(self.target), agents_block="full")
        emitted = "\n".join(
            (
                output,
                (self.target / "AGENTS.md").read_text(encoding="utf-8"),
                (self.target / ".agents/skills/orc-ledger/SKILL.md").read_text(encoding="utf-8"),
            )
        )
        self.assertNotRegex(emitted, r"(?<![A-Za-z0-9_.-])docs/[^\s`)]+\.md")
        for line in emitted.splitlines():
            if "PLAYBOOK-" in line:
                self.assertRegex(
                    line.lower(), r"external|canonical in the orc-werk",
                    f"stable ID must be explicitly external in adopter output: {line}",
                )

    def test_rerun_is_idempotent_no_dupes_skip_notes(self):
        _onboard(path=str(self.target))
        gitignore_before = (self.target / ".gitignore").read_text(encoding="utf-8")
        agents_before = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        skill_before = (self.target / ".agents" / "skills" / "orc-ledger" / "SKILL.md").read_text(encoding="utf-8")

        exit_code, output = _onboard(path=str(self.target))
        self.assertEqual(exit_code, 0)
        self.assertEqual((self.target / ".gitignore").read_text(encoding="utf-8"), gitignore_before)
        self.assertEqual((self.target / "AGENTS.md").read_text(encoding="utf-8"), agents_before)
        self.assertEqual(
            (self.target / ".agents" / "skills" / "orc-ledger" / "SKILL.md").read_text(encoding="utf-8"),
            skill_before,
        )
        self.assertEqual(gitignore_before.splitlines().count(GITIGNORE_ENTRY), 1)
        self.assertEqual(agents_before.count(BLOCK_BEGIN), 1)
        self.assertIn("-- skip", output)
        self.assertIn("already present", output)
        self.assertIn(f"skill: v{_packaged_skill_version()} already installed -- skip", output)
        self.assertIn("skill changelog: already installed", output)
        self.assertIn("already links to the installed skill", output)
        self.assertIn("already present and up to date", output)

    def test_operator_modified_profile_is_skipped_then_replaced_with_force(self):
        _onboard(path=str(self.target))
        profile = self.target / ".orc" / "profile.json"
        profile.write_text('{"max_attempts": 7}\n', encoding="utf-8")
        _, output = _onboard(path=str(self.target))
        self.assertEqual(profile.read_text(encoding="utf-8"), '{"max_attempts": 7}\n')
        self.assertIn("profile: skip", output)
        _, output = _onboard(path=str(self.target), force=True)
        self.assertEqual(profile.read_text(encoding="utf-8"), "{}\n")
        self.assertIn("profile: overwritten (--force)", output)

    def test_agents_block_mode_mismatch_is_named_without_force(self):
        _onboard(path=str(self.target), agents_block="slim")
        agents_path = self.target / "AGENTS.md"
        slim = agents_path.read_text(encoding="utf-8")

        exit_code, output = _onboard(path=str(self.target), agents_block="full")

        self.assertEqual(exit_code, 0)
        self.assertEqual(agents_path.read_text(encoding="utf-8"), slim, "must not replace without --force")
        self.assertIn("mode mismatch: requested full", output)
        self.assertIn("canonical slim block", output)
        self.assertNotIn("operator-modified", output)
        self.assertIn("--agents-block full --force", output)

    def test_operator_modified_agents_block_is_skipped_then_replaced_with_force(self):
        _onboard(path=str(self.target))
        agents_path = self.target / "AGENTS.md"
        original = agents_path.read_text(encoding="utf-8")
        modified = original.replace("Before touching the ledger", "OPERATOR EDITED THIS LINE")
        agents_path.write_text(modified, encoding="utf-8")

        exit_code, output = _onboard(path=str(self.target))
        self.assertEqual(exit_code, 0)
        self.assertEqual(agents_path.read_text(encoding="utf-8"), modified, "must not clobber without --force")
        self.assertIn("operator-modified", output)
        self.assertIn("--force", output)

        exit_code, output = _onboard(path=str(self.target), force=True)
        self.assertEqual(exit_code, 0)
        replaced = agents_path.read_text(encoding="utf-8")
        self.assertNotEqual(replaced, modified)
        self.assertIn("Before touching the ledger", replaced)
        self.assertIn("replaced (--force)", output)

    def test_stale_known_skill_is_upgraded_without_force(self):
        old_skill = "---\nname: orc-ledger\nversion: 1\ndescription: old\n---\n\n# Old\n"
        new_skill = old_skill.replace("version: 1", "version: 2").replace("# Old", "# New")
        old_hash = hashlib.sha256(old_skill.encode("utf-8")).hexdigest()
        new_hash = hashlib.sha256(new_skill.encode("utf-8")).hexdigest()
        changelog = (
            f"## v2 -- 2026-08-30\n- Changed for a reason.\ncontent-sha256: {new_hash}\n\n"
            f"## v1 -- 2026-08-29\n- Initial.\ncontent-sha256: {old_hash}\n"
        )
        skill_path = self.target / ".agents" / "skills" / "orc-ledger" / "SKILL.md"
        skill_path.parent.mkdir(parents=True)
        skill_path.write_text(old_skill, encoding="utf-8")
        changelog_path = skill_path.parent / "CHANGELOG.md"
        old_changelog = "previous packaged changelog\n"
        changelog_path.write_text(old_changelog, encoding="utf-8")
        # Patch the exact globals used by the imported cmd_onboard function;
        # another scenario module may reload the CLI module during a full run.
        with mock.patch.dict(
            cmd_onboard.__globals__,
            {
                "packaged_skill_text": lambda: new_skill,
                "packaged_skill_changelog_text": lambda: changelog,
            },
        ):
            exit_code, output = _onboard(path=str(self.target))
        self.assertEqual(exit_code, 0)
        self.assertEqual(skill_path.read_text(encoding="utf-8"), new_skill)
        self.assertEqual(changelog_path.read_text(encoding="utf-8"), changelog)
        self.assertNotEqual(changelog_path.read_text(encoding="utf-8"), old_changelog)
        self.assertIn("skill: upgraded v1 -> v2 (see .agents/skills/orc-ledger/CHANGELOG.md)", output)
        self.assertIn("skill changelog: refreshed for skill upgrade v1 -> v2", output)
        changelog_note = next(line for line in output.splitlines() if "skill changelog:" in line)
        self.assertNotIn("--force", changelog_note)

    def test_operator_modified_skill_file_is_skipped_then_replaced_with_force(self):
        _onboard(path=str(self.target))
        skill_path = self.target / ".agents" / "skills" / "orc-ledger" / "SKILL.md"
        skill_path.write_text("OPERATOR EDITED SKILL CONTENT", encoding="utf-8")

        exit_code, output = _onboard(path=str(self.target))
        self.assertEqual(exit_code, 0)
        self.assertEqual(skill_path.read_text(encoding="utf-8"), "OPERATOR EDITED SKILL CONTENT")
        self.assertIn("operator-modified", output)

        exit_code, output = _onboard(path=str(self.target), force=True)
        self.assertEqual(exit_code, 0)
        self.assertEqual(skill_path.read_text(encoding="utf-8"), packaged_skill_text())
        self.assertIn("overwritten (--force)", output)

    def test_print_agents_block_prints_and_writes_nothing(self):
        exit_code, output = _onboard(path=str(self.target), print_agents_block=True)
        self.assertEqual(exit_code, 0)
        self.assertIn(BLOCK_BEGIN, output)
        self.assertIn(BLOCK_END, output)
        self.assertIn("## Delivery ledger (orc)", output)
        self.assertEqual(list(self.target.iterdir()), [], "print_agents_block must write nothing")

    def test_custom_agents_file(self):
        _onboard(path=str(self.target), agents_file="CLAUDE.md")
        self.assertTrue((self.target / "CLAUDE.md").exists())
        self.assertFalse((self.target / "AGENTS.md").exists())

    def test_gitignore_appends_without_duplicating_existing_content(self):
        (self.target / ".gitignore").write_text("node_modules/", encoding="utf-8")  # no trailing newline
        _onboard(path=str(self.target))
        text = (self.target / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(text, f"node_modules/\n{GITIGNORE_ENTRY}\n")

    def test_gitignore_recognizes_entry_without_trailing_slash(self):
        (self.target / ".gitignore").write_text(".orc\n", encoding="utf-8")
        exit_code, output = _onboard(path=str(self.target))
        text = (self.target / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(text, ".orc\n")
        self.assertIn("already present", output)

    def test_path_missing_is_canonical_validation_error_with_next(self):
        missing = self.target / "does-not-exist"
        with self.assertRaises(CoreError) as ctx:
            cmd_onboard(_namespace(path=str(missing)))
        error = ctx.exception.to_canonical()
        self.assertEqual(error["error"], "ERR-VALIDATION")
        self.assertTrue(error.get("next"))

    def test_path_is_a_file_is_canonical_validation_error(self):
        not_a_dir = self.target / "a-file"
        not_a_dir.write_text("x", encoding="utf-8")
        with self.assertRaises(CoreError) as ctx:
            cmd_onboard(_namespace(path=str(not_a_dir)))
        self.assertEqual(ctx.exception.to_canonical()["error"], "ERR-VALIDATION")


# ---------------------------------------------------------------------------
# OMP seat scaffold (`TASK-M5-007`, `ADR-0007`): --omp/existing .omp/ trigger,
# all five files installed, idempotent re-run, operator-modified preserved
# unless --force, absent trigger leaves today's onboarding unchanged.
# ---------------------------------------------------------------------------


class OmpScaffoldTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = Path(self._tmp.name)

    def test_trigger_absent_installs_nothing_and_leaves_output_unchanged(self):
        exit_code, output = _onboard(path=str(self.target))
        self.assertEqual(exit_code, 0)
        self.assertFalse((self.target / ".omp").exists())
        self.assertNotIn("omp:", output)
        self.assertNotIn("omp agents/", output)

    def test_omp_flag_installs_all_five_files(self):
        exit_code, output = _onboard(path=str(self.target), omp=True)
        self.assertEqual(exit_code, 0)
        self.assertIn("omp: --omp requested", output)
        for name in OMP_AGENT_NAMES:
            path = self.target / ".omp" / "agents" / f"{name}.md"
            self.assertEqual(path.read_text(encoding="utf-8"), omp_scaffold_agent_text(name))
            self.assertIn(f"omp agents/{name}.md: installed", output)
        self.assertEqual(
            (self.target / ".omp" / "config.yml").read_text(encoding="utf-8"), omp_scaffold_config_text()
        )
        self.assertEqual(
            (self.target / ".omp" / "RULES.md").read_text(encoding="utf-8"), omp_scaffold_rules_text()
        )
        self.assertIn("omp config.yml: installed", output)
        self.assertIn("omp RULES.md: installed", output)

    def test_existing_omp_directory_triggers_scaffold_without_the_flag(self):
        (self.target / ".omp").mkdir()
        exit_code, output = _onboard(path=str(self.target))
        self.assertEqual(exit_code, 0)
        self.assertIn("omp: existing", output)
        self.assertIn("detected", output)
        for name in OMP_AGENT_NAMES:
            self.assertTrue((self.target / ".omp" / "agents" / f"{name}.md").exists())

    def test_rerun_is_idempotent_no_dupes_skip_notes(self):
        _onboard(path=str(self.target), omp=True)
        before = {
            name: (self.target / ".omp" / "agents" / f"{name}.md").read_text(encoding="utf-8")
            for name in OMP_AGENT_NAMES
        }
        exit_code, output = _onboard(path=str(self.target), omp=True)
        self.assertEqual(exit_code, 0)
        for name in OMP_AGENT_NAMES:
            self.assertEqual(
                (self.target / ".omp" / "agents" / f"{name}.md").read_text(encoding="utf-8"), before[name]
            )
            self.assertIn(f"omp agents/{name}.md: already installed -- skip", output)
        self.assertIn("omp config.yml: already installed -- skip", output)
        self.assertIn("omp RULES.md: already installed -- skip", output)

    def test_operator_modified_file_is_skipped_then_replaced_with_force(self):
        _onboard(path=str(self.target), omp=True)
        ship_path = self.target / ".omp" / "agents" / "ship.md"
        ship_path.write_text("OPERATOR EDITED SHIP SEAT", encoding="utf-8")

        exit_code, output = _onboard(path=str(self.target), omp=True)
        self.assertEqual(exit_code, 0)
        self.assertEqual(ship_path.read_text(encoding="utf-8"), "OPERATOR EDITED SHIP SEAT")
        self.assertIn("operator-modified", output)
        self.assertIn("--force", output)
        # every OTHER file stays untouched by the one conflict
        for name in ("scout", "verify"):
            self.assertEqual(
                (self.target / ".omp" / "agents" / f"{name}.md").read_text(encoding="utf-8"),
                omp_scaffold_agent_text(name),
            )

        exit_code, output = _onboard(path=str(self.target), omp=True, force=True)
        self.assertEqual(exit_code, 0)
        self.assertEqual(ship_path.read_text(encoding="utf-8"), omp_scaffold_agent_text("ship"))
        self.assertIn("omp agents/ship.md: replaced (--force)", output)

    def test_ship_and_verify_scaffold_defaults_are_different_model_families(self):
        # ADR-0007's V7 ruling: verify must run model families entirely
        # disjoint from ship's -- a model-diversity risk control against
        # self-review-by-construction. Pinned on the actual frontmatter
        # `model:` field, comparing EVERY resolution-preference entry on
        # each side (not just ship's first): a future edit that adds a
        # second ship preference overlapping any verify family must fail
        # this just as surely as collapsing to a single same-family pin.
        ship_families = set(_model_families(_frontmatter_model(omp_scaffold_agent_text("ship"))))
        verify_families = set(_model_families(_frontmatter_model(omp_scaffold_agent_text("verify"))))
        overlap = ship_families & verify_families
        self.assertFalse(
            overlap,
            f"ship's model families {sorted(ship_families)} and verify's "
            f"{sorted(verify_families)} must be disjoint per ADR-0007's V7 ruling "
            f"(overlap: {sorted(overlap)})",
        )


# ---------------------------------------------------------------------------
# Packaged-scaffold drift (TASK-M5-007 attempt 2): the five packaged
# resources under src/orc_werk/omp_scaffold/ are an authored copy of this
# repository's own live .omp/ seat definitions (see omp_scaffold/__init__.py's
# docstring), not a symlink -- so every difference from the live seat must be
# either one of the enumerated adopter-facing substitutions below or drift.
# This is the mechanical signal that catches a protocol/safety edit to a live
# .omp/agents/*.md seat that never got propagated to the packaged copy.
# ---------------------------------------------------------------------------

# Each entry: (old snippet from the live .omp/ file, new snippet in the
# packaged template, reason it's an intentional adopter-facing difference
# rather than drift). Applied to the live text IN ORDER; the result must
# equal the packaged text exactly. Extend this table -- never widen a
# snippet or drop reasoning -- when a new intentional divergence is added.
_ADOPTER_SUBSTITUTIONS: dict[str, list[tuple[str, str, str]]] = {
    "agents/scout.md": [
        (
            "description: Read-only reconnaissance seat. Maps contracts, proposes decompositions, "
            "lists ambiguities, and assesses proposals. Cites file:line for every load-bearing claim. "
            "Writes nothing to the repository.\nmodel: anthropic/claude-opus-5:high",
            "description: Read-only reconnaissance seat. Maps contracts, proposes decompositions, "
            "lists ambiguities, and assesses proposals. Cites file:line for every load-bearing claim. "
            "Writes nothing to the repository.\n"
            "# TEMPLATE (orc onboard --omp): model: below mirrors orc-werk's own pilot default.\n"
            "# Scout is read-only reconnaissance, never verdict-bearing, so it may share ship's\n"
            "# model family; pick any model available in your own account.\n"
            "model: anthropic/claude-opus-5:high",
            "adopter-facing model-pin disclaimer (account-specific, out of scope per TASK-M5-007)",
        ),
    ],
    "agents/ship.md": [
        (
            "description: Implementation seat. Ships exactly one task card in its own git worktree and "
            "PR, runs the local gate, records the execution settlement in the orc ledger, never merges, "
            "never verifies its own work.\nmodel: anthropic/claude-sonnet-5:medium",
            "description: Implementation seat. Ships exactly one task card in its own git worktree and "
            "PR, runs the local gate, records the execution settlement in the orc ledger, never merges, "
            "never verifies its own work.\n"
            "# TEMPLATE (orc onboard --omp): model: below mirrors orc-werk's own pilot default.\n"
            "# Pick a model available in your own account for this seat. The verify seat below\n"
            "# must run a different model family than this one (a model-diversity risk control) --\n"
            "# confirm a different-family model is actually available before first use.\n"
            "model: anthropic/claude-sonnet-5:medium",
            "adopter-facing model-pin disclaimer",
        ),
        (
            "- Work only inside `.worktrees/<branch>` under the repository root. Create it with "
            "`git worktree add .worktrees/<branch> -b <branch> master`.\n"
            "- Never merge, never push to `master`, never run `gh pr merge`, never record an assurance "
            "verdict. Landing is the watchtower's act.\n"
            "- The ledger lives at the primary checkout root: always run `orc` as "
            "`ORC_JOURNAL_DIR=<repo-root>/.orc uv run --project <repo-root> orc ...`.",
            "- Work only inside `.worktrees/<branch>` under the repository root. Create it with "
            "`git worktree add .worktrees/<branch> -b <branch> <default-branch>`.\n"
            "- Never merge, never push to the default branch, never run `gh pr merge`, never record an "
            "assurance verdict. Landing is the watchtower's act.\n"
            "- The ledger lives at the primary checkout root: always run `orc` as "
            "`ORC_JOURNAL_DIR=<repo-root>/.orc uv run --project <repo-root> orc ...` (adjust the "
            "invocation to however `orc` is installed in this repo).",
            "orc-werk's own default branch name (master) and orc install path are repo-specific, "
            "not portable to an adopter",
        ),
        (
            "2. Implement. Run `bash scripts/check.sh` in the worktree; it must be green. A skipped or "
            "narrowed check is a defect, not a pass.",
            "2. Implement. Run the repository's own check script (e.g. `bash scripts/check.sh`) in the "
            "worktree; it must be green. A skipped or narrowed check is a defect, not a pass.",
            "orc-werk's own check.sh path is repo-specific, not portable to an adopter",
        ),
    ],
    "agents/verify.md": [
        (
            "# V7: every entry is a non-Anthropic family (ship runs on anthropic/*). Never add a "
            "Claude-family fallback here.\n"
            "# Order is resolution preference only; a usage-limit error on entry 1 does NOT fall "
            "through at spawn\n"
            "# (observed 2026-09-06: two spawns died at usage_limit_reached on openai-codex). Put the "
            "model with quota first.\n"
            "model: google-antigravity/gemini-3.8-flash:high, openai-codex/gpt-5.6-sol:high, "
            "google-antigravity/gpt-oss-120b",
            "# TEMPLATE (orc onboard --omp): every entry below is a non-Anthropic family, since\n"
            "# this scaffold's ship seat (.omp/agents/ship.md) templates as anthropic/* -- a\n"
            "# model-diversity risk control against self-review-by-construction (ADR-0007's V7\n"
            "# ruling -- canonical to the orc-werk repository/package, cited here for context\n"
            "# only): a verify seat sharing the ship seat's model family cannot render an\n"
            "# independent, adversarial verdict, regardless of whether that pairing has ever\n"
            "# produced an observed rejection. That repository/package's own seat-reliability\n"
            "# incident log (docs/delivery/seat-reliability.md, same repository/package, same\n"
            "# context-only citation) records something narrower: real spawn-time model\n"
            "# unavailability, not a pairing-violation rejection -- two verify spawns died at\n"
            "# a usage-limit error because OMP does not fall through a frontmatter model list\n"
            "# to a later entry on a spawn-time usage-limit error. Order is resolution\n"
            "# preference only: unless your harness's own retry/fallback configuration names\n"
            "# a model explicitly, put the model with quota first. Pick models actually\n"
            "# available in your own account before first use; do not add a Claude-family\n"
            "# fallback here while ship runs on anthropic/*.\n"
            "model: google-antigravity/gemini-3.8-flash:high, openai-codex/gpt-5.6-sol:high, "
            "google-antigravity/gpt-oss-120b",
            "adopter-facing model-pin disclaimer plus ADR-0007's V7 ruling grounded in "
            "self-review-by-construction (not the incident log) and this repository's own "
            "seat-reliability incident log cited only for what it actually records -- spawn-time "
            "model unavailability and the lack of spawn-time frontmatter fallthrough, never a "
            "rejection from violating the V7 pairing, which the log has never recorded",
        ),
        (
            "- The ledger lives at the primary checkout root: `ORC_JOURNAL_DIR=<repo-root>/.orc uv run "
            "--project <repo-root> orc ...`.",
            "- The ledger lives at the primary checkout root: `ORC_JOURNAL_DIR=<repo-root>/.orc uv run "
            "--project <repo-root> orc ...` (adjust the invocation to however `orc` is installed in "
            "this repo).",
            "orc install path is repo-specific, not portable to an adopter",
        ),
        (
            "1. Fetch the PR into your own worktree at the derived sha. Run `bash scripts/check.sh`. A "
            "green gate is an input, never the verdict.",
            "1. Fetch the PR into your own worktree at the derived sha. Run the repository's own check "
            "script (e.g. `bash scripts/check.sh`). A green gate is an input, never the verdict.",
            "orc-werk's own check.sh path is repo-specific, not portable to an adopter",
        ),
        (
            "4. Decide: `accepted` only when every acceptance criterion holds at the derived sha; "
            "`rejected` for any defect on advertised behavior (findings verbatim, they become the next "
            "brief); `inconclusive` when you could not evaluate (tooling down, timeout, sandbox "
            "missing) \u2014 never `rejected` for a failure that is yours.",
            "4. Decide: `accepted` only when every acceptance criterion holds at the derived sha; "
            "`rejected` for any defect on advertised behavior (findings verbatim, they become the next "
            "brief); `inconclusive` when you could not evaluate (tooling down, timeout, sandbox "
            "missing) -- never `rejected` for a failure that is yours.",
            "ASCII-safe em-dash substitution for the packaged template (no functional difference)",
        ),
    ],
    "config.yml": [
        (
            "# Project harness config for orc-werk delivery seats (see .omp/agents/*.md).\n"
            "# Seats are OMP subagents; the orc ledger stays the durable record (ADR-0005).",
            "# Project harness config for this repo's delivery seats (see .omp/agents/*.md).\n"
            "# Seats are OMP subagents; the orc ledger stays the durable record (ADR-0005 --\n"
            "# canonical to the orc-werk repository/package, cited here for context only).\n"
            "# TEMPLATE (orc onboard --omp): the values below mirror orc-werk's own pilot\n"
            "# defaults; tune maxRuntimeMs/maxRecursionDepth to taste, nothing here is\n"
            "# account-specific.",
            "orc-werk-specific header rephrased for an adopting repo, plus a TEMPLATE disclaimer",
        ),
    ],
    "RULES.md": [
        (
            "# orc-werk seat invariants (sticky; mechanics in `.omp/agents/*.md`)",
            "# Seat invariants (sticky; mechanics in `.omp/agents/*.md`)",
            "orc-werk's own name dropped from the title for an adopting repo",
        ),
    ],
}


def _apply_adopter_substitutions(live_text: str, resource: str) -> str:
    """Apply each `_ADOPTER_SUBSTITUTIONS[resource]` entry to `live_text`, in
    order, and return the transformed result -- the packaged scaffold text
    this predicts. Each `old` snippet must appear exactly once; if a live
    `.omp/` seat edit changed or removed the surrounding text, the snippet
    stops matching and this raises immediately, naming the resource and the
    substitution that broke."""
    result = live_text
    for old, new, reason in _ADOPTER_SUBSTITUTIONS[resource]:
        count = result.count(old)
        if count != 1:
            raise AssertionError(
                f"packaged-scaffold drift check for {resource!r}: allowlisted substitution "
                f"({reason}) expected exactly one occurrence of the live snippet below in "
                f".omp/{resource}, found {count}. The live seat changed in a way this allowlist "
                f"doesn't cover -- propagate the change to src/orc_werk/omp_scaffold/{resource}, "
                f"or if this IS a new intended adopter-facing substitution, add it to "
                f"_ADOPTER_SUBSTITUTIONS in this test.\n--- expected live snippet ---\n{old}"
            )
        result = result.replace(old, new, 1)
    return result


class PackagedScaffoldDriftTest(unittest.TestCase):
    """Fails the moment a live `.omp/` seat edit isn't propagated to the
    packaged scaffold and isn't declared as an intended adopter-facing
    substitution in `_ADOPTER_SUBSTITUTIONS` -- the mechanical signal
    `omp_scaffold/__init__.py`'s docstring promises: the two copies may
    differ, but only in enumerated, reasoned ways."""

    def _assert_matches_allowlist(self, resource: str, live_text: str, packaged_text: str):
        expected = _apply_adopter_substitutions(live_text, resource)
        self.assertEqual(
            expected, packaged_text,
            f"src/orc_werk/omp_scaffold/{resource} has drifted from .omp/{resource} beyond the "
            f"substitutions enumerated in _ADOPTER_SUBSTITUTIONS -- update the packaged file to "
            f"match the live seat, or extend the allowlist if the new difference is an intended "
            f"adopter-facing one.",
        )

    def test_scout_matches_live_seat_modulo_allowlist(self):
        live = (REPO_ROOT / ".omp" / "agents" / "scout.md").read_text(encoding="utf-8")
        self._assert_matches_allowlist("agents/scout.md", live, omp_scaffold_agent_text("scout"))

    def test_ship_matches_live_seat_modulo_allowlist(self):
        live = (REPO_ROOT / ".omp" / "agents" / "ship.md").read_text(encoding="utf-8")
        self._assert_matches_allowlist("agents/ship.md", live, omp_scaffold_agent_text("ship"))

    def test_verify_matches_live_seat_modulo_allowlist(self):
        live = (REPO_ROOT / ".omp" / "agents" / "verify.md").read_text(encoding="utf-8")
        self._assert_matches_allowlist("agents/verify.md", live, omp_scaffold_agent_text("verify"))

    def test_config_matches_live_seat_modulo_allowlist(self):
        live = (REPO_ROOT / ".omp" / "config.yml").read_text(encoding="utf-8")
        self._assert_matches_allowlist("config.yml", live, omp_scaffold_config_text())

    def test_rules_matches_live_seat_modulo_allowlist(self):
        live = (REPO_ROOT / ".omp" / "RULES.md").read_text(encoding="utf-8")
        self._assert_matches_allowlist("RULES.md", live, omp_scaffold_rules_text())


# ---------------------------------------------------------------------------
# Install verification: honest found/absent reporting, driven via subprocess
# so `$PATH` can be controlled precisely.
# ---------------------------------------------------------------------------


class VerificationHonestyTest(unittest.TestCase):
    def test_reports_orc_and_bd_absent_when_not_on_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            result = _run_cli(target, "onboard", "--path", str(target), env={"PATH": "/usr/bin:/bin"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("orc console script on PATH: absent", result.stdout)
            self.assertIn("bd (optional Beads mirror): absent -- noted optional, never required", result.stdout)
            self.assertIn("orc_werk importable as a module in this interpreter: yes", result.stdout)

    def test_reports_orc_and_bd_found_when_stubbed_on_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            fake_bin = target / "fakebin"
            fake_bin.mkdir()
            for name in ("orc", "bd"):
                stub = fake_bin / name
                stub.write_text("#!/bin/sh\necho stub\n", encoding="utf-8")
                stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            env = {"PATH": f"{fake_bin}:/usr/bin:/bin"}
            result = _run_cli(target, "onboard", "--path", str(target), env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"orc console script on PATH: found ({fake_bin / 'orc'})", result.stdout)
            self.assertIn(f"bd (optional Beads mirror): found ({fake_bin / 'bd'})", result.stdout)

    def test_journal_dir_resolution_reports_env_source_anchored_at_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            env = {"PATH": "/usr/bin:/bin", "ORC_JOURNAL_DIR": "custom-journal"}
            result = _run_cli(target, "onboard", "--path", str(target), env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = (target / "custom-journal").resolve()
            self.assertIn(f"journal dir resolves to: {expected}", result.stdout)
            self.assertIn("source: ORC_JOURNAL_DIR", result.stdout)

    def test_journal_dir_resolution_default_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            result = _run_cli(target, "onboard", "--path", str(target), env={"PATH": "/usr/bin:/bin"})
            expected = (target / ".orc").resolve()
            self.assertIn(f"journal dir resolves to: {expected}", result.stdout)
            self.assertIn("source: default ./.orc", result.stdout)

    def test_output_has_no_terminal_escape_sequences_when_not_a_tty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(Path(tmp), "onboard", "--path", tmp, env={"PATH": "/usr/bin:/bin"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("\x1b", result.stdout)

    def test_print_agents_block_over_subprocess_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            result = _run_cli(target, "onboard", "--print-agents-block")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(BLOCK_BEGIN, result.stdout)
            self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
