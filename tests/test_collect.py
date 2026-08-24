#!/usr/bin/env python3
"""Collector dispatch and entry-point tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.main import PROVIDERS, requested_providers
from collector.schema import row
from collector.security import MAX_SNAPSHOT_BYTES, snapshot_json


assert requested_providers({}, ["grok"]) == ("grok",)
assert requested_providers({"only": "codex"}, []) == ("codex",)
assert requested_providers({"only": "factory"}, []) == ("factory",)
assert requested_providers({}, []) == PROVIDERS
assert PROVIDERS[-1] == "factory"
assert row("grok", source="chrome", error="x")["error"]["message"] == "x"
assert len(row("grok", source="chrome", error="x" * 1000)["error"]["message"]) == 512
assert len(snapshot_json([row("grok", source="chrome", error="x")]).encode()) <= MAX_SNAPSHOT_BYTES
print("collect tests passed")
