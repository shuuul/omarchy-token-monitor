from __future__ import annotations

import json
import os
import struct
from datetime import datetime, timezone
from pathlib import Path
from collector.cookies import HOME, cookie_header
from collector.http import http
from collector.schema import iso_from_unix, iso_now, row, window

def parse_grok_grpc(payload: bytes) -> dict:
    # grpc-web: 1-byte flag + 4-byte big-endian length + protobuf message + trailers
    if len(payload) < 5:
        raise ValueError("empty grok payload")
    length = int.from_bytes(payload[1:5], "big")
    message = payload[5:5 + length]
    floats: list[float] = []
    resets: list[int] = []

    def read_varint(buf: bytes, index: int) -> tuple[int, int]:
        shift = 0
        value = 0
        while index < len(buf):
            byte = buf[index]
            index += 1
            value |= (byte & 0x7F) << shift
            if byte < 0x80:
                return value, index
            shift += 7
        raise ValueError("truncated varint")

    def walk(buf: bytes, path: list[int]) -> None:
        index = 0
        while index < len(buf):
            key, index = read_varint(buf, index)
            field = key >> 3
            wire = key & 7
            field_path = path + [field]
            if wire == 0:
                value, index = read_varint(buf, index)
                if 1_700_000_000 <= value <= 2_100_000_000:
                    resets.append(int(value))
            elif wire == 2:
                size, index = read_varint(buf, index)
                walk(buf[index:index + size], field_path)
                index += size
            elif wire == 5:
                bits = struct.unpack_from("<I", buf, index)[0]
                number = struct.unpack("<f", struct.pack("<I", bits))[0]
                if 0 <= number <= 100:
                    floats.append(number)
                index += 4
            elif wire == 1:
                index += 8
            else:
                break

    walk(message, [])
    used = floats[0] if floats else 0.0
    now = datetime.now(timezone.utc).timestamp()
    future = [ts for ts in resets if ts > now]
    reset_at = iso_from_unix(min(future) if future else (min(resets) if resets else None))
    return used, reset_at


GROK_OIDC_SCOPE_PREFIX = "https://auth.x.ai::"
GROK_LEGACY_SCOPE = "https://accounts.x.ai/sign-in"


def grok_home() -> Path:
    custom = str(os.environ.get("GROK_HOME") or "").strip()
    return Path(custom).expanduser() if custom else HOME / ".grok"


def grok_parse_stamp(raw) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    if "." in text:
        head, rest = text.split(".", 1)
        digits = ""
        tz = ""
        for index, char in enumerate(rest):
            if char.isdigit():
                digits += char
            else:
                tz = rest[index:]
                break
        text = f"{head}.{(digits + '000000')[:6]}{tz}"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def grok_iso(stamp: datetime | None) -> str | None:
    if stamp is None:
        return None
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def grok_env_token() -> str | None:
    raw = str(os.environ.get("GROK_OAUTH_TOKEN") or "").strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw or raw.lower().startswith(("cookie:", "xai-")) or "=" in raw:
        return None
    return raw


def grok_select_auth_entry(root: dict) -> tuple[str, dict] | None:
    oidc = None
    legacy = None
    for scope, value in (root or {}).items():
        if not isinstance(value, dict):
            continue
        key = str(value.get("key") or "").strip()
        if not key:
            continue
        scope_text = str(scope or "")
        if scope_text.startswith(GROK_OIDC_SCOPE_PREFIX):
            oidc = (scope_text, value)
        elif scope_text == GROK_LEGACY_SCOPE or "/sign-in" in scope_text:
            legacy = (scope_text, value)
    return oidc or legacy


def grok_credentials_from_entry(scope: str, entry: dict) -> dict:
    expires = grok_parse_stamp(entry.get("expires_at"))
    now = datetime.now(timezone.utc)
    return {
        "scope": scope,
        "access_token": str(entry.get("key") or "").strip(),
        "auth_mode": str(entry.get("auth_mode") or "").strip(),
        "email": str(entry.get("email") or "").strip() or None,
        "principal_type": str(entry.get("principal_type") or "").strip() or None,
        "expires_at": grok_iso(expires),
        "expired": bool(expires and expires <= now),
    }


def grok_load_credentials() -> dict | None:
    token = grok_env_token()
    if token:
        return {
            "scope": GROK_OIDC_SCOPE_PREFIX,
            "access_token": token,
            "auth_mode": "oidc",
            "email": None,
            "principal_type": None,
            "expires_at": None,
            "expired": False,
        }
    path = grok_home() / "auth.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    selected = grok_select_auth_entry(data)
    if not selected:
        return None
    return grok_credentials_from_entry(*selected)


def grok_login_method(creds: dict | None) -> str:
    if not creds:
        return ""
    mode = str(creds.get("auth_mode") or "").strip().lower()
    if mode == "oidc" or str(creds.get("scope") or "").startswith(GROK_OIDC_SCOPE_PREFIX):
        return "SuperGrok"
    if mode == "session":
        return "session"
    return grok_pretty_plan(str(creds.get("auth_mode") or ""))


def grok_pretty_plan(raw: str) -> str:
    compact = "".join(ch for ch in raw.lower() if ch.isalnum() or ch == "+")
    letters = "".join(ch for ch in compact if ch.isalpha())
    if letters in ("supergrokheavy", "heavy") or compact in ("supergrokheavy", "heavy"):
        return "SuperGrok Heavy"
    if letters == "supergrokplus" or compact in ("supergrok+", "supergrokplus"):
        return "SuperGrok Plus"
    if letters in ("supergroklite", "lite"):
        return "SuperGrok Lite"
    if letters == "supergrok":
        return "SuperGrok"
    if compact in ("premium+", "xpremium+", "premiumplus", "xpremiumplus") or letters in ("premiumplus", "xpremiumplus"):
        return "X Premium+"
    if letters in ("premium", "xpremium"):
        return "X Premium"
    if letters in ("free", "none"):
        return ""
    return raw.strip()


def grok_bearer_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "x-xai-token-auth": "xai-grok-cli",
        "Accept": "application/json",
    }


def grok_settings_plan_from_body(body: bytes | str) -> str:
    try:
        data = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return grok_pretty_plan(str(data.get("subscription_tier_display") or ""))


def grok_oauth_settings_plan(token: str) -> str:
    status, body, _ = http(
        "https://cli-chat-proxy.grok.com/v1/settings",
        headers=grok_bearer_headers(token),
        timeout=2,
    )
    if status != 200:
        return ""
    return grok_settings_plan_from_body(body)


def grok_settings_plan(header: str) -> str:
    status, body, _ = http(
        "https://cli-chat-proxy.grok.com/v1/settings",
        headers={"Cookie": header, "Accept": "application/json"},
        timeout=8,
    )
    if status != 200:
        return ""
    return grok_settings_plan_from_body(body)


def grok_session_plan(header: str) -> tuple[str, str | None]:
    status, body, _ = http(
        "https://accounts.x.ai/api/auth/session",
        headers={
            "Cookie": header,
            "Accept": "application/json",
            "Origin": "https://accounts.x.ai",
            "Referer": "https://accounts.x.ai/",
        },
        timeout=8,
    )
    if status != 200:
        return "", None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return "", None
    session = data.get("session") or {}
    email = session.get("email")
    plan = grok_pretty_plan(str(session.get("xSubscriptionType") or ""))
    return plan, email


def grok_plan_name(header: str, creds: dict | None = None) -> tuple[str, str | None]:
    billed, email = grok_session_plan(header)
    settings = grok_settings_plan(header)
    oauth_plan = ""
    if creds and not creds.get("expired") and creds.get("access_token"):
        oauth_plan = grok_oauth_settings_plan(str(creds["access_token"]))
    plan = oauth_plan or settings or grok_login_method(creds) or billed
    if creds and creds.get("email"):
        email = creds.get("email")
    return plan, email


def grok_parse_billing(body: bytes | str) -> tuple[float, str | None] | None:
    try:
        data = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    config = data.get("config") if isinstance(data.get("config"), dict) else {}
    period = config.get("currentPeriod") if isinstance(config.get("currentPeriod"), dict) else {}
    reset_at = grok_iso(grok_parse_stamp(period.get("end") or config.get("billingPeriodEnd")))
    percent = config.get("creditUsagePercent")
    if isinstance(percent, (int, float)):
        return max(0.0, min(100.0, float(percent))), reset_at
    cap = ((config.get("onDemandCap") or {}).get("val") if isinstance(config.get("onDemandCap"), dict) else None)
    used = ((config.get("onDemandUsed") or {}).get("val") if isinstance(config.get("onDemandUsed"), dict) else None)
    if isinstance(cap, (int, float)) and cap > 0 and isinstance(used, (int, float)):
        return max(0.0, min(100.0, float(used) / float(cap) * 100.0)), reset_at
    if reset_at:
        return 0.0, reset_at
    return None


def grok_oauth_billing(token: str) -> tuple[float, str | None] | None:
    status, body, _ = http(
        "https://cli-chat-proxy.grok.com/v1/billing?format=credits",
        headers=grok_bearer_headers(token),
        timeout=15,
    )
    if status != 200:
        return None
    return grok_parse_billing(body)


def grok_usage_row(source: str, used: float, reset_at: str | None, plan: str, email: str | None) -> dict:
    usage = {
        "loginMethod": plan,
        "identity": {
            "providerID": "grok",
            "accountEmail": email,
            "plan": plan,
            "loginMethod": plan,
        },
        "primary": window(used, None, reset_at, "Weekly"),
        "updatedAt": iso_now(),
    }
    if email:
        usage["accountEmail"] = email
    return row("grok", source=source, usage=usage)


def fetch_grok(jars: dict) -> dict:
    creds = grok_load_credentials()
    token = str((creds or {}).get("access_token") or "")
    if creds and not creds.get("expired") and token:
        billing = grok_oauth_billing(token)
        if billing is not None:
            used, reset_at = billing
            plan = grok_oauth_settings_plan(token) or grok_login_method(creds)
            return grok_usage_row("oauth", used, reset_at, plan, creds.get("email"))

    header = cookie_header(jars, [("sso", [".grok.com", "grok.com", ".x.ai"]), ("sso-rw", [".grok.com", "grok.com", ".x.ai"])])
    if not header:
        if creds and creds.get("expired"):
            return row("grok", source="oauth", error="Grok login expired. Run `grok login`.")
        return row("grok", source="chrome", error="Run `grok login`, or sign in to grok.com in Chrome.")
    status, body, _ = http(
        "https://grok.com/grok_api_v2.GrokBuildBilling/GetGrokCreditsConfig",
        method="POST",
        headers={
            "Cookie": header,
            "Origin": "https://grok.com",
            "Referer": "https://grok.com/?_s=usage",
            "Content-Type": "application/grpc-web+proto",
            "x-grpc-web": "1",
            "Accept": "*/*",
        },
        body=b"\x00\x00\x00\x00\x00",
    )
    if status != 200:
        return row("grok", source="chrome", error=f"Grok billing returned {status}.")
    try:
        used, reset_at = parse_grok_grpc(body)
    except Exception:
        return row("grok", source="chrome", error="Could not parse Grok billing payload.")
    plan, email = grok_plan_name(header, creds)
    return grok_usage_row("chrome", used, reset_at, plan, email)
