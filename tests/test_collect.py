#!/usr/bin/env python3
"""Collector dispatch and entry-point tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.main import PROVIDERS, requested_providers
from collector.schema import row


assert requested_providers({}, ["grok"]) == ("grok",)
assert requested_providers({"only": "codex"}, []) == ("codex",)
assert requested_providers({"only": "factory"}, []) == ("factory",)
assert requested_providers({}, []) == PROVIDERS
assert PROVIDERS[-1] == "factory"
assert row("grok", source="chrome", error="x")["error"]["message"] == "x"
print("collect tests passed")
