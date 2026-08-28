"""Dependency-free in-memory adapters for core and conformance tests."""

from __future__ import annotations

from orc_werk.adapters.memory.journal import MemoryJournal
from orc_werk.adapters.memory.work_graph import MemoryWorkGraph

__all__ = ["MemoryJournal", "MemoryWorkGraph"]
