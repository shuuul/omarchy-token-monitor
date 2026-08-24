#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers.zed import zed_dashboard_windows


token_spend, edit_predictions = zed_dashboard_windows({
    "current_usage": {
        "token_spend": {
            "spend_in_cents": 257,
            "limit_in_cents": 1000,
            "updated_at": "2026-08-24T06:00:00Z",
        },
        "edit_predictions": {"used": 1, "limit": None, "remaining": None},
    }
})
assert token_spend["label"] == "Token Spend  $2.57 / $10"
assert token_spend["usedPercent"] == 25.7
assert token_spend["resetsAt"] is None
assert edit_predictions["label"] == "Edit Predictions"
assert edit_predictions["usedPercent"] == 0

limited_spend, limited_predictions = zed_dashboard_windows({
    "current_usage": {
        "token_spend": {"spend_in_cents": 0, "limit_in_cents": None, "updated_at": None},
        "edit_predictions": {"used": 500, "limit": 2000, "remaining": 1500},
    }
})
assert limited_spend is None
assert limited_predictions["usedPercent"] == 25
assert zed_dashboard_windows({}) == (None, None)
print("zed collector tests passed")
