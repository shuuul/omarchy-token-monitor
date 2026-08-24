from __future__ import annotations

import json
import re
from collector.http import http
from collector.schema import iso_now, row, window
from collector.security import MAX_CREDENTIAL_BYTES, bounded_secret, run_bounded

MAX_ZED_RESPONSE_BYTES = 512 * 1024
MAX_KEYRING_LIST_BYTES = 256 * 1024

def zed_keyring_items() -> list[tuple[str, str]]:
    dest = "org.freedesktop.secrets"
    collection = "/org/freedesktop/secrets/collection/Default_5fkeyring"
    listing = run_bounded(
        ["busctl", "--user", "get-property", dest, collection, "org.freedesktop.Secret.Collection", "Items"],
        timeout=5,
        max_bytes=MAX_KEYRING_LIST_BYTES,
        text=True,
    )
    if listing.returncode != 0:
        return []
    paths = re.findall(r'"(/org/freedesktop/secrets/collection/[^"]+)"', listing.stdout)[:128]
    found = []
    for path in paths:
        label = run_bounded(
            ["busctl", "--user", "get-property", dest, path, "org.freedesktop.Secret.Item", "Label"],
            timeout=5,
            max_bytes=MAX_KEYRING_LIST_BYTES,
            text=True,
        )
        if "zed-github-account" not in label.stdout:
            continue
        attrs = run_bounded(
            ["busctl", "--user", "get-property", dest, path, "org.freedesktop.Secret.Item", "Attributes"],
            timeout=5,
            max_bytes=MAX_KEYRING_LIST_BYTES,
            text=True,
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
    secret = run_bounded(
        ["secret-tool", "lookup", "url", url],
        timeout=8,
        max_bytes=MAX_CREDENTIAL_BYTES,
    )
    if secret.returncode != 0 or not secret.stdout:
        return row("zed", source="keyring", error="Could not read the Zed keyring item.")
    token = bounded_secret(secret.stdout.decode(errors="replace"))
    user_id = bounded_secret(user_id)
    if not token or not user_id:
        return row("zed", source="keyring", error="The Zed keyring item exceeds the credential limit.")
    status, body, _ = http(
        "https://cloud.zed.dev/client/users/me",
        headers={
            "Authorization": f"{user_id} {token}",
            "Accept": "application/json",
        },
        max_bytes=MAX_ZED_RESPONSE_BYTES,
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
