"""OSC-8 clickable-path wrapping for printed filesystem paths (issue #55
scope addition, rerouted from the wiring PR).

`orc`'s `report:`/`journal:`/index lines already print the resolved
absolute path of a run's journal/report/journal-directory (`docs/playbooks/
cli-usage.md`: "every path this CLI prints... is the resolved absolute
path, so it's clickable in a terminal regardless of cwd"). This module adds
the next step -- an actual clickable hyperlink -- without changing what is
printed for a reader that cannot render one:

- `sys.stdout.isatty()` true (an interactive terminal): the path is
  wrapped in an OSC 8 hyperlink escape sequence (`file://` target) whose
  display text is the exact same plain path string that would otherwise
  have been printed -- a terminal that understands OSC 8 renders it as a
  clickable path; one that doesn't typically falls back to just showing
  the display text (OSC 8 is a well-established de facto terminal
  convention, degrading gracefully).
- `sys.stdout.isatty()` false (a pipe, a file redirect, or -- the common
  case this CLI's own `--help`/module docstrings call out -- an agent
  capturing this CLI's output programmatically): the plain path string is
  printed byte-identical to today, with zero escape bytes. Agent-facing
  output must never carry terminal escape sequences an agent's own
  parsing/logging could choke on or have to strip; this is the negative
  assertion this module's own tests pin explicitly.

Scope: wrapping applies to lines that ARE a printed path (this CLI's
`report:`/`journal:` lines, and directory-path index lines) -- never to a
path embedded as one argument inside a larger copy-pasteable shell command
(the `next:` block's `orc dispatch ...` affordance strings). Embedding an
invisible OSC 8 escape sequence inside text a reader is meant to select and
paste as a literal command risks corrupting that paste in terminals/tools
that don't strip it; the `next:` block's commands are deliberately left
plain (see the PR body's "Ambiguities encountered" for this scoping call).

`sys.stdout` is read at call time, not import time, so redirecting stdout
(as `contextlib.redirect_stdout` does in tests) changes this module's
behavior exactly the way it changes `print`'s.
"""

from __future__ import annotations

import sys
from pathlib import Path

_OSC8_OPEN = "\x1b]8;;"
_OSC8_SEP = "\x1b\\"
_OSC8_CLOSE = "\x1b]8;;\x1b\\"


def hyperlink_path(path: Path) -> str:
    """Return `path` (an absolute filesystem path) as the string this CLI
    should print for it: OSC-8-wrapped when `sys.stdout` is a TTY, the
    plain path string (unchanged, no escape bytes) otherwise."""
    text = str(path)
    isatty = getattr(sys.stdout, "isatty", None)
    if not (isatty and isatty()):
        return text
    resolved = path if path.is_absolute() else path.resolve()
    target = resolved.as_uri()
    return f"{_OSC8_OPEN}{target}{_OSC8_SEP}{text}{_OSC8_CLOSE}"


__all__ = ["hyperlink_path"]
