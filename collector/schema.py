from __future__ import annotations

from datetime import datetime, timezone
from collector.security import bounded_value

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
    return bounded_value(out)
