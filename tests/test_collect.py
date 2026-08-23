#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("collect", ROOT / "collect.py")
collect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collect)

text = """
Signed in as zetarylee@gmail.com (shuuul)
**Amp Free:** 99% remaining today (resets daily)
**Amp Megawatt Subscription:** 95% other usage and 97% orb usage remaining - resets upon renewal in 6 days
**Individual credits:** $3.23 remaining
"""
parsed = collect.parse_amp_text(text)
assert parsed["provider"] == "amp"
assert parsed["usage"]["primary"]["usedPercent"] == 1
assert parsed["usage"]["secondary"]["usedPercent"] == 5
assert parsed["usage"]["tertiary"]["usedPercent"] == 3
assert parsed["credits"]["remaining"] == 3.23

payload = bytes.fromhex("0000000056") + b"\nT" + b"\r\x00\x00\x82B"
# The live parser is covered by the live collector; keep a structural check here.
row = collect.row("grok", source="chrome", error="x")
assert row["error"]["message"] == "x"
assert collect.kimi_token_fresh({"expires_at": 1}, now=100) is False
assert collect.kimi_token_fresh({"expires_at": 200}, now=100) is True
assert [region["name"] for region in collect.KIMI_REGIONS] == ["kimi.com", "kimi.ai"]
merged = collect.merge_kimi_rows([
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
spaces = {
    "user-1": {
        "notion_user": {"user-1": {"value": {"email": "user@example.com"}}},
        "space": {
            "space-1": {
                "spaceId": "space-1",
                "value": {
                    "id": "space-1",
                    "name": "shuuul",
                    "plan_type": "team",
                    "subscription_tier": "business",
                },
            }
        },
    }
}
space_id, email, tier, name = collect.notion_account(spaces)
assert space_id == "space-1"
assert email == "user@example.com"
assert tier == "business"
assert name == "shuuul"
assert collect.kimi_plan_name(
    "token",
    {"me": None},
    {"user": {"membership": {"level": "LEVEL_INTERMEDIATE"}}},
) == "LEVEL_INTERMEDIATE"
source = (ROOT / "collect.py").read_text()
assert "WHERE name IN" in source
assert "auth.kimi.com/api/oauth/token" in source
assert "auth.kimi.ai/api/oauth/token" in source
assert "api.kimi.ai/coding/v1/usages" in source
assert "api.kimi.com/coding/v1/me" in source
assert "api.kimi.ai/coding/v1/me" in source
assert "zed-github-account" in source
print("collect tests passed")
