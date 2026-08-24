from __future__ import annotations

import json
from datetime import datetime

from collector.cookies import cookie_header
from collector.http import http
from collector.schema import iso_now, row, window

MAX_CURSOR_RESPONSE_BYTES = 512 * 1024


def _cursor_stamp(raw: str | None) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def cursor_grok_bot_window(body: bytes | str) -> dict | None:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("hasNonZeroIncludedLimit") is not True:
        return None
    used = data.get("usagePercent")
    if not isinstance(used, (int, float)) or isinstance(used, bool):
        return None
    start = _cursor_stamp(data.get("currentPeriodStart"))
    end = _cursor_stamp(data.get("nextResetTimestampUtc"))
    minutes = None
    if start and end:
        minutes = round((end - start).total_seconds() / 60)
        if minutes <= 0:
            minutes = None
    return {
        "id": "cursor-grok-bot",
        "title": "Grok Bot",
        "window": window(max(0, min(100, used)), minutes, data.get("nextResetTimestampUtc"), "Grok Bot"),
    }


def fetch_cursor(jars: dict) -> dict:
    header = cookie_header(jars, [("WorkosCursorSessionToken", ["cursor.com"])])
    if not header:
        return row("cursor", source="chrome", error="Sign in to cursor.com in Chrome.")
    headers = {"Cookie": header, "Accept": "application/json"}
    status, body, _ = http(
        "https://cursor.com/api/usage-summary",
        headers=headers,
        max_bytes=MAX_CURSOR_RESPONSE_BYTES,
    )
    if status != 200:
        return row("cursor", source="chrome", error=f"Cursor usage-summary returned {status}.")
    data = json.loads(body)
    me_status, me_body, _ = http(
        "https://cursor.com/api/auth/me",
        headers=headers,
        max_bytes=MAX_CURSOR_RESPONSE_BYTES,
    )
    email = None
    if me_status == 200:
        email = (json.loads(me_body) or {}).get("email")
    sand_status, sand_body, _ = http(
        "https://cursor.com/api/dashboard/get-sand-usage-status",
        method="POST",
        headers={
            **headers,
            "Content-Type": "application/json",
            "Origin": "https://cursor.com",
            "Referer": "https://cursor.com/dashboard?tab=usage",
        },
        body=b"{}",
        max_bytes=MAX_CURSOR_RESPONSE_BYTES,
        timeout=5,
    )
    grok_bot = cursor_grok_bot_window(sand_body) if sand_status == 200 else None
    plan = ((data.get("individualUsage") or {}).get("plan")) or {}
    cycle_end = data.get("billingCycleEnd")
    usage = {
        "accountEmail": email,
        "loginMethod": data.get("membershipType") or "",
        "identity": {
            "accountEmail": email,
            "plan": data.get("membershipType") or "",
            "loginMethod": data.get("membershipType") or "",
            "providerID": "cursor",
        },
        "primary": window(plan.get("totalPercentUsed"), None, cycle_end, "Plan"),
        "secondary": window(plan.get("autoPercentUsed"), None, cycle_end, "Cursor models"),
        "tertiary": window(plan.get("apiPercentUsed"), None, cycle_end, "Third-party"),
        "extraRateWindows": [grok_bot] if grok_bot else [],
        "updatedAt": iso_now(),
    }
    return row("cursor", source="chrome", usage=usage)
