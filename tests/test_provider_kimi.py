#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers.kimi import KIMI_REGIONS, kimi_plan_name, kimi_token_fresh, merge_kimi_rows


assert kimi_token_fresh({"expires_at": 1}, now=100) is False
assert kimi_token_fresh({"expires_at": 200}, now=100) is True
assert [region["name"] for region in KIMI_REGIONS] == ["kimi.com", "kimi.ai"]
merged = merge_kimi_rows([
    {
        "source": "cli",
        "usage": {
            "identity": {"plan": "Allegretto", "accountOrganization": "kimi.com"},
            "primary": {"usedPercent": 0, "label": "5-hour · kimi.com"},
        },
    }
])
assert "Allegretto" in merged["usage"]["loginMethod"]
assert "kimi.com" in merged["usage"]["loginMethod"]
assert kimi_plan_name(
    "token",
    {"me": None},
    {"user": {"membership": {"level": "LEVEL_INTERMEDIATE"}}},
) == "LEVEL_INTERMEDIATE"
print("kimi collector tests passed")
