#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers.factory import factory_api_key_from_dotenv, factory_plan_name, factory_usage_from_payloads


assert factory_api_key_from_dotenv("export FACTORY_API_KEY='abc'") == "abc"
assert factory_plan_name({
    "organization": {
        "subscription": {
            "factoryTier": "team_annual",
            "orbSubscription": {"plan": {"name": "Factory Pro Annual Plan"}},
        }
    }
}) == "Factory Team Annual"
limits = {
    "usesTokenRateLimitsBilling": True,
    "limits": {
        "standard": {
            "fiveHour": {"usedPercent": 2, "secondsRemaining": 100},
            "weekly": {"usedPercent": 8, "secondsRemaining": 200},
            "monthly": {"usedPercent": 27, "windowEnd": "2026-09-12T10:32:37.120Z"},
        },
        "core": {
            "fiveHour": {"usedPercent": 29, "windowEnd": "2026-08-11T19:15:10.804Z"},
        },
    },
    "overagePreference": "droidCore",
    "extraUsageBalanceCents": 0,
}
auth = {
    "userProfile": {"email": "user@example.com"},
    "organization": {
        "name": "Example",
        "subscription": {
            "factoryTier": "team_annual",
            "orbSubscription": {"plan": {"name": "Factory Pro Annual Plan"}},
        },
    },
}
usage, credits = factory_usage_from_payloads(auth, limits, None, None)
assert usage["primary"]["label"] == "5h"
assert usage["primary"]["usedPercent"] == 2
assert usage["secondary"]["label"] == "Weekly"
assert usage["tertiary"]["label"] == "Monthly"
assert [extra["title"] for extra in usage["extraRateWindows"]] == ["Core 5h", "Core 7-day", "Core Monthly"]
assert usage["extraRateWindows"][0]["window"]["usedPercent"] == 0
assert "Factory Team Annual" in usage["loginMethod"]
assert credits["remaining"] == 0
assert credits["label"] == "Extra usage"
legacy_usage, _ = factory_usage_from_payloads(auth, None, {
    "usage": {
        "endDate": 1800864000000,
        "standard": {"userTokens": 40, "totalAllowance": 100, "usedRatio": 0.4},
        "premium": {"userTokens": 10, "totalAllowance": 100, "usedRatio": 0.1},
    }
}, None)
assert legacy_usage["primary"]["label"] == "Standard"
assert legacy_usage["primary"]["usedPercent"] == 40
assert legacy_usage["secondary"]["label"] == "Premium"
print("factory collector tests passed")
