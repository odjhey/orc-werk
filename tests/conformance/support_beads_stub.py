"""Fake `bd` executable for `BeadsMirror`'s stub-bd tests
(`TASK-M2-006`).

No real `bd`/Dolt dependency: the fake binary is a small self-contained
Python script (stdlib only) written to a temp directory and passed
directly as `BeadsMirror(bd_bin=<path>)` -- achieving the same hermetic
isolation `support_acpx_stub.py` gets from a `PATH`-shadowing fake, without
needing to mutate `PATH` itself (`BeadsMirror._invoke` always spawns
`[self._bd_bin, ...]`, so an absolute path works identically to a `PATH`
lookup).

`BeadsMirror` is write-only: it never parses a `bd` subprocess's stdout
(module docstring, `orc_werk.adapters.beads.mirror`). This stub therefore
does not need to simulate `bd`'s actual JSON response shapes at all -- it
only needs to (a) record every invocation's argv for assertions and (b)
optionally fail on command, to exercise `BeadsMirror`'s non-fatal
degraded-mirror handling. `BeadsMirror._invoke` always builds argv as
`[bd_bin, "--json", "-C", <workspace>, <verb>, ...]`, so the verb is always
`sys.argv[4]` (1-indexed after the script path) -- this stub relies on
that fixed shape rather than parsing arbitrary flags.
"""

from __future__ import annotations

import json
import os
import stat
import textwrap
from pathlib import Path
from typing import Any

_STUB_SOURCE = textwrap.dedent(
    '''
    #!/usr/bin/env python3
    """Fake `bd` for BeadsMirror's stub-bd tests. See
    tests/conformance/support_beads_stub.py for the protocol this
    implements and why."""
    import json
    import os
    import sys
    from pathlib import Path

    LOG = Path(os.environ["ORC_BEADS_STUB_LOG"])
    FAIL_VERBS = set(filter(None, os.environ.get("ORC_BEADS_STUB_FAIL_VERBS", "").split(",")))

    argv = sys.argv[1:]
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(argv) + "\\n")

    # Fixed shape BeadsMirror._invoke always builds:
    # ["--json", "-C", <workspace>, <verb>, ...rest]
    verb = argv[3] if len(argv) > 3 else None
    if verb in FAIL_VERBS:
        sys.stderr.write(f"stub-bd: forced failure for verb {verb!r}\\n")
        sys.exit(1)
    print(json.dumps({"stub": True, "argv": argv}))
    sys.exit(0)
    '''
).lstrip("\n")


def install_stub(directory: Path) -> Path:
    """Write the fake `bd` script into `directory`, return its path.
    Caller passes this path as `BeadsMirror(bd_bin=<path>)`."""
    bin_path = directory / "bd-stub.py"
    bin_path.write_text(_STUB_SOURCE, encoding="utf-8")
    mode = bin_path.stat().st_mode
    bin_path.chmod(mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_path


def read_calls(log_path: Path) -> list[list[str]]:
    """Every recorded invocation's argv (the `[..., "--json", "-C",
    <workspace>, <verb>, ...]` list `BeadsMirror._invoke` built), in call
    order. Empty when the log file was never written (no calls made)."""
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verbs(calls: list[list[str]]) -> list[str]:
    """Convenience: just the `<verb>` token from each recorded call,
    matching the fixed argv shape this stub relies on."""
    return [call[3] for call in calls if len(call) > 3]
