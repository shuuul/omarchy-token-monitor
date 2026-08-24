from __future__ import annotations

import hashlib
import os
import pwd
import shutil
import sqlite3
import tempfile
from pathlib import Path
from collector.security import MAX_CREDENTIAL_BYTES, bounded_secret, run_bounded

MAX_COOKIE_ROWS = 128
MAX_ENCRYPTED_COOKIE_BYTES = 64 * 1024
MAX_COOKIE_DB_BYTES = 512 * 1024 * 1024

def user_home() -> Path:
    env = os.environ.get("HOME")
    if env:
        return Path(env)
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


HOME = user_home()

FACTORY_COOKIE_NAMES = (
    "wos-session",
    "__Secure-next-auth.session-token",
    "next-auth.session-token",
    "__Secure-authjs.session-token",
    "__Host-authjs.csrf-token",
    "authjs.session-token",
    "session",
    "access-token",
)
FACTORY_COOKIE_HOSTS = ["factory.ai", "app.factory.ai", "auth.factory.ai"]
BROWSERS = {
    "chrome": HOME / ".config/google-chrome",
    "chromium": HOME / ".config/chromium",
}


def derive_key(password: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1, 16)


def aes128_cbc_decrypt(key: bytes, data: bytes) -> bytes | None:
    if len(data) > MAX_ENCRYPTED_COOKIE_BYTES:
        return None
    proc = run_bounded(
        ["openssl", "enc", "-aes-128-cbc", "-d", "-nopad", "-K", key.hex(), "-iv", "20" * 16],
        input=data,
        timeout=5,
        max_bytes=MAX_ENCRYPTED_COOKIE_BYTES,
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
    proc = run_bounded(
        ["secret-tool", "lookup", "application", app],
        timeout=5,
        max_bytes=MAX_CREDENTIAL_BYTES,
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
    if db_path.stat().st_size > MAX_COOKIE_DB_BYTES:
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
            *FACTORY_COOKIE_NAMES,
        )
        placeholders = ",".join("?" * len(wanted))
        jars: dict[str, dict[str, str]] = {}
        for host, name, encrypted in con.execute(
            f"SELECT host_key, name, encrypted_value FROM cookies WHERE name IN ({placeholders}) ORDER BY last_access_utc DESC LIMIT ?",
            (*wanted, MAX_COOKIE_ROWS),
        ):
            if not isinstance(host, str) or len(host) > 255:
                continue
            if not isinstance(encrypted, bytes) or len(encrypted) > MAX_ENCRYPTED_COOKIE_BYTES:
                continue
            value = decrypt_cookie(key, encrypted, meta_version)
            value = bounded_secret(value)
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
        normalized = host.lstrip(".").lower()
        if any(
            normalized == wanted.lstrip(".").lower()
            or normalized.endswith("." + wanted.lstrip(".").lower())
            for wanted in hosts
        ):
            return value
    return None


def cookie_header(jars: dict[str, dict[str, str]], pairs: list[tuple[str, list[str]]]) -> str:
    parts = []
    for name, hosts in pairs:
        value = cookie_value(jars, name, hosts)
        if value:
            parts.append(f"{name}={value}")
    header = "; ".join(parts)
    return header if len(header.encode("utf-8")) <= 32 * 1024 else ""


def preferred_jars(settings: dict) -> tuple[str, dict[str, dict[str, str]]]:
    wanted = str(settings.get("browser") or "chrome")
    order = [wanted] + [name for name in ("chrome", "chromium") if name != wanted]
    for name in order:
        jars = load_cookies(name)
        if jars:
            return name, jars
    return wanted, {}
