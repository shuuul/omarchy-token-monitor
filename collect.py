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
import tempfile
import urllib.error
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
        "loginMethod": data.get("plan_type"),
        "identity": {"accountEmail": data.get("email"), "loginMethod": data.get("plan_type"), "providerID": "codex"},
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
        "loginMethod": data.get("membershipType"),
        "identity": {"accountEmail": email, "loginMethod": data.get("membershipType"), "providerID": "cursor"},
        "primary": window(plan.get("totalPercentUsed"), None, cycle_end, "Plan"),
        "secondary": window(plan.get("autoPercentUsed"), None, cycle_end, "Cursor models"),
        "tertiary": window(plan.get("apiPercentUsed"), None, cycle_end, "Third-party"),
        "updatedAt": iso_now(),
    }
    return row("cursor", source="chrome", usage=usage)


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
    rec = next(iter(spaces.values()))
    space_map = rec.get("space") or {}
    space_id = next(iter(space_map))
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
    reset_6h = None
    if rolling.get("used") is not None and rolling.get("limit"):
        # Notion does not always send resetsInSeconds; leave blank.
        pass
    monthly_reset = iso_from_unix((monthly.get("periodEndMs") or 0) / 1000) if monthly.get("periodEndMs") else None

    def pct(block: dict) -> float | None:
        limit = block.get("limit")
        used = block.get("used")
        if limit in (None, 0) or used is None:
            return None
        return float(used) / float(limit) * 100.0

    usage = {
        "loginMethod": "Notion AI",
        "identity": {"providerID": "notion", "loginMethod": "Notion AI"},
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
        usage["secondary"] = window(100 - float(sub.group(2)), None, None, "Other usage")
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
    return row(
        "grok",
        source="chrome",
        usage={
            "loginMethod": "Grok",
            "identity": {"providerID": "grok", "loginMethod": "Grok"},
            "primary": window(used, None, reset_at, "Credits"),
            "updatedAt": iso_now(),
        },
    )


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
        return parse_grok_grpc(body)
    except Exception:
        return row("grok", source="chrome", error="Could not parse Grok billing payload.")


def fetch_kimi(jars: dict) -> dict:
    cred_path = HOME / ".kimi-code/credentials/kimi-code.json"
    token = None
    source = "cli"
    if cred_path.exists():
        creds = json.loads(cred_path.read_text())
        token = creds.get("access_token")
    if not token:
        token = cookie_value(jars, "kimi-auth", ["www.kimi.com", ".kimi.com", "kimi.com"])
        source = "chrome"
    if not token:
        return row("kimi", source="cli", error="Sign in with Kimi Code CLI, or open kimi.com in Chrome.")
    status, body, _ = http(
        "https://api.kimi.com/coding/v1/usages",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if status != 200:
        return row("kimi", source=source, error="Kimi token expired. Run the Kimi Code CLI login again.")
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

    usage = {
        "loginMethod": "Kimi Code",
        "identity": {"providerID": "kimi", "loginMethod": "Kimi Code"},
        "primary": from_counts(rolling, "5-hour", 300),
        "secondary": from_counts(weekly, "Weekly", 10080),
        "updatedAt": iso_now(),
    }
    return row("kimi", source=source, usage=usage)


def fetch_zed() -> dict:
    return row("zed", source="local", error="Zed Linux credentials are not in Chrome cookies. Sign-in lives in the Zed app keyring.")


def collect(settings: dict | None = None) -> list[dict]:
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
    for provider in PROVIDERS:
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
    print(json.dumps(collect(settings), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
