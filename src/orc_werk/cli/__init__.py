"""Orc Werk command-line product surface (`TASK-M0-005`).

Owns the user-facing command surface and composition bootstrap: it may
import `orc_werk.app` and `orc_werk.adapters` (`ARCH-REPOSITORY-STRUCTURE`).
"""

from orc_werk.cli.main import build_parser, main

__all__ = ["build_parser", "main"]
