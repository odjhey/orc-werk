"""Read-only pre-dispatch config validation and ingestion preview (#148)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


class CliValidateTest(unittest.TestCase):
    def _validate(
        self, root: Path, config: dict, *extra_args: str
    ) -> subprocess.CompletedProcess[str]:
        path = root / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "orc_werk.cli", "validate", str(path), *extra_args],
            cwd=root,
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_valid_config_previews_ingestion_without_creating_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._validate(
                root,
                {
                    "plan": {"works": [{"work_id": "w", "deps": []}]},
                    "execution": {"adapter": "scripted"},
                    "candidate": {"adapter": "scripted"},
                    "assurance": {"adapter": "scripted"},
                    "attempts": {
                        "w": [{
                            "outcome": "completed",
                            "candidate": {"label": "A"},
                            "assurance": {
                                "verdict": "accepted",
                                "extensions": {"review-findings/v1": {"findings": []}},
                            },
                        }]
                    },
                },
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("PASS:", result.stdout)
            self.assertIn("plan works: w", result.stdout)
            self.assertIn("adapters: execution=scripted candidate=scripted assurance=scripted", result.stdout)
            self.assertIn("attempts.w[0]: keys=[assurance, candidate, outcome]", result.stdout)
            self.assertIn(
                "attempts.w[0].assurance: verdict=accepted, extensions=[review-findings/v1]",
                result.stdout,
            )
            self.assertFalse((root / ".orc").exists())

    def test_profile_composes_with_per_run_config_and_names_both_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "ledger"
            journal.mkdir()
            (journal / "profile.json").write_text(
                json.dumps({
                    "candidate": {"adapter": "git"},
                    "mirror": {"adapter": "beads", "workspace": "/tmp/beads"},
                }),
                encoding="utf-8",
            )
            result = self._validate(
                root,
                {
                    "candidate": {"repo_path": str(root)},
                },
                "--journal", str(journal),
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn(
                f"layers: profile: {(journal / 'profile.json').resolve()} (candidate, mirror) "
                f"+ config: {root / 'config.json'}",
                result.stdout,
            )
            self.assertIn("adapters: execution=scripted candidate=git assurance=scripted", result.stdout)

    def test_adapter_switch_keeps_override_keys_and_unrelated_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "ledger"
            journal.mkdir()
            (journal / "profile.json").write_text(json.dumps({
                "assurance": {
                    "adapter": "command", "script": "scripts/assure.sh",
                    "cwd": "/tmp", "timeout_s": 120,
                }
            }), encoding="utf-8")

            result = self._validate(
                root,
                {"assurance": {"adapter": "scripted"}, "briefs": {"work-1": "keep me"}},
                "--journal", str(journal),
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("adapters: execution=scripted candidate=scripted assurance=scripted", result.stdout)

    def test_same_adapter_keeps_profile_defaults_composed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "ledger"
            journal.mkdir()
            script = root / "scripts" / "assure.sh"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            script.chmod(0o755)
            (journal / "profile.json").write_text(json.dumps({
                "assurance": {
                    "adapter": "command", "script": "scripts/assure.sh", "timeout_s": 120,
                },
                "candidate": {"adapter": "git"},
            }), encoding="utf-8")

            result = self._validate(
                root,
                {
                    "assurance": {"adapter": "command", "cwd": str(root)},
                    "candidate": {"adapter": "git", "repo_path": str(root)},
                },
                "--journal", str(journal),
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("adapters: execution=scripted candidate=git assurance=command", result.stdout)

    def test_candidate_switch_to_scripted_drops_inherited_git_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "ledger"
            journal.mkdir()
            (journal / "profile.json").write_text(
                json.dumps({"candidate": {"adapter": "git"}}), encoding="utf-8"
            )

            result = self._validate(
                root, {"candidate": {"adapter": "scripted"}}, "--journal", str(journal)
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("candidate=scripted", result.stdout)

    def test_same_git_candidate_composes_explicit_repo_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "ledger"
            journal.mkdir()
            (journal / "profile.json").write_text(
                json.dumps({"candidate": {"adapter": "git"}}), encoding="utf-8"
            )

            result = self._validate(
                root,
                {"candidate": {"adapter": "git", "repo_path": str(root)}},
                "--journal", str(journal),
            )

            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn("candidate=git", result.stdout)

    def test_no_profile_preserves_standalone_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "ledger"
            journal.mkdir()
            (journal / "profile.json").write_text(
                json.dumps({
                    "assurance": {"adapter": "command", "script": "scripts/assure.sh", "cwd": str(root)},
                    "candidate": {"adapter": "git", "repo_path": str(root)},
                }),
                encoding="utf-8",
            )
            # The per-run config alone (adapter selected, but the profile's
            # `script`/`cwd` completeness dropped since --no-profile skips
            # composing it in) is missing a REQUIRED command-assurance
            # field -- proving --no-profile really validates the config
            # standalone rather than silently still consulting the profile.
            result = self._validate(
                root,
                {"assurance": {"adapter": "command"}, "candidate": {"adapter": "git", "repo_path": str(root)}},
                "--journal", str(journal), "--no-profile",
            )
            self.assertEqual(result.returncode, 2)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertEqual(error["details"]["path"], "<config>.assurance.script")

    def test_missing_profile_keeps_standalone_behavior_and_does_not_create_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "missing" / ".orc"
            result = self._validate(root, {}, "--journal", str(journal))
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertIn(f"layers: config: {root / 'config.json'}", result.stdout)
            self.assertFalse(journal.exists())

    def test_unknown_assurance_key_is_canonical_validation_error_and_pure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._validate(root, {"attempts": {"w": [{"assurance": {"reveiw-findings": []}}]}})
            self.assertEqual(result.returncode, 2)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("reveiw-findings", error["message"])
            self.assertIn("<config>.attempts.w[0].assurance", error["message"])
            self.assertFalse((root / ".orc").exists())

    def test_invalid_derived_identity_shapes_name_exact_path(self) -> None:
        cases = ("stale", {}, {"extensions": {"source": "audit"}})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, derived_identity in enumerate(cases):
                with self.subTest(derived_identity=derived_identity):
                    result = self._validate(root, {
                        "attempts": {"w": [{"assurance": {
                            "verdict": "accepted", "derived_identity": derived_identity
                        }}]}
                    })
                    self.assertEqual(result.returncode, 2)
                    error = json.loads(result.stderr)
                    self.assertEqual(error["error"], "ERR-VALIDATION")
                    self.assertEqual(
                        error["details"]["path"],
                        "<config>.attempts.w[0].assurance.derived_identity",
                    )

    def test_unknown_top_level_key_is_canonical_validation_error_and_pure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._validate(root, {"attemtps": {}})
            self.assertEqual(result.returncode, 2)
            error = json.loads(result.stderr)
            self.assertEqual(error["error"], "ERR-VALIDATION")
            self.assertIn("attemtps", error["message"])
            self.assertFalse((root / ".orc").exists())


if __name__ == "__main__":
    unittest.main()
