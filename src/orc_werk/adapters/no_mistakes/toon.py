"""Minimal, tolerant TOON parser for `no-mistakes axi status`/`axi run`
output (`TASK-M2-001`).

`no-mistakes axi` prints "token-efficient TOON to stdout" and offers no
`--format json` (or any other machine-structured) alternative -- confirmed
by reading every `axi`/`axi status`/`axi run` `--help` text on this
machine, none of which advertise a format flag (`docs/adapters/no-mistakes/
mapping.md` "TOON parsing" records the recon). Per the task card's
instruction to "write a minimal tolerant parser and record its fragility"
when TOON is the only surface, this module is exactly that: a small,
purpose-built parser for the handful of shapes `NoMistakesAssurance`
actually reads (nested `key: value` blocks and `key[N]{col,...}:` record
tables), not a general TOON-format implementation. It tolerates and
silently skips any line it does not recognize rather than raising --
"minimal" means narrow coverage, not strict validation of a third-party
tool's output format this adapter does not own.

Observed shape (real `no-mistakes@`, recon session, `docs/adapters/
no-mistakes/mapping.md` "Empirical recon"):

```text
run:
  id: "01M14D86JKBVCMNEKK6W2ER559"
  branch: feature/test-branch
  status: running
  steps[9]{step,status,findings,duration_ms}:
    intent,completed,0,3
    review,running,0,0
gate:
  step: review
  status: awaiting_approval
  findings[2]{id,severity,file,action,description}:
    hardcoded-secret,error,buggy.py,auto-fix,"A hardcoded credential-shaped ..."
outcome: passed
```

Parsing rules (deliberately narrow):

- Indentation is 2-space-per-level, tracked structurally (a stack of
  `(indent, container, mode, columns)` frames) -- never assumed to be
  exactly 2 so mild formatting drift does not silently corrupt structure,
  only exact-or-deeper/shallower comparisons matter.
- `key: value` -> scalar leaf. `key:` (nothing after the colon) -> nested
  block, children are the following more-indented lines. `key[N]{col1,
  col2,...}:` -> a record table; children (all at one consistent deeper
  indent) are CSV-shaped rows zipped against the declared columns. A
  bracket count suffix (`[9]`, `[2]`, ...) is stripped from the stored key
  name (`"steps[9]"` -> `"steps"`) so consuming code never has to guess or
  hardcode a row count.
- Scalar values: a fully double-quoted token is unescaped (a literal
  backslash-quote becomes a plain quote, a literal double-backslash
  becomes a single backslash) and returned as a string with the quotes
  stripped;
  `true`/`false` become real booleans; a token that is only digits (with
  an optional leading `-`) becomes an `int`; anything else is returned
  verbatim as a string (this deliberately does NOT attempt to parse
  `key[N]: comma,separated,inline,list` shapes like `help[6]: ...` into a
  structured list -- nothing this adapter consumes ever needs that shape,
  and guessing at inline-list quoting rules generically is exactly the
  kind of scope this "minimal" parser avoids).
- Table rows are split with a small quote-aware tokenizer
  (`_split_toon_row`) that treats a backslash immediately before `"` or
  `\\` as an escape (matching the backslash-escaped-quote style observed
  in real `no-mistakes` finding descriptions, e.g. an embedded
  `` `API_KEY = \"sk-...\"` ``) -- NOT standard RFC 4180 CSV quoting
  (which doubles an embedded quote instead), because that is not the
  escaping style this tool's output actually uses.

Known fragility (recorded per the task card; also flagged in
`docs/playbooks/cli-usage.md`'s Known issues ledger):

- This is reverse-engineered from one CLI version's observed output, not
  a published grammar. A future `no-mistakes` release could change
  indentation width, quoting, or field names without notice; this parser
  has no schema/version guard and would silently parse such a change
  incorrectly (most likely: some fields go missing, read as absent rather
  than erroring) rather than fail loudly. `NoMistakesAssurance` compensates
  where it can (never fabricates settlement from a field it fails to find
  -- see `assurance.py`) but a silent mis-parse of a table row is not
  otherwise detected.
- Only the flat scalar/nested-block/record-table shapes above are
  handled. Any other TOON construct (deeper inline-list encodings,
  multi-line scalars, alternate quoting) is silently skipped, not an
  error -- lines that do not match a known shape are ignored so an
  unrelated future field does not break parsing of the fields this
  adapter does read.
"""

from __future__ import annotations

import re
from typing import Any

_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_\[\]]*)(\{[^}]*\})?:\s*(.*)$")
_BRACKET_SUFFIX_RE = re.compile(r"\[\d+\]$")
_INT_RE = re.compile(r"^-?\d+$")


def _strip_bracket_suffix(key: str) -> str:
    return _BRACKET_SUFFIX_RE.sub("", key)


def _parse_scalar_token(raw: str) -> Any:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    if raw == "true":
        return True
    if raw == "false":
        return False
    if _INT_RE.match(raw):
        return int(raw)
    return raw


def _split_toon_row(line: str) -> list[str]:
    """Quote-aware comma split for one table row. See module docstring
    for why this is backslash-escape-aware rather than RFC 4180 CSV."""
    fields: list[str] = []
    buf: list[str] = []
    in_quotes = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if in_quotes:
            if ch == "\\" and i + 1 < n and line[i + 1] in ('"', "\\"):
                buf.append(line[i + 1])
                i += 2
                continue
            if ch == '"':
                in_quotes = False
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_quotes = True
            i += 1
            continue
        if ch == ",":
            fields.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    fields.append("".join(buf))
    return [f.strip() for f in fields]


def parse_toon(text: str) -> dict[str, Any]:
    """Parse `no-mistakes axi`/`axi status` TOON stdout into a plain
    nested `dict`/`list` structure (portable, JSON-compatible). Returns
    `{}` for empty/whitespace-only input. Never raises on unrecognized
    input -- see module docstring's "Known fragility"."""
    root: dict[str, Any] = {}
    # Stack of (indent, container, mode, columns). mode is "dict" or
    # "table"; columns is the declared column list, only set for "table".
    stack: list[tuple[int, Any, str, list[str] | None]] = [(-1, root, "dict", None)]

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        content = raw_line.strip()

        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()
        _parent_indent, parent, parent_mode, parent_cols = stack[-1]

        if parent_mode == "table" and parent_cols is not None:
            values = _split_toon_row(content)
            row = {col: _parse_scalar_token(val) for col, val in zip(parent_cols, values)}
            parent.append(row)
            continue

        match = _LINE_RE.match(content)
        if not match:
            continue  # tolerate: not a shape this parser understands
        key_raw, brace, rest = match.groups()
        rest = rest.strip()
        key = _strip_bracket_suffix(key_raw)

        if not isinstance(parent, dict):
            continue  # tolerate: malformed nesting (e.g. a key under a table row)

        if brace and not rest:
            columns = [c.strip() for c in brace[1:-1].split(",") if c.strip()]
            new_list: list[Any] = []
            parent[key] = new_list
            stack.append((indent, new_list, "table", columns))
        elif not rest:
            new_dict: dict[str, Any] = {}
            parent[key] = new_dict
            stack.append((indent, new_dict, "dict", None))
        else:
            parent[key] = _parse_scalar_token(rest)

    return root


__all__ = ["parse_toon"]
