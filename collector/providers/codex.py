from __future__ import annotations

import json
import os
from pathlib import Path
from collector.cookies import HOME
from collector.http import http
from collector.schema import iso_from_unix, iso_now, row, window
from collector.security import bounded_secret, read_json

MAX_CODEX_RESPONSE_BYTES = 512 * 1024

def fetch_codex() -> dict:
    auth_path = Path(os.environ.get("CODEX_HOME", HOME / ".codex")) / "auth.json"
    if not auth_path.exists():
        return row("codex", source="oauth", error="Sign in with `codex login`.")
    auth = read_json(auth_path)
    tokens = auth.get("tokens") or {}
    access = bounded_secret(tokens.get("access_token"))
    if not access:
        return row("codex", source="oauth", error="Codex auth.json has no access token.")
    headers = {
        "Authorization": f"Bearer {access}",
        "Accept": "application/json",
    }
    account = bounded_secret(tokens.get("account_id"))
    if account:
        headers["ChatGPT-Account-ID"] = account
    status, body, _ = http(
        "https://chatgpt.com/backend-api/wham/usage",
        headers=headers,
        max_bytes=MAX_CODEX_RESPONSE_BYTES,
    )
    if status != 200:
        return row("codex", source="oauth", error=f"Codex usage API returned {status}.")
    data = json.loads(body)
    rate = data.get("rate_limit") or {}

    def map_window(raw: dict | None, label: str) -> dict | None:
        if not raw:
            return None
        minutes = None
        seconds = raw.get("limit_window_seconds")
        if seconds:
            minutes = int(seconds) // 60
        return window(raw.get("used_percent"), minutes, iso_from_unix(raw.get("reset_at")), label)

    extras = []
    for extra in data.get("additional_rate_limits") or []:
        extra_rate = extra.get("rate_limit") or {}
        title = extra.get("display_name") or extra.get("limit_name") or extra.get("model") or "Extra"
        if "spark" in title.lower():
            title = "Codex Spark"
        primary = map_window(extra_rate.get("primary_window"), f"{title} Session")
        secondary = map_window(extra_rate.get("secondary_window"), f"{title} Weekly")
        if primary:
            extras.append({"id": extra.get("id") or "extra", "title": primary["label"], "window": primary})
        if secondary:
            extras.append({"id": extra.get("id") or "extra-weekly", "title": secondary["label"], "window": secondary})
    usage = {
        "accountEmail": data.get("email"),
        "loginMethod": data.get("plan_type") or "",
        "identity": {
            "accountEmail": data.get("email"),
            "plan": data.get("plan_type") or "",
            "loginMethod": data.get("plan_type") or "",
            "providerID": "codex",
        },
        "primary": map_window(rate.get("primary_window"), "Weekly" if (rate.get("primary_window") or {}).get("limit_window_seconds", 0) >= 6 * 24 * 3600 else "Session"),
        "secondary": map_window(rate.get("secondary_window"), "Weekly"),
        "tertiary": None,
        "extraRateWindows": extras,
        "updatedAt": iso_now(),
    }
    credits = None
    credit_info = data.get("credits") or {}
    if isinstance(credit_info, dict) and credit_info.get("remaining") is not None:
        credits = {"remaining": credit_info.get("remaining"), "updatedAt": iso_now()}
    return row("codex", source="oauth", usage=usage, credits=credits)
