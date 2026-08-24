#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers.cursor import cursor_grok_bot_window


grok_bot = cursor_grok_bot_window(b"""
{
  "currentPeriodStart": "2026-08-24T02:28:01.719Z",
  "nextResetTimestampUtc": "2026-08-31T02:28:01.719Z",
  "usagePercent": 13.089207,
  "hasAvailableUsage": true,
  "hasNonZeroIncludedLimit": true
}
""")
assert grok_bot["id"] == "cursor-grok-bot"
assert grok_bot["title"] == "Grok Bot"
assert grok_bot["window"]["usedPercent"] == 13.089207
assert grok_bot["window"]["windowMinutes"] == 10080
assert grok_bot["window"]["resetsAt"] == "2026-08-31T02:28:01.719Z"
assert cursor_grok_bot_window('{"usagePercent": 10, "hasNonZeroIncludedLimit": false}') is None
assert cursor_grok_bot_window("not json") is None
print("cursor collector tests passed")
