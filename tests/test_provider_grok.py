#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers.grok import (grok_env_token, grok_login_method, grok_parse_billing, grok_pretty_plan, grok_select_auth_entry, grok_settings_plan_from_body, parse_grok_grpc)


used, reset_at = parse_grok_grpc(bytes.fromhex("0000000000"))
assert used == 0.0
assert reset_at is None
assert grok_pretty_plan("Premium") == "X Premium"
assert grok_pretty_plan("Premium+") == "X Premium+"
assert grok_pretty_plan("SuperGrok Heavy") == "SuperGrok Heavy"
assert grok_pretty_plan("") == ""
assert grok_login_method({"auth_mode": "oidc", "scope": "https://auth.x.ai::cli"}) == "SuperGrok"
assert grok_login_method({"auth_mode": "session"}) == "session"
assert grok_env_token() is None
oidc = {
    "https://auth.x.ai::cli": {"key": "oidc-token", "auth_mode": "oidc", "email": "user@example.com"},
    "https://accounts.x.ai/sign-in": {"key": "legacy-token", "auth_mode": "session"},
}
scope, entry = grok_select_auth_entry(oidc)
assert scope.startswith("https://auth.x.ai::")
assert entry["auth_mode"] == "oidc"
assert grok_parse_billing(b'{"config":{"creditUsagePercent":12.5,"currentPeriod":{"end":"2026-09-01T00:00:00Z"}}}') == (
    12.5,
    "2026-09-01T00:00:00Z",
)
assert grok_settings_plan_from_body(b'{"subscription_tier_display":"SuperGrok"}') == "SuperGrok"
print("grok collector tests passed")
