from __future__ import annotations

import json
import re
import subprocess
from collector.http import http
from collector.schema import iso_now, row, window

def zed_keyring_items() -> list[tuple[str, str]]:
    dest = "org.freedesktop.secrets"
    collection = "/org/freedesktop/secrets/collection/Default_5fkeyring"
    listing = subprocess.run(
        ["busctl", "--user", "get-property", dest, collection, "org.freedesktop.Secret.Collection", "Items"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    if listing.returncode != 0:
        return []
    paths = re.findall(r'"(/org/freedesktop/secrets/collection/[^"]+)"', listing.stdout)
    found = []
    for path in paths:
        label = subprocess.run(
            ["busctl", "--user", "get-property", dest, path, "org.freedesktop.Secret.Item", "Label"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if "zed-github-account" not in label.stdout:
            continue
        attrs = subprocess.run(
            ["busctl", "--user", "get-property", dest, path, "org.freedesktop.Secret.Item", "Attributes"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        url = re.search(r'"url"\s+"([^"]+)"', attrs.stdout)
        user = re.search(r'"username"\s+"([^"]+)"', attrs.stdout)
        if url and user:
            found.append((url.group(1), user.group(1)))
    return found


def fetch_zed() -> dict:
    items = zed_keyring_items()
    if not items:
        return row("zed", source="keyring", error="Sign in to Zed (Command Palette → client: sign in).")
    url, user_id = items[0]
    secret = subprocess.run(
        ["secret-tool", "lookup", "url", url],
        capture_output=True,
        timeout=8,
        check=False,
    )
    if secret.returncode != 0 or not secret.stdout:
        return row("zed", source="keyring", error="Could not read the Zed keyring item.")
    token = secret.stdout.decode().rstrip("\n")
    status, body, _ = http(
        "https://cloud.zed.dev/client/users/me",
        headers={
            "Authorization": f"{user_id} {token}",
            "Accept": "application/json",
        },
    )
    if status != 200:
        return row("zed", source="keyring", error=f"Zed cloud API returned {status}.")
    data = json.loads(body)
    user = data.get("user") or {}
    plan = data.get("plan") or {}
    predictions = (plan.get("usage") or {}).get("edit_predictions") or {}
    used = predictions.get("used")
    limit = predictions.get("limit")
    used_percent = None
    label = "Edit predictions"
    if isinstance(limit, str) and limit.lower() == "unlimited":
        used_percent = 0
        label = f"Unlimited ({used or 0} used)"
    elif limit not in (None, 0) and used is not None:
        used_percent = float(used) / float(limit) * 100.0
        label = f"{used} / {limit} predictions"
    period = plan.get("subscription_period") or {}
    usage = {
        "accountEmail": user.get("github_login"),
        "loginMethod": plan.get("plan_v3") or plan.get("plan") or "",
        "identity": {
            "providerID": "zed",
            "accountEmail": user.get("github_login"),
            "plan": plan.get("plan_v3") or plan.get("plan") or "",
            "loginMethod": plan.get("plan_v3") or plan.get("plan") or "",
        },
        "primary": window(used_percent, None, period.get("ended_at"), label),
        "updatedAt": iso_now(),
    }
    return row("zed", source="keyring", usage=usage)
