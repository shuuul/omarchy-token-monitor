from __future__ import annotations

import base64
import ctypes
import ctypes.util
import json
import os
import re
import subprocess
import time
import urllib.parse
from datetime import datetime, timezone
from collector.cookies import HOME, FACTORY_COOKIE_HOSTS, FACTORY_COOKIE_NAMES, cookie_header, cookie_value
from collector.http import http
from collector.schema import iso_from_unix, iso_now, row, window

FACTORY_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://app.factory.ai",
    "Referer": "https://app.factory.ai/",
    "x-factory-client": "web-app",
}

def factory_api_key_from_dotenv(text: str) -> str | None:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != "FACTORY_API_KEY":
            continue
        value = value.strip()
        if (value.startswith("\"") and value.endswith("\"")) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        value = value.strip()
        return value or None
    return None


def factory_api_key() -> str | None:
    env = str(os.environ.get("FACTORY_API_KEY") or "").strip()
    if env:
        return env
    path = HOME / ".factory" / ".env"
    if not path.exists():
        return None
    return factory_api_key_from_dotenv(path.read_text())


def aes256_gcm_decrypt(key: bytes, iv: bytes, tag: bytes, ciphertext: bytes) -> bytes | None:
    libname = ctypes.util.find_library("crypto")
    if not libname:
        return None
    lib = ctypes.CDLL(libname)
    lib.EVP_CIPHER_CTX_new.restype = ctypes.c_void_p
    lib.EVP_CIPHER_CTX_free.argtypes = [ctypes.c_void_p]
    lib.EVP_aes_256_gcm.restype = ctypes.c_void_p
    lib.EVP_DecryptInit_ex.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    lib.EVP_DecryptInit_ex.restype = ctypes.c_int
    lib.EVP_CIPHER_CTX_ctrl.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    lib.EVP_CIPHER_CTX_ctrl.restype = ctypes.c_int
    lib.EVP_DecryptUpdate.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_void_p, ctypes.c_int]
    lib.EVP_DecryptUpdate.restype = ctypes.c_int
    lib.EVP_DecryptFinal_ex.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
    lib.EVP_DecryptFinal_ex.restype = ctypes.c_int
    evp_ctrl_aead_set_ivlen = 0x9
    evp_ctrl_aead_set_tag = 0x11
    ctx = lib.EVP_CIPHER_CTX_new()
    if not ctx:
        return None
    try:
        cipher = lib.EVP_aes_256_gcm()
        if not cipher:
            return None
        if lib.EVP_DecryptInit_ex(ctx, cipher, None, None, None) != 1:
            return None
        if lib.EVP_CIPHER_CTX_ctrl(ctx, evp_ctrl_aead_set_ivlen, len(iv), None) != 1:
            return None
        if lib.EVP_DecryptInit_ex(ctx, None, None, key, iv) != 1:
            return None
        out = ctypes.create_string_buffer(len(ciphertext) + 16)
        outl = ctypes.c_int()
        if lib.EVP_DecryptUpdate(ctx, out, ctypes.byref(outl), ciphertext, len(ciphertext)) != 1:
            return None
        first = outl.value
        if lib.EVP_CIPHER_CTX_ctrl(ctx, evp_ctrl_aead_set_tag, len(tag), tag) != 1:
            return None
        extra = ctypes.c_int()
        if lib.EVP_DecryptFinal_ex(ctx, ctypes.byref(out, first), ctypes.byref(extra)) != 1:
            return None
        return out.raw[: first + extra.value]
    finally:
        lib.EVP_CIPHER_CTX_free(ctx)


def factory_cli_auth() -> dict | None:
    blob_path = HOME / ".factory" / "auth.v2.keyring"
    if not blob_path.exists():
        return None
    secret = subprocess.run(
        ["secret-tool", "lookup", "service", "Factory CLI", "account", "auth-encryption-key"],
        capture_output=True,
        timeout=8,
        check=False,
    )
    if secret.returncode != 0 or not secret.stdout:
        return None
    try:
        key = base64.b64decode(secret.stdout.decode().strip())
        iv_b64, tag_b64, ct_b64 = blob_path.read_text().strip().split(":")
        plain = aes256_gcm_decrypt(key, base64.b64decode(iv_b64), base64.b64decode(tag_b64), base64.b64decode(ct_b64))
        if not plain:
            return None
        data = json.loads(plain)
    except (ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def factory_jwt_claims(token: str | None) -> dict:
    if not token or token.count(".") < 2:
        return {}
    payload = token.split(".")[1]
    payload += "=" * ((4 - len(payload) % 4) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except (ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def factory_cookie_pairs() -> list[tuple[str, list[str]]]:
    return [(name, FACTORY_COOKIE_HOSTS) for name in FACTORY_COOKIE_NAMES]


def factory_session_header(jars: dict) -> str:
    return cookie_header(jars, factory_cookie_pairs())


def factory_bearer_from_cookies(jars: dict) -> str | None:
    for name in ("access-token", "__Secure-next-auth.session-token", "next-auth.session-token",
                 "__Secure-authjs.session-token", "authjs.session-token", "session"):
        value = cookie_value(jars, name, FACTORY_COOKIE_HOSTS)
        if value and "." in value:
            return value
    return cookie_value(jars, "access-token", FACTORY_COOKIE_HOSTS)


def factory_request(url: str, *, bearer: str | None = None, cookie: str | None = None) -> tuple[int, bytes]:
    headers = dict(FACTORY_HEADERS)
    if cookie:
        headers["Cookie"] = cookie
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    status, body, _ = http(url, headers=headers)
    return status, body


def factory_parse_date(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        return iso_from_unix(ts)
    text = str(value).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None:
        if numeric > 1e12:
            numeric /= 1000.0
        return iso_from_unix(numeric)
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def factory_used_percent(raw: dict | None) -> float | None:
    if not isinstance(raw, dict):
        return None
    used = raw.get("usedPercent")
    if isinstance(used, (int, float)):
        return max(0.0, min(100.0, float(used)))
    return None


def factory_window_from_limit(raw: dict | None, minutes: int | None, label: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    used = factory_used_percent(raw)
    if used is None:
        return None
    remaining = raw.get("secondsRemaining")
    reset_at = None
    if isinstance(remaining, (int, float)) and remaining > 0:
        reset_at = iso_from_unix(time.time() + float(remaining))
    else:
        reset_at = factory_parse_date(raw.get("windowEnd"))
        if reset_at and raw.get("secondsRemaining") is None:
            end = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
            if end <= datetime.now(timezone.utc):
                used = 0.0
    return window(used, minutes, reset_at, label)


def factory_ratio_percent(used: float | None, allowance: float | None, ratio: float | None) -> float:
    unlimited = 1_000_000_000_000
    if isinstance(ratio, (int, float)) and -0.001 <= float(ratio) <= 1.001:
        if not (float(ratio) == 0 and used and allowance and 0 < float(allowance) <= unlimited):
            return max(0.0, min(100.0, float(ratio) * 100.0))
    if isinstance(ratio, (int, float)) and (not allowance or float(allowance) > unlimited) and -0.1 <= float(ratio) <= 100.1:
        return max(0.0, min(100.0, float(ratio)))
    if allowance and float(allowance) > unlimited:
        return min(100.0, float(used or 0) / 100_000_000.0 * 100.0)
    if allowance and float(allowance) > 0 and used is not None:
        return min(100.0, float(used) / float(allowance) * 100.0)
    return 0.0


def factory_plan_name(auth: dict, extra: str | None = None) -> str:
    org = auth.get("organization") or {}
    sub = org.get("subscription") or {}
    orb = sub.get("orbSubscription") or {}
    plan = ((orb.get("plan") or {}).get("name") or "").strip()
    tier = str(sub.get("factoryTier") or "").strip()
    parts = []
    if tier:
        parts.append("Factory " + " ".join(piece.capitalize() for piece in re.split(r"[_\s]+", tier) if piece))
    if plan and "factory" not in plan.lower():
        parts.append(plan)
    elif plan and not parts:
        parts.append(plan)
    if extra:
        parts.append(extra)
    return " - ".join(parts)


def factory_email(auth: dict, bearer: str | None) -> str:
    profile = auth.get("userProfile") or {}
    email = str(profile.get("email") or "").strip()
    if email:
        return email
    return str(factory_jwt_claims(bearer).get("email") or "").strip()


def factory_usage_from_payloads(auth: dict, limits: dict | None, usage: dict | None, bearer: str | None) -> tuple[dict, dict | None]:
    email = factory_email(auth, bearer)
    org = (auth.get("organization") or {}).get("name") or ""
    identity = {
        "providerID": "factory",
        "accountEmail": email,
        "accountOrganization": org,
        "plan": factory_plan_name(auth),
        "loginMethod": factory_plan_name(auth),
    }
    out = {
        "accountEmail": email,
        "loginMethod": identity["loginMethod"],
        "identity": identity,
        "updatedAt": iso_now(),
        "extraRateWindows": [],
    }
    credits = None
    if isinstance(limits, dict) and limits.get("usesTokenRateLimitsBilling") and isinstance(limits.get("limits"), dict):
        pools = limits["limits"]
        standard = pools.get("standard") or {}
        out["primary"] = factory_window_from_limit(standard.get("fiveHour"), 300, "5h") or window(0, 300, None, "5h")
        out["secondary"] = factory_window_from_limit(standard.get("weekly"), 10080, "Weekly") or window(0, 10080, None, "Weekly")
        out["tertiary"] = factory_window_from_limit(standard.get("monthly"), None, "Monthly") or window(0, None, None, "Monthly")
        core = pools.get("core") or {}
        extras = []
        for key, minutes, title in (("fiveHour", 300, "Core 5h"), ("weekly", 10080, "Core 7-day"), ("monthly", None, "Core Monthly")):
            extra = factory_window_from_limit(core.get(key), minutes, title) or window(0, minutes, None, title)
            extras.append({"id": f"factory-core-{key}", "title": title, "window": extra})
        out["extraRateWindows"] = extras
        overage = str(limits.get("overagePreference") or "").strip()
        if overage:
            out["loginMethod"] = factory_plan_name(auth, f"Fallback: {overage}")
            out["identity"]["loginMethod"] = out["loginMethod"]
            out["identity"]["plan"] = out["loginMethod"]
        cents = limits.get("extraUsageBalanceCents")
        credits = {
            "remaining": float(cents) / 100.0 if isinstance(cents, (int, float)) else 0.0,
            "unit": "usd",
            "label": "Extra usage",
            "updatedAt": iso_now(),
        }
        return out, credits

    usage_data = (usage or {}).get("usage") if isinstance(usage, dict) else None
    usage_data = usage_data if isinstance(usage_data, dict) else {}
    period_end = factory_parse_date(usage_data.get("endDate"))
    standard = usage_data.get("standard") or {}
    premium = usage_data.get("premium") or {}
    out["primary"] = window(
        factory_ratio_percent(standard.get("userTokens"), standard.get("totalAllowance"), standard.get("usedRatio")),
        None,
        period_end,
        "Standard",
    )
    out["secondary"] = window(
        factory_ratio_percent(premium.get("userTokens"), premium.get("totalAllowance"), premium.get("usedRatio")),
        None,
        period_end,
        "Premium",
    )
    return out, credits


def factory_try_session(bearer: str | None, cookie: str | None, source: str) -> dict | None:
    if not bearer and not cookie:
        return None
    last_error = None
    auth = None
    for base in ("https://api.factory.ai", "https://app.factory.ai"):
        status, body = factory_request(f"{base}/api/app/auth/me", bearer=bearer, cookie=cookie)
        if status == 200:
            try:
                auth = json.loads(body)
            except json.JSONDecodeError:
                last_error = "Could not parse Factory auth."
                continue
            break
        if status in (401, 403):
            last_error = "Sign in to app.factory.ai in Chrome, or run `droid`."
            continue
        last_error = f"Factory auth returned {status}."
    if not isinstance(auth, dict):
        return row("factory", source=source, error=last_error or "Sign in to app.factory.ai in Chrome, or run `droid`.")

    limits = None
    limit_status, limit_body = factory_request("https://api.factory.ai/api/billing/limits", bearer=bearer, cookie=cookie)
    if limit_status == 200:
        try:
            limits = json.loads(limit_body)
        except json.JSONDecodeError:
            limits = None

    usage = None
    user_id = ((auth.get("userProfile") or {}).get("id") if isinstance(auth, dict) else None) or factory_jwt_claims(bearer).get("sub")
    for base in ("https://api.factory.ai", "https://app.factory.ai"):
        query = "useCache=true"
        if user_id:
            query += f"&userId={urllib.parse.quote(str(user_id))}"
        status, body = factory_request(f"{base}/api/organization/subscription/usage?{query}", bearer=bearer, cookie=cookie)
        if status == 200:
            try:
                usage = json.loads(body)
            except json.JSONDecodeError:
                last_error = "Could not parse Factory usage."
                continue
            break
        if status in (401, 403):
            last_error = "Sign in to app.factory.ai in Chrome, or run `droid`."
        else:
            last_error = f"Factory usage returned {status}."

    uses_limits = isinstance(limits, dict) and limits.get("usesTokenRateLimitsBilling") and limits.get("limits")
    if not uses_limits and not isinstance(usage, dict):
        return row("factory", source=source, error=last_error or "Factory usage was empty.")
    parsed, credits = factory_usage_from_payloads(auth, limits, usage, bearer)
    return row("factory", source=source, usage=parsed, credits=credits)


def fetch_factory(jars: dict) -> dict:
    api_key = factory_api_key()
    if api_key:
        result = factory_try_session(api_key, None, "api")
        if result and not result.get("error"):
            return result
        # Auto falls back to web/CLI when the key is missing or unauthorized.
        if result and "401" not in str((result.get("error") or {}).get("message") or "") and "403" not in str((result.get("error") or {}).get("message") or ""):
            pass

    cli = factory_cli_auth()
    if cli:
        result = factory_try_session(str(cli.get("access_token") or "") or None, None, "cli")
        if result and not result.get("error"):
            return result

    cookie = factory_session_header(jars)
    bearer = factory_bearer_from_cookies(jars)
    if cookie or bearer:
        result = factory_try_session(bearer, cookie or None, "chrome")
        if result:
            return result

    if api_key:
        return row("factory", source="api", error="Factory API key was rejected.")
    return row("factory", source="chrome", error="Sign in with `droid`, set FACTORY_API_KEY, or open app.factory.ai in Chrome.")
