from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path
from collector.cookies import HOME, cookie_value
from collector.http import http
from collector.schema import iso_now, row, window

KIMI_CLIENT_ID = "17e5f671-d194-4dfb-9706-5516cb48c098"
KIMI_REGIONS = (
    {
        "id": "cn",
        "name": "kimi.com",
        "oauth": "https://auth.kimi.com/api/oauth/token",
        "api": "https://api.kimi.com/coding/v1/usages",
        "me": "https://api.kimi.com/coding/v1/me",
        "cookie_hosts": ["www.kimi.com", ".kimi.com", "kimi.com", ".www.kimi.com"],
        "cred_names": ("kimi-code.json",),
    },
    {
        "id": "ai",
        "name": "kimi.ai",
        "oauth": "https://auth.kimi.ai/api/oauth/token",
        "api": "https://api.kimi.ai/coding/v1/usages",
        "me": "https://api.kimi.ai/coding/v1/me",
        "cookie_hosts": ["www.kimi.ai", ".kimi.ai", "kimi.ai", ".www.kimi.ai"],
        "cred_names": (),
    },
)


def kimi_token_fresh(creds: dict, now: float | None = None) -> bool:
    expires_at = creds.get("expires_at")
    if not expires_at:
        return False
    now = time.time() if now is None else now
    return float(expires_at) - now > 60


def write_kimi_creds(path: Path, creds: dict) -> None:
    path.parent.mkdir(mode=0o700, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(creds, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(path)


def refresh_kimi_creds(creds: dict, oauth_url: str) -> dict | None:
    refresh = creds.get("refresh_token")
    if not refresh:
        return None
    body = urllib.parse.urlencode({
        "client_id": KIMI_CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh,
    }).encode()
    status, raw, _ = http(
        oauth_url,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        body=body,
    )
    if status != 200:
        return None
    data = json.loads(raw)
    if not data.get("access_token"):
        return None
    expires_in = int(data.get("expires_in") or 900)
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or refresh,
        "expires_at": int(time.time()) + expires_in,
        "scope": data.get("scope") or creds.get("scope") or "kimi-code",
        "token_type": data.get("token_type") or "Bearer",
        "expires_in": expires_in,
    }


def kimi_plan_name(token: str, region: dict, usage_data: dict) -> str:
    """Prefer /me user_level_name. membership.level is a coarse bucket, not the billed tier."""
    me_url = region.get("me")
    if me_url:
        status, body, _ = http(
            me_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if status == 200:
            try:
                me = json.loads(body)
            except json.JSONDecodeError:
                me = {}
            name = str(me.get("user_level_name") or "").strip()
            if name:
                return name
    return str(((usage_data.get("user") or {}).get("membership") or {}).get("level") or "")


def kimi_usage_from_token(token: str, source: str, region: dict) -> dict:
    status, body, _ = http(
        region["api"],
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if status != 200:
        return row("kimi", source=source, error=f"{region['name']} token expired. Run `kimi login`.")
    data = json.loads(body)
    weekly = data.get("usage") or {}
    rolling = None
    for item in data.get("limits") or []:
        rolling = (item or {}).get("detail") or rolling

    def from_counts(block: dict | None, label: str, minutes: int | None) -> dict | None:
        if not block:
            return None
        limit = float(block.get("limit") or 0)
        used = float(block.get("used") or 0)
        if limit <= 0:
            return None
        return window(used / limit * 100.0, minutes, block.get("resetTime"), label)

    site = region["name"]
    membership = kimi_plan_name(token, region, data)
    usage = {
        "loginMethod": membership or site,
        "identity": {
            "providerID": "kimi",
            "plan": membership,
            "loginMethod": membership or site,
            "accountOrganization": site,
        },
        "primary": from_counts(rolling, f"5-hour · {site}", 300),
        "secondary": from_counts(weekly, f"Weekly · {site}", 10080),
        "updatedAt": iso_now(),
    }
    return row("kimi", source=source, usage=usage)


def kimi_cred_files(region: dict) -> list[Path]:
    directory = HOME / ".kimi-code/credentials"
    if not directory.exists():
        return []
    names = set(region["cred_names"])
    if region["id"] == "ai":
        names.update(path.name for path in directory.glob("kimi-code-env-*.json"))
    return [directory / name for name in names if (directory / name).exists()]


def try_kimi_region(jars: dict, region: dict) -> dict | None:
    for cred_path in kimi_cred_files(region):
        creds = json.loads(cred_path.read_text())
        if not kimi_token_fresh(creds):
            refreshed = refresh_kimi_creds(creds, region["oauth"])
            if refreshed:
                write_kimi_creds(cred_path, refreshed)
                creds = refreshed
        token = creds.get("access_token")
        if not token:
            continue
        result = kimi_usage_from_token(token, "cli", region)
        if not result.get("error"):
            return result
    cookie = cookie_value(jars, "kimi-auth", region["cookie_hosts"])
    if cookie:
        result = kimi_usage_from_token(cookie, "chrome", region)
        if not result.get("error"):
            return result
    return None


def merge_kimi_rows(rows: list[dict]) -> dict:
    extras = []
    plan_parts = []
    sites = []
    binding_source = None
    for item in rows:
        usage = item.get("usage") or {}
        identity = usage.get("identity") or {}
        plan_parts.append(identity.get("plan") or usage.get("loginMethod") or "")
        if identity.get("accountOrganization"):
            sites.append(identity["accountOrganization"])
        for key in ("primary", "secondary", "tertiary"):
            win = usage.get(key)
            if win:
                extras.append({"id": f"{item.get('source')}-{key}", "title": win.get("label") or key, "window": win})
        if not binding_source:
            binding_source = item.get("source")
    plan = " + ".join(part for part in plan_parts if part)
    if sites:
        plan = (plan + " · " if plan else "") + " + ".join(sites)
    usage = {
        "loginMethod": plan or "Kimi Code",
        "identity": {"providerID": "kimi", "plan": plan, "loginMethod": plan or "Kimi Code"},
        "extraRateWindows": extras,
        "updatedAt": iso_now(),
    }
    return row("kimi", source=binding_source or "cli", usage=usage)


def fetch_kimi(jars: dict) -> dict:
    found = []
    missing = []
    for region in KIMI_REGIONS:
        result = try_kimi_region(jars, region)
        if result:
            found.append(result)
        else:
            missing.append(region["name"])
    if found:
        return merge_kimi_rows(found)
    sites = " and ".join(missing) if missing else "kimi.com and kimi.ai"
    return row("kimi", source="cli", error=f"Sign in with `kimi login`, or open {sites} in Chrome.")
