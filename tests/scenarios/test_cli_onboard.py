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
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from orc_werk.cli.onboard import (
    BLOCK_BEGIN,
    BLOCK_END,
    GITIGNORE_ENTRY,
    agents_block_text,
    cmd_onboard,
    packaged_skill_text,
)
from orc_werk.core.errors import CoreError

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


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
    defaults = dict(path=".", print_agents_block=False, force=False, agents_file="AGENTS.md", journal=None)
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

    def test_agents_block_derived_from_packaged_skill_text(self):
        skill_text = packaged_skill_text()
        block = agents_block_text(skill_text)
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
        self.assertNotIn("# Working with the orc delivery ledger", block)
        # but the ledger's own intro paragraph (context-free content) survives
        self.assertIn("This repository tracks delivery through orc", block)

    def test_agents_block_is_a_live_derivation_not_a_frozen_copy(self):
        # A caller-supplied skill_text that diverges from the packaged one
        # produces a divergent block -- proves `agents_block_text` actually
        # transforms its input rather than returning a string literal that
        # could silently drift from SKILL.md (a fork would fail this).
        forked = packaged_skill_text().replace("Orient first", "FORKED SECTION TITLE")
        self.assertIn("FORKED SECTION TITLE", agents_block_text(forked))
        self.assertNotIn("FORKED SECTION TITLE", agents_block_text())


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
        self.assertIn("delivery-ledger rules below", block)

    def test_real_execution_and_assurance_profile_declares_adapter_driven_mode(self):
        profile = self.target / ".orc" / "profile.json"
        profile.parent.mkdir()
        profile.write_text(
            json.dumps(
                {
                    "execution": {"adapter": "acp", "cwd": str(self.target)},
                    "candidate": {"adapter": "git", "repo_path": str(self.target)},
                    "assurance": {"adapter": "no-mistakes", "repo_path": str(self.target)},
                }
            ),
            encoding="utf-8",
        )
        _onboard(path=str(self.target))
        block = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("ADAPTER-DRIVEN MODE", block)
        self.assertIn("you configure rather than perform", block)
        self.assertIn("delivery-ledger rules below", block)

    def test_absent_profile_declares_scripted_default_mode(self):
        _onboard(path=str(self.target))
        block = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("SCRIPTED MODE (scripted default)", block)
        self.assertIn("delivery-ledger rules below", block)

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
        self.assertIn("already installed and matches the package source", output)
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

    def test_operator_modified_agents_block_is_skipped_then_replaced_with_force(self):
        _onboard(path=str(self.target))
        agents_path = self.target / "AGENTS.md"
        original = agents_path.read_text(encoding="utf-8")
        modified = original.replace("This repository tracks delivery", "OPERATOR EDITED THIS LINE")
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
        self.assertIn("This repository tracks delivery", replaced)
        self.assertIn("replaced (--force)", output)

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
