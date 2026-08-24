from __future__ import annotations

import json
from collector.cookies import cookie_header
from collector.http import http
from collector.schema import iso_now, row, window

MAX_CURSOR_RESPONSE_BYTES = 512 * 1024

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
        "updatedAt": iso_now(),
    }
    return row("cursor", source="chrome", usage=usage)
