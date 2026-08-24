from __future__ import annotations

import json
from collector.cookies import cookie_header
from collector.http import http
from collector.schema import iso_from_unix, iso_now, row, window

MAX_NOTION_RESPONSE_BYTES = 2 * 1024 * 1024

def unwrap_record(raw):
    if not isinstance(raw, dict):
        return {}
    value = raw.get("value") if "value" in raw else raw
    if isinstance(value, dict) and isinstance(value.get("value"), dict):
        return value["value"]
    return value if isinstance(value, dict) else {}


def notion_account(spaces: dict) -> tuple[str | None, str | None, str | None, str | None]:
    rec = next(iter(spaces.values()), None)
    if not isinstance(rec, dict):
        return None, None, None, None
    email = None
    users = rec.get("notion_user") or {}
    first_user = next(iter(users.values()), None)
    user = unwrap_record(first_user)
    if user:
        email = user.get("email")
    space_map = rec.get("space") or {}
    chosen = None
    for raw in space_map.values():
        space = unwrap_record(raw)
        if not space:
            continue
        if chosen is None:
            chosen = space
        tier = str(space.get("subscription_tier") or "").lower()
        if tier in ("business", "enterprise"):
            chosen = space
            break
    if not chosen:
        return None, email, None, None
    return chosen.get("id"), email, chosen.get("subscription_tier"), chosen.get("name")


def fetch_notion(jars: dict) -> dict:
    header = cookie_header(jars, [("token_v2", [".app.notion.com", "app.notion.com", ".notion.so"])])
    if not header:
        return row("notion", source="chrome", error="Sign in to Notion in Chrome.")
    headers = {
        "Cookie": header,
        "Content-Type": "application/json",
        "Origin": "https://app.notion.com",
        "Referer": "https://app.notion.com/",
        "Accept": "application/json",
    }
    status, body, _ = http(
        "https://app.notion.com/api/v3/getSpaces",
        method="POST",
        headers=headers,
        body=b"{}",
        max_bytes=MAX_NOTION_RESPONSE_BYTES,
    )
    if status != 200:
        return row("notion", source="chrome", error=f"Notion getSpaces returned {status}.")
    spaces = json.loads(body)
    space_id, email, tier, workspace = notion_account(spaces)
    if not space_id:
        return row("notion", source="chrome", error="No Notion workspace found.")
    status, body, _ = http(
        "https://app.notion.com/api/v3/getCreditRateLimitStatus",
        method="POST",
        headers=headers,
        body=json.dumps({"spaceId": space_id}).encode(),
        max_bytes=MAX_NOTION_RESPONSE_BYTES,
    )
    if status != 200:
        return row("notion", source="chrome", error=f"Notion credit status returned {status}.")
    data = json.loads(body)
    rolling = data.get("window") or {}
    monthly = data.get("billingPeriodWindow") or {}
    monthly_reset = iso_from_unix((monthly.get("periodEndMs") or 0) / 1000) if monthly.get("periodEndMs") else None

    def pct(block: dict) -> float | None:
        limit = block.get("limit")
        used = block.get("used")
        if limit in (None, 0) or used is None:
            return None
        return float(used) / float(limit) * 100.0

    plan = str(tier or "").strip()
    usage = {
        "accountEmail": email,
        "loginMethod": plan or "Notion AI",
        "identity": {
            "providerID": "notion",
            "accountEmail": email,
            "accountOrganization": workspace,
            "plan": plan,
            "loginMethod": plan or "Notion AI",
        },
        "primary": window(pct(rolling), 360, None, "Rolling"),
        "secondary": window(pct(monthly), None, monthly_reset, "Monthly"),
        "updatedAt": iso_now(),
    }
    return row("notion", source="chrome", usage=usage)
