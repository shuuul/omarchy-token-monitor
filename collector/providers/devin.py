"""Devin usage collector (CodexBar provider id: devin).

Linux auth is manual only: environment variables or a CodexBar CLI config
entry. Chromium localStorage import is not implemented.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from collector.codexbar_config import provider_entry, provider_secret, provider_workspace_id
from collector.http import http
from collector.schema import iso_from_unix, iso_now, row, window
from collector.security import bounded_secret

MAX_DEVIN_RESPONSE_BYTES = 512 * 1024
DEVIN_BASE = "https://app.devin.ai"
DEVIN_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)


def strip_bearer(raw: str | None) -> str | None:
    """Normalize a Bearer token, Authorization header, or bare token.

    Args:
        raw: Token string that may include an Authorization: or Bearer prefix.

    Returns:
        Bounded bare token, or None when empty.
    """
    text = bounded_secret(raw)
    if not text:
        return None
    lower = text.lower()
    if lower.startswith("authorization:"):
        text = text.split(":", 1)[1].strip()
        lower = text.lower()
    if lower.startswith("bearer "):
        text = text[7:].strip()
    return bounded_secret(text)


def is_internal_organization_id(value: str) -> bool:
    """Return True when value looks like an internal org-... / org_... id.

    Args:
        value: Organization identifier.

    Returns:
        Whether the value is an internal Devin organization id.
    """
    return value.startswith("org-") or value.startswith("org_")


def normalized_organization(raw: str | None) -> str | None:
    """Normalize an organization slug, URL, or internal id for API paths.

    Args:
        raw: Organization from env, config, or x-cog-org-id.

    Returns:
        Path-ready organization string, or None.
    """
    text = bounded_secret(raw)
    if not text:
        return None
    value = text.strip().strip("/")
    if "://" in value:
        try:
            from urllib.parse import urlsplit

            parsed = urlsplit(value)
            host = (parsed.hostname or "").lower()
            if host == "devin.ai" or host.endswith(".devin.ai"):
                parts = [part for part in parsed.path.split("/") if part]
                if len(parts) >= 2 and parts[0] == "org":
                    value = f"org/{parts[1]}"
                elif len(parts) >= 2 and parts[0] == "organizations":
                    value = f"organizations/{parts[1]}"
        except ValueError:
            pass
        value = value.strip().strip("/")
    if value.startswith("org/") or value.startswith("organizations/"):
        return value
    if is_internal_organization_id(value):
        return f"organizations/{value}"
    return f"org/{value}"


def internal_organization_id(raw: str | None) -> str | None:
    """Extract the bare internal organization id when present.

    Args:
        raw: Organization string.

    Returns:
        Internal id without the organizations/ prefix, or None.
    """
    normalized = normalized_organization(raw)
    if not normalized or not normalized.startswith("organizations/"):
        return None
    return normalized[len("organizations/") :]


def display_organization(raw: str | None) -> str | None:
    """Human-readable organization label for the usage identity.

    Args:
        raw: Organization string.

    Returns:
        Display form without org/ or organizations/ prefixes.
    """
    text = bounded_secret(raw)
    if not text:
        return None
    if text.startswith("org/"):
        return text[4:]
    if text.startswith("organizations/"):
        return text[len("organizations/") :]
    return text


def candidate_paths(organization: str, internal_id: str | None) -> tuple[str, ...]:
    """Build Devin quota usage path candidates in CodexBar order.

    Args:
        organization: Normalized organization path segment.
        internal_id: Optional bare internal organization id.

    Returns:
        Unique path suffixes under /api/.
    """
    paths: list[str] = []
    normalized = normalized_organization(organization) or organization
    if internal_id:
        paths.append(f"{internal_id}/billing/quota/usage")
    paths.append(f"{normalized}/billing/quota/usage")
    if normalized.startswith("org/"):
        slug = normalized[4:]
        paths.append(f"{slug}/billing/quota/usage")
    if not normalized.startswith("org/") and not normalized.startswith("organizations/"):
        paths.append(f"org/{normalized}/billing/quota/usage")
    if internal_id:
        paths.append(f"organizations/{internal_id}/billing/quota/usage")
    seen: set[str] = set()
    out: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return tuple(out)


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number == number else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _used_percent(value: object) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    if number < 1:
        number *= 100
    return max(0.0, min(100.0, number))


def _date_to_iso(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if re.match(r"^\d+(\.\d+)?$", text):
            return _date_to_iso(float(text))
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    number = _as_float(value)
    if number is None or number <= 0:
        return None
    seconds = number / 1000.0 if number > 10_000_000_000 else number
    return iso_from_unix(seconds)


def _first_double(mapping: Mapping[str, object], keys: Sequence[str]) -> float | None:
    for key in keys:
        if key in mapping:
            number = _as_float(mapping[key])
            if number is not None:
                return number
    return None


def _percent_from_object(value: object) -> float | None:
    direct = _used_percent(value)
    if direct is not None and not isinstance(value, dict):
        return direct
    if not isinstance(value, dict):
        return None
    for key in (
        "used_percent",
        "usedPercent",
        "usage_percent",
        "usagePercent",
        "percent_used",
        "percentUsed",
        "percent",
    ):
        if key in value:
            number = _used_percent(value[key])
            if number is not None:
                return number
    for key in ("remaining_percent", "remainingPercent", "percent_remaining", "percentRemaining"):
        if key in value:
            remaining = _as_float(value[key])
            if remaining is not None:
                percent = remaining * 100 if remaining <= 1 else remaining
                return max(0.0, min(100.0, 100.0 - percent))
    used = _first_double(value, ("used", "usage", "used_count", "usedCount", "consumed"))
    limit = _first_double(value, ("limit", "quota", "total", "max", "available"))
    if used is not None and limit is not None and limit > 0:
        return max(0.0, min(100.0, used / limit * 100.0))
    remaining = _first_double(value, ("remaining", "left", "available"))
    if remaining is not None and limit is not None and limit > 0:
        return max(0.0, min(100.0, (limit - remaining) / limit * 100.0))
    return None


def _reset_from_dict(mapping: Mapping[str, object]) -> str | None:
    for key, value in mapping.items():
        if "reset" in str(key).lower():
            iso = _date_to_iso(value)
            if iso:
                return iso
    return None


def _window_from_value(value: object) -> tuple[float, str | None] | None:
    if isinstance(value, dict):
        percent = _percent_from_object(value)
        if percent is not None:
            return percent, _reset_from_dict(value)
        for nested in value.values():
            found = _window_from_value(nested)
            if found is not None:
                return found
        return None
    percent = _percent_from_object(value)
    if percent is None:
        return None
    return percent, None


def _is_daily_key(raw: str) -> bool:
    key = raw.lower()
    return "hide" not in key and ("daily" in key or "day" in key)


def _is_weekly_key(raw: str) -> bool:
    key = raw.lower()
    return "hide" not in key and ("weekly" in key or "week" in key)


def _find_window(object_: object, key_matches: Any) -> tuple[float, str | None] | None:
    if isinstance(object_, dict):
        for key, value in object_.items():
            if key_matches(str(key)):
                found = _window_from_value(value)
                if found is not None:
                    return found
        for value in object_.values():
            found = _find_window(value, key_matches)
            if found is not None:
                return found
    elif isinstance(object_, list):
        for value in object_:
            found = _find_window(value, key_matches)
            if found is not None:
                return found
    return None


def _clean_display(raw: str) -> str | None:
    cleaned = raw.strip()
    if not cleaned:
        return None
    parts: list[str] = []
    for chunk in re.split(r"[_\-]+", cleaned):
        if not chunk:
            continue
        parts.append(chunk[:1].upper() + chunk[1:])
    return " ".join(parts) if parts else None


def _find_plan_name(object_: object) -> str | None:
    if isinstance(object_, dict):
        for key in ("plan_name", "planName", "plan", "tier", "subscription_tier", "subscriptionTier"):
            value = object_.get(key)
            if isinstance(value, str):
                cleaned = _clean_display(value)
                if cleaned:
                    return cleaned
        for value in object_.values():
            found = _find_plan_name(value)
            if found:
                return found
    elif isinstance(object_, list):
        for value in object_:
            found = _find_plan_name(value)
            if found:
                return found
    return None


def _find_overage_balance(payload: Mapping[str, object]) -> float | None:
    balance = _as_float(payload.get("overage_balance"))
    if balance is not None and balance >= 0:
        return balance
    cents = _as_float(payload.get("overage_balance_cents"))
    if cents is not None and cents >= 0:
        return cents / 100.0
    return None


def parse_devin_usage(payload: object, organization: str | None) -> tuple[dict[str, object], dict[str, object] | None]:
    """Parse a Devin billing/quota/usage JSON object into usage and credits.

    Args:
        payload: Decoded JSON response body.
        organization: Organization string used for the request.

    Returns:
        Tuple of usage dict and optional credits dict.

    Raises:
        ValueError: When neither daily nor weekly quota can be resolved.
    """
    dictionary = payload if isinstance(payload, dict) else {}
    hide_daily = dictionary.get("hide_daily_quota") is True
    daily: tuple[float, str | None] | None = None
    if not hide_daily:
        percent = _used_percent(dictionary.get("daily_percentage"))
        if percent is not None:
            daily = (percent, _date_to_iso(dictionary.get("daily_reset_at")))
        else:
            daily = _find_window(payload, _is_daily_key)
    weekly: tuple[float, str | None] | None = None
    percent = _used_percent(dictionary.get("weekly_percentage"))
    if percent is not None:
        weekly = (percent, _date_to_iso(dictionary.get("weekly_reset_at")))
    else:
        weekly = _find_window(payload, _is_weekly_key)
    if daily is None and weekly is None:
        raise ValueError("Missing Devin quota windows.")

    usage: dict[str, object] = {
        "loginMethod": _find_plan_name(payload) or "Devin",
        "identity": {
            "providerID": "devin",
            "plan": _find_plan_name(payload) or "",
            "accountOrganization": display_organization(organization) or "",
        },
        "updatedAt": iso_now(),
    }
    if daily is not None:
        usage["primary"] = window(daily[0], 24 * 60, daily[1], "Daily")
    if weekly is not None:
        usage["secondary"] = window(weekly[0], 7 * 24 * 60, weekly[1], "Weekly")

    credits = None
    overage = _find_overage_balance(dictionary) if dictionary else None
    if overage is not None:
        credits = {
            "remaining": overage,
            "unit": "usd",
            "label": "Extra usage balance",
        }
    return usage, credits


def resolve_devin_auth() -> tuple[str, str, str | None] | None:
    """Resolve manual Devin bearer token and organization.

    Returns:
        Tuple of (token, organization, internal_org_id), or None when incomplete.
    """
    token = strip_bearer(os.environ.get("DEVIN_BEARER_TOKEN")) or strip_bearer(
        os.environ.get("DEVIN_AUTHORIZATION")
    )
    organization = bounded_secret(os.environ.get("DEVIN_ORGANIZATION")) or bounded_secret(
        os.environ.get("DEVIN_ORG")
    )
    entry = provider_entry("devin")
    if not token:
        token = strip_bearer(provider_secret(entry))
    if not organization:
        organization = provider_workspace_id(entry)
    if not token or not organization:
        return None
    internal = internal_organization_id(organization)
    return token, organization, internal


def fetch_devin() -> dict:
    """Fetch Devin daily/weekly quota for the configured organization.

    Returns:
        Snapshot row for the collector.
    """
    auth = resolve_devin_auth()
    if not auth:
        return row(
            "devin",
            source="manual",
            error=(
                "Set DEVIN_BEARER_TOKEN and DEVIN_ORGANIZATION, or configure "
                "cookieSource=manual in ~/.config/codexbar/config.json."
            ),
        )
    token, organization, internal = auth
    normalized = normalized_organization(organization)
    if not normalized:
        return row("devin", source="manual", error="No Devin organization was found.")
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": DEVIN_UA,
        "Authorization": f"Bearer {token}",
    }
    if internal:
        headers["x-cog-org-id"] = internal
    last_error = "No Devin quota endpoint succeeded."
    for path in candidate_paths(normalized, internal):
        status, body, _ = http(
            f"{DEVIN_BASE}/api/{path}",
            max_bytes=MAX_DEVIN_RESPONSE_BYTES,
            headers=headers,
        )
        if status in (401, 403):
            detail = ""
            try:
                payload = json.loads(body.decode("utf-8", errors="replace"))
                if isinstance(payload, dict):
                    detail = str(payload.get("detail") or "")
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                detail = ""
            if detail == "No organizations found for auth1 user":
                return row(
                    "devin",
                    source="manual",
                    error=(
                        "No Devin organization was found. Set Organization to the "
                        "internal org-... or org_... ID from x-cog-org-id."
                    ),
                )
            return row(
                "devin",
                source="manual",
                error="Devin rejected the session token (invalid or expired).",
            )
        if status != 200:
            last_error = f"Devin API returned HTTP {status}."
            continue
        try:
            payload = json.loads(body.decode("utf-8"))
            usage, credits = parse_devin_usage(payload, organization)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            last_error = f"Could not parse Devin usage: {exc}"
            continue
        return row("devin", source="manual", usage=usage, credits=credits)
    return row("devin", source="manual", error=last_error)
