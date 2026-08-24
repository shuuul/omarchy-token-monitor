#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
source = "\n".join(path.read_text() for path in (ROOT / "collector").rglob("*.py"))
assert "WHERE name IN" in source
assert "auth.kimi.com/api/oauth/token" in source
assert "auth.kimi.ai/api/oauth/token" in source
assert "api.kimi.ai/coding/v1/usages" in source
assert "api.kimi.com/coding/v1/me" in source
assert "api.kimi.ai/coding/v1/me" in source
assert "cli-chat-proxy.grok.com/v1/settings" in source
assert "cli-chat-proxy.grok.com/v1/billing?format=credits" in source
assert "cursor.com/api/dashboard/get-sand-usage-status" in source
assert "GROK_OAUTH_TOKEN" in source
assert '"Weekly"' in source
assert "Codex Spark" in source
assert "accounts.x.ai/api/auth/session" in source
assert "zed-github-account" in source
assert "api.factory.ai/api/billing/limits" in source
assert "Factory CLI" in source
assert "auth.v2.keyring" in source
print("collector source tests passed")
