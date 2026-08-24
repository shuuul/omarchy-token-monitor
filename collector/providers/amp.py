from __future__ import annotations

import json
import os
import re
import shutil
from collector.cookies import HOME, cookie_header
from collector.http import http
from collector.schema import iso_now, row, window
from collector.security import bounded_secret, read_json, run_bounded

MAX_AMP_OUTPUT_BYTES = 256 * 1024
AMP_USAGE_URL = "https://ampcode.com/api/internal?userDisplayBalanceInfo"
AMP_SECRETS_KEY = "apiKey@https://ampcode.com/"
# CSI / 7-bit ESC sequences, including Amp's TUI reset (`ESC[=0u`, `ESC[<u`, `ESC[?25h`).
ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
AMP_USAGE_BODY = b'{"method":"userDisplayBalanceInfo","params":{}}'


def strip_cli_text(text: str) -> str:
    cleaned = ANSI_RE.sub("", text or "")
    return CONTROL_RE.sub("", cleaned)


def visible_cli_error(stderr: str, stdout: str, returncode: int) -> str:
    text = strip_cli_text(f"{stderr or ''}\n{stdout or ''}")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    useful = [line for line in lines if re.search(r"[A-Za-z]", line)]
    for line in reversed(useful):
        if line.lower().startswith("error"):
            return line
    if useful:
        return useful[-1]
    return f"exit {returncode}"


def amp_api_token() -> str | None:
    env = bounded_secret(os.environ.get("AMP_API_KEY"))
    if env:
        return env
    path = HOME / ".local/share/amp" / "secrets.json"
    if not path.exists():
        return None
    data = read_json(path)
    if not isinstance(data, dict):
        return None
    return bounded_secret(data.get(AMP_SECRETS_KEY))


def parse_amp_api_payload(body: bytes | str) -> tuple[str | None, str | None]:
    try:
        data = json.loads(body)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "Amp usage API returned invalid JSON."
    if not isinstance(data, dict):
        return None, "Amp usage API returned invalid JSON."
    if data.get("ok") is False:
        error = data.get("error") if isinstance(data.get("error"), dict) else {}
        if error.get("code") == "auth-required":
            return None, "Amp access token is invalid or expired."
        return None, "Amp usage API returned an error."
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    display = result.get("displayText")
    if not isinstance(display, str) or not display.strip():
        return None, "Amp usage API returned no usage text."
    return display, None


def parse_amp_text(text: str, source: str = "cli") -> dict:
    text = strip_cli_text(text).replace("**", "")
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
        r"(?:Amp\s+(.+?)\s+Subscription|Subscription\s+(.+?)):\s*"
        r"([0-9.]+)\s*%\s+other usage and\s*([0-9.]+)\s*%\s+orb usage remaining"
        r".*?(\d+)\s+(?:days?|months?)",
        text,
        re.I,
    )
    if sub:
        plan = (sub.group(1) or sub.group(2) or "").strip()
        usage["loginMethod"] = plan
        usage["secondary"] = window(100 - float(sub.group(3)), None, None, "Token Usage")
        usage["tertiary"] = window(100 - float(sub.group(4)), None, None, "Orb usage")
        usage.setdefault("identity", {})["loginMethod"] = plan
    credits = re.search(r"Individual credits:\s*\$?([0-9.]+)\s+remaining", text)
    credit_row = {"remaining": float(credits.group(1)), "unit": "usd", "updatedAt": iso_now()} if credits else None
    return row("amp", source=source, usage=usage, credits=credit_row)


def amp_row_has_usage(parsed: dict) -> bool:
    usage = parsed.get("usage") or {}
    if usage.get("primary") or usage.get("secondary") or usage.get("tertiary"):
        return True
    return parsed.get("credits") is not None


def _amp_headers(token: str | None = None, cookie: str | None = None) -> dict:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://ampcode.com",
        "Referer": "https://ampcode.com/settings",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cookie:
        headers["Cookie"] = cookie
    return headers


def fetch_amp_display(headers: dict) -> tuple[str | None, str | None]:
    status, body, _ = http(
        AMP_USAGE_URL,
        method="POST",
        headers=headers,
        body=AMP_USAGE_BODY,
        max_bytes=MAX_AMP_OUTPUT_BYTES,
    )
    if status == 401 or status == 403:
        if headers.get("Authorization"):
            return None, "Amp access token is invalid or expired."
        return None, "Amp session cookie expired."
    if status != 200:
        return None, f"Amp usage API returned {status}."
    return parse_amp_api_payload(body)


def fetch_amp(jars: dict) -> dict:
    errors: list[str] = []
    amp = shutil.which("amp")
    if amp:
        proc = run_bounded(
            [amp, "usage"],
            timeout=25,
            max_bytes=MAX_AMP_OUTPUT_BYTES,
            text=True,
        )
        text = proc.stdout or ""
        if not strip_cli_text(text).strip():
            text = proc.stderr or ""
        parsed = parse_amp_text(text, source="cli")
        if amp_row_has_usage(parsed):
            return parsed
        if proc.returncode != 0:
            errors.append(f"amp usage failed: {visible_cli_error(proc.stderr or '', proc.stdout or '', proc.returncode)}")
        elif strip_cli_text(text).strip():
            errors.append("amp usage returned no usage data.")

    token = amp_api_token()
    if token:
        display, error = fetch_amp_display(_amp_headers(token=token))
        if display:
            parsed = parse_amp_text(display, source="api")
            if amp_row_has_usage(parsed):
                return parsed
            errors.append("Amp usage API returned no usage data.")
        elif error:
            errors.append(error)

    header = cookie_header(jars, [("session", ["ampcode.com", "www.ampcode.com"])])
    if header:
        display, error = fetch_amp_display(_amp_headers(cookie=header))
        if display:
            parsed = parse_amp_text(display, source="chrome")
            if amp_row_has_usage(parsed):
                return parsed
        if error:
            errors.append(error)
        if not errors:
            errors.append("Amp cookie page has no usage text; CLI `amp usage` is preferred.")
        return row("amp", source="chrome", error=errors[0])

    if errors:
        source = "api" if token else "cli"
        return row("amp", source=source, error=errors[0])
    return row("amp", source="chrome", error="Sign in to ampcode.com in Chrome, or run `amp`.")
