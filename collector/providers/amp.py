from __future__ import annotations

import re
import shutil
import subprocess
from collector.cookies import cookie_header
from collector.schema import iso_now, row, window

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
