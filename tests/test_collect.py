#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("collect", ROOT / "collect.py")
collect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collect)

text = """
Signed in as user@example.com (example)
**Amp Free:** 99% remaining today (resets daily)
**Amp Megawatt Subscription:** 95% other usage and 97% orb usage remaining - resets upon renewal in 6 days
**Individual credits:** $3.23 remaining
"""
parsed = collect.parse_amp_text(text)
assert parsed["provider"] == "amp"
assert parsed["usage"]["primary"]["usedPercent"] == 1
assert parsed["usage"]["secondary"]["usedPercent"] == 5
assert parsed["usage"]["secondary"]["label"] == "Token Usage"
assert parsed["usage"]["tertiary"]["usedPercent"] == 3
assert parsed["credits"]["remaining"] == 3.23

payload = bytes.fromhex("0000000056") + b"\nT" + b"\r\x00\x00\x82B"
# The live parser is covered by the live collector; keep a structural check here.
row = collect.row("grok", source="chrome", error="x")
assert row["error"]["message"] == "x"
assert collect.kimi_token_fresh({"expires_at": 1}, now=100) is False
assert collect.kimi_token_fresh({"expires_at": 200}, now=100) is True
assert [region["name"] for region in collect.KIMI_REGIONS] == ["kimi.com", "kimi.ai"]
assert collect.requested_providers({}, ["grok"]) == ("grok",)
assert collect.requested_providers({"only": "codex"}, []) == ("codex",)
assert collect.requested_providers({"only": "factory"}, []) == ("factory",)
assert collect.requested_providers({}, []) == collect.PROVIDERS
assert collect.PROVIDERS[-1] == "factory"
assert collect.factory_api_key_from_dotenv("export FACTORY_API_KEY='abc'") == "abc"
assert collect.factory_plan_name({
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
usage, credits = collect.factory_usage_from_payloads(auth, limits, None, None)
assert usage["primary"]["label"] == "5h"
assert usage["primary"]["usedPercent"] == 2
assert usage["secondary"]["label"] == "Weekly"
assert usage["tertiary"]["label"] == "Monthly"
assert [extra["title"] for extra in usage["extraRateWindows"]] == ["Core 5h", "Core 7-day", "Core Monthly"]
assert usage["extraRateWindows"][0]["window"]["usedPercent"] == 0
assert "Factory Team Annual" in usage["loginMethod"]
assert credits["remaining"] == 0
assert credits["label"] == "Extra usage"
legacy_usage, _ = collect.factory_usage_from_payloads(auth, None, {
    "usage": {
        "endDate": 1800864000000,
        "standard": {"userTokens": 40, "totalAllowance": 100, "usedRatio": 0.4},
        "premium": {"userTokens": 10, "totalAllowance": 100, "usedRatio": 0.1},
    }
}, None)
assert legacy_usage["primary"]["label"] == "Standard"
assert legacy_usage["primary"]["usedPercent"] == 40
assert legacy_usage["secondary"]["label"] == "Premium"
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
                    "name": "Example",
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
assert name == "Example"
used, reset_at = collect.parse_grok_grpc(bytes.fromhex("0000000000"))
assert used == 0.0
assert reset_at is None
assert collect.grok_pretty_plan("Premium") == "X Premium"
assert collect.grok_pretty_plan("Premium+") == "X Premium+"
assert collect.grok_pretty_plan("SuperGrok Heavy") == "SuperGrok Heavy"
assert collect.grok_pretty_plan("") == ""
assert collect.grok_login_method({"auth_mode": "oidc", "scope": "https://auth.x.ai::cli"}) == "SuperGrok"
assert collect.grok_login_method({"auth_mode": "session"}) == "session"
assert collect.grok_env_token() is None
oidc, legacy = {
    "https://auth.x.ai::cli": {"key": "oidc-token", "auth_mode": "oidc", "email": "user@example.com"},
    "https://accounts.x.ai/sign-in": {"key": "legacy-token", "auth_mode": "session"},
}, None
scope, entry = collect.grok_select_auth_entry(oidc)
assert scope.startswith("https://auth.x.ai::")
assert entry["auth_mode"] == "oidc"
assert collect.grok_parse_billing(b'{"config":{"creditUsagePercent":12.5,"currentPeriod":{"end":"2026-09-01T00:00:00Z"}}}') == (
    12.5,
    "2026-09-01T00:00:00Z",
)
assert collect.grok_settings_plan_from_body(b'{"subscription_tier_display":"SuperGrok"}') == "SuperGrok"
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
assert "cli-chat-proxy.grok.com/v1/settings" in source
assert "cli-chat-proxy.grok.com/v1/billing?format=credits" in source
assert "GROK_OAUTH_TOKEN" in source
assert '"Weekly"' in source
assert "Codex Spark" in source
assert "accounts.x.ai/api/auth/session" in source
assert "zed-github-account" in source
assert "api.factory.ai/api/billing/limits" in source
assert "Factory CLI" in source
assert "auth.v2.keyring" in source
print("collect tests passed")
