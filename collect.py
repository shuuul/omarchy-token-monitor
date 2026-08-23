#!/usr/bin/env python3
"""Collect usage for Amp, Codex, Kimi, Cursor, Grok, Notion, and Zed.

Never prints cookies or tokens. Stdout is one JSON array.
"""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import re
import shutil
import sqlite3
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)
def user_home() -> Path:
    env = os.environ.get("HOME")
    if env:
        return Path(env)
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


HOME = user_home()
CTX = ssl.create_default_context()

PROVIDERS = ("amp", "codex", "kimi", "cursor", "grok", "notion", "zed")
BROWSERS = {
    "chrome": HOME / ".config/google-chrome",
    "chromium": HOME / ".config/chromium",
}


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_from_unix(ts: float | int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def window(used: float | None, minutes: int | None = None, resets_at: str | None = None, label: str | None = None) -> dict:
    return {
        "usedPercent": used,
        "windowMinutes": minutes,
        "resetsAt": resets_at,
        "label": label,
    }


def row(provider: str, *, source: str, usage: dict | None = None, credits: dict | None = None,
        pace: dict | None = None, error: str | None = None) -> dict:
    out = {"provider": provider, "source": source, "error": None}
    if usage:
        out["usage"] = usage
    if credits:
        out["credits"] = credits
    if pace:
        out["pace"] = pace
    if error:
        out["error"] = {"message": error}
    return out


def http(url: str, *, method: str = "GET", headers: dict | None = None, body: bytes | None = None, timeout: int = 20):
    req_headers = {"User-Agent": UA}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers or {})
    except Exception as exc:
        return 0, str(exc).encode(), {}


def derive_key(password: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1, 16)


def aes128_cbc_decrypt(key: bytes, data: bytes) -> bytes | None:
    proc = subprocess.run(
        ["openssl", "enc", "-aes-128-cbc", "-d", "-nopad", "-K", key.hex(), "-iv", "20" * 16],
        input=data,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    raw = proc.stdout
    pad = raw[-1]
    if 1 <= pad <= 16 and raw.endswith(bytes([pad]) * pad):
        raw = raw[:-pad]
    return raw


def decrypt_cookie(key: bytes, encrypted: bytes, meta_version: int = 24) -> str | None:
    if not encrypted or len(encrypted) < 4:
        return None
    version, ciphertext = encrypted[:3], encrypted[3:]
    if version not in (b"v10", b"v11"):
        return None
    plain = aes128_cbc_decrypt(key, ciphertext)
    if plain is None:
        return None
    if meta_version >= 24 and len(plain) >= 32:
        plain = plain[32:]
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        return None


def chrome_password(browser: str) -> bytes | None:
    app = "chrome" if browser == "chrome" else "chromium"
    proc = subprocess.run(
        ["secret-tool", "lookup", "application", app],
        capture_output=True,
        check=False,
        timeout=5,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout.rstrip(b"\n")


def cookie_db_path(root: Path) -> Path | None:
    for cand in (root / "Default" / "Network" / "Cookies", root / "Default" / "Cookies"):
        if cand.exists():
            return cand
    return None


def load_cookies(browser: str) -> dict[str, dict[str, str]]:
    root = BROWSERS.get(browser)
    if not root or not root.exists():
        return {}
    password = chrome_password(browser)
    if not password:
        return {}
    key = derive_key(password)
    db_path = cookie_db_path(root)
    if not db_path:
        return {}
    tmpdir = Path(tempfile.mkdtemp(prefix="otm-cookies-"))
    try:
        copy = tmpdir / "Cookies"
        shutil.copy2(db_path, copy)
        for side in ("-wal", "-shm"):
            extra = Path(str(db_path) + side)
            if extra.exists():
                shutil.copy2(extra, Path(str(copy) + side))
        con = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        try:
            version_row = con.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
            meta_version = int(version_row[0]) if version_row else 0
        except sqlite3.Error:
            meta_version = 0
        wanted = (
            "WorkosCursorSessionToken",
            "token_v2",
            "sso",
            "sso-rw",
            "session",
            "kimi-auth",
            "zed.session",
        )
        placeholders = ",".join("?" * len(wanted))
        jars: dict[str, dict[str, str]] = {}
        for host, name, encrypted in con.execute(
            f"SELECT host_key, name, encrypted_value FROM cookies WHERE name IN ({placeholders})",
            wanted,
        ):
            value = decrypt_cookie(key, encrypted, meta_version)
            if value:
                jars.setdefault(name, {})[host] = value
        con.close()
        return jars
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def cookie_value(jars: dict[str, dict[str, str]], name: str, hosts: list[str]) -> str | None:
    by_host = jars.get(name) or {}
    for host in hosts:
        if host in by_host:
            return by_host[host]
    for host, value in by_host.items():
        if any(wanted in host for wanted in hosts):
            return value
    return None


def cookie_header(jars: dict[str, dict[str, str]], pairs: list[tuple[str, list[str]]]) -> str:
    parts = []
    for name, hosts in pairs:
        value = cookie_value(jars, name, hosts)
        if value:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def preferred_jars(settings: dict) -> tuple[str, dict[str, dict[str, str]]]:
    wanted = str(settings.get("browser") or "chrome")
    order = [wanted] + [name for name in ("chrome", "chromium") if name != wanted]
    for name in order:
        jars = load_cookies(name)
        if jars:
            return name, jars
    return wanted, {}


def fetch_codex() -> dict:
    auth_path = Path(os.environ.get("CODEX_HOME", HOME / ".codex")) / "auth.json"
    if not auth_path.exists():
        return row("codex", source="oauth", error="Sign in with `codex login`.")
    auth = json.loads(auth_path.read_text())
    tokens = auth.get("tokens") or {}
    access = tokens.get("access_token")
    if not access:
        return row("codex", source="oauth", error="Codex auth.json has no access token.")
    headers = {
        "Authorization": f"Bearer {access}",
        "Accept": "application/json",
    }
    account = tokens.get("account_id")
    if account:
        headers["ChatGPT-Account-ID"] = account
    status, body, _ = http("https://chatgpt.com/backend-api/wham/usage", headers=headers)
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
        primary = map_window(extra_rate.get("primary_window"), f"{title} session")
        secondary = map_window(extra_rate.get("secondary_window"), f"{title} weekly")
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
        "primary": map_window(rate.get("primary_window"), "Session"),
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


def fetch_cursor(jars: dict) -> dict:
    header = cookie_header(jars, [("WorkosCursorSessionToken", ["cursor.com"])])
    if not header:
        return row("cursor", source="chrome", error="Sign in to cursor.com in Chrome.")
    headers = {"Cookie": header, "Accept": "application/json"}
    status, body, _ = http("https://cursor.com/api/usage-summary", headers=headers)
    if status != 200:
        return row("cursor", source="chrome", error=f"Cursor usage-summary returned {status}.")
    data = json.loads(body)
    me_status, me_body, _ = http("https://cursor.com/api/auth/me", headers=headers)
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
    status, body, _ = http("https://app.notion.com/api/v3/getSpaces", method="POST", headers=headers, body=b"{}")
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
        "primary": window(pct(rolling), 360, None, "6-hour"),
        "secondary": window(pct(monthly), None, monthly_reset, "Monthly"),
        "updatedAt": iso_now(),
    }
    return row("notion", source="chrome", usage=usage)


def parse_amp_text(text: str) -> dict:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = text.replace("**", "")
    usage: dict = {"updatedAt": iso_now(), "extraRateWindows": []}
    signed = re.search(r"Signed in as\s+(\S+)", text)
    if signed:
        usage["accountEmail"] = signed.group(1)
        usage["identity"] = {"accountEmail": signed.group(1), "providerID": "amp"}
    free = re.search(r"Amp Free:\s*([0-9.]+)\s*%\s+remaining", text)
    if free:
        remaining = float(free.group(1))
        usage["primary"] = window(100 - remaining, 1440, None, "Amp Free")
    sub = re.search(
        r"Amp\s+(.+?)\s+Subscription:\s*([0-9.]+)\s*%\s+other usage and\s*([0-9.]+)\s*%\s+orb usage remaining.*?(\d+)\s+days?",
        text,
        re.I,
    )
    if sub:
        usage["loginMethod"] = sub.group(1).strip()
        usage["secondary"] = window(100 - float(sub.group(2)), None, None, "Token Usage")
        usage["tertiary"] = window(100 - float(sub.group(3)), None, None, "Orb usage")
        usage.setdefault("identity", {})["loginMethod"] = sub.group(1).strip()
    credits = re.search(r"Individual credits:\s*\$?([0-9.]+)\s+remaining", text)
    credit_row = {"remaining": float(credits.group(1)), "unit": "usd", "updatedAt": iso_now()} if credits else None
    return row("amp", source="cli", usage=usage, credits=credit_row)


def fetch_amp(jars: dict) -> dict:
    amp = shutil.which("amp")
    if amp:
        proc = subprocess.run([amp, "usage"], capture_output=True, text=True, timeout=25, check=False)
        if proc.returncode == 0 and "Amp Free" in (proc.stdout or ""):
            return parse_amp_text(proc.stdout)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            detail = detail[-1] if detail else f"exit {proc.returncode}"
            return row("amp", source="cli", error=f"amp usage failed: {detail}")
    header = cookie_header(jars, [("session", ["ampcode.com"])])
    if not header:
        return row("amp", source="chrome", error="Sign in to ampcode.com in Chrome, or run `amp`.")
    return row("amp", source="chrome", error="Amp cookie page has no usage text; CLI `amp usage` is preferred.")


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


def grok_settings_plan(header: str) -> str:
    status, body, _ = http(
        "https://cli-chat-proxy.grok.com/v1/settings",
        headers={"Cookie": header, "Accept": "application/json"},
        timeout=8,
    )
    if status != 200:
        return ""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return ""
    return grok_pretty_plan(str(data.get("subscription_tier_display") or ""))


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


def grok_plan_name(header: str) -> tuple[str, str | None]:
    billed, email = grok_session_plan(header)
    settings = grok_settings_plan(header)
    return settings or billed, email


def fetch_grok(jars: dict) -> dict:
    header = cookie_header(jars, [("sso", [".grok.com", "grok.com", ".x.ai"]), ("sso-rw", [".grok.com", "grok.com", ".x.ai"])])
    if not header:
        return row("grok", source="chrome", error="Sign in to grok.com in Chrome.")
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
    plan, email = grok_plan_name(header)
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
    return row("grok", source="chrome", usage=usage)


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


def requested_providers(settings: dict, argv: list[str] | None = None) -> tuple[str, ...]:
    args = list(argv or [])
    wanted: list[str] = []
    skip = False
    for item in args:
        if skip:
            skip = False
            continue
        if item in ("-p", "--provider"):
            skip = True
            continue
        if item.startswith("--provider="):
            wanted.append(item.split("=", 1)[1])
            continue
        if item.startswith("-") or item.endswith(".py"):
            continue
        wanted.append(item)
    only = str((settings or {}).get("only") or "").strip()
    if only:
        wanted.append(only)
    names = []
    for name in wanted:
        if name in PROVIDERS and name not in names:
            names.append(name)
    return tuple(names) if names else PROVIDERS


def collect(settings: dict | None = None, argv: list[str] | None = None) -> list[dict]:
    settings = settings or {}
    enabled = settings.get("providers") or {}
    browser, jars = preferred_jars(settings)
    fetchers = {
        "amp": lambda: fetch_amp(jars),
        "codex": fetch_codex,
        "kimi": lambda: fetch_kimi(jars),
        "cursor": lambda: fetch_cursor(jars),
        "grok": lambda: fetch_grok(jars),
        "notion": lambda: fetch_notion(jars),
        "zed": fetch_zed,
    }
    out = []
    for provider in requested_providers(settings, argv):
        entry = enabled.get(provider) if isinstance(enabled, dict) else None
        if entry and entry.get("enabled") is False:
            continue
        try:
            out.append(fetchers[provider]())
        except Exception as exc:
            out.append(row(provider, source=browser, error=str(exc)))
    return out


def main() -> int:
    settings = {}
    raw = os.environ.get("OTM_SETTINGS_JSON")
    if raw:
        settings = json.loads(raw)
    print(json.dumps(collect(settings, sys.argv[1:]), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
