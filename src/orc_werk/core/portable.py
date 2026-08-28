"""Portability guard shared by canonical value types and their serialization.

ARCH-REPOSITORY-STRUCTURE forbids pickle/marshal, Python class names,
exception objects, arbitrary object graphs, callables, and object identity
in canonical shapes. `is_portable` recursively checks that a value is built
only from JSON-compatible primitives: str, int, float, bool, None, list, and
string-keyed dict.
"""

from __future__ import annotations

from typing import Any


def is_portable(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, (list, tuple)):
        return all(is_portable(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and is_portable(val) for key, val in value.items())
    return False


def to_portable(value: Any) -> Any:
    """Recursively coerce tuples/mappings into portable list/dict form.

    Raises TypeError for anything that is not already JSON-compatible; this
    function normalizes container types, it does not invent data.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [to_portable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_portable(val) for key, val in value.items()}
    raise TypeError(f"value is not portable/JSON-compatible: {value!r}")
