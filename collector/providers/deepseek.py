"""DeepSeek balance collector (CodexBar provider id: deepseek).

API-key balance is preferred. A platform userToken from the environment or
CodexBar config is used when no API key is set. Detailed platform usage charts
are not fetched.
"""

from __future__ import annotations

import json
import os
from typing import Mapping, Sequence

from collector.codexbar_config import provider_entry, provider_secret
from collector.http import http
from collector.schema import iso_now, row
from collector.security import bounded_secret

MAX_DEEPSEEK_RESPONSE_BYTES = 512 * 1024
API_BALANCE_URL = "https://api.deepseek.com/user/balance"
PLATFORM_SUMMARY_URL = "https://platform.deepseek.com/api/v0/users/get_user_summary"
EXPIRED_CODES = frozenset({40002, 40003})


def deepseek_api_key() -> str | None:
    """Resolve the DeepSeek API key from the environment.

    Returns:
        Bounded API key, or None.
    """
    return bounded_secret(os.environ.get("DEEPSEEK_API_KEY")) or bounded_secret(
        os.environ.get("DEEPSEEK_KEY")
    )


def deepseek_platform_token() -> str | None:
    """Resolve a DeepSeek Platform userToken from env or CodexBar config.

    Returns:
        Bounded platform token, or None.
    """
    token = bounded_secret(os.environ.get("DEEPSEEK_PLATFORM_TOKEN")) or bounded_secret(
        os.environ.get("DEEPSEEK_USER_TOKEN")
    )
    if token:
        return token
    entry = provider_entry("deepseek")
    return provider_secret(entry)


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


def _currency_symbol(currency: str) -> str:
    return "¥" if currency.upper() == "CNY" else "$"


def select_balance_info(infos: Sequence[Mapping[str, object]]) -> Mapping[str, object] | None:
    """Pick the preferred currency row from balance_infos.

    Prefers a funded USD row, then any funded row, then USD, then the first row.

    Args:
        infos: balance_infos entries from the API balance response.

    Returns:
        Selected mapping, or None when empty.
    """
    if not infos:
        return None
    funded_usd = [
        item for item in infos
        if str(item.get("currency") or "").upper() == "USD"
        and (_as_float(item.get("total_balance")) or 0.0) > 0
    ]
    if funded_usd:
        return funded_usd[0]
    funded = [item for item in infos if (_as_float(item.get("total_balance")) or 0.0) > 0]
    if funded:
        return funded[0]
    usd = [item for item in infos if str(item.get("currency") or "").upper() == "USD"]
    if usd:
        return usd[0]
    return infos[0]


def parse_api_balance(
    payload: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Parse GET /user/balance into usage, credits, and pace.

    Args:
        payload: Decoded balance JSON.

    Returns:
        Tuple of usage dict, credits dict, and pace dict.

    Raises:
        ValueError: When the payload cannot be interpreted.
    """
    infos_raw = payload.get("balance_infos")
    if not isinstance(infos_raw, list):
        raise ValueError("DeepSeek balance_infos missing.")
    infos: list[Mapping[str, object]] = [item for item in infos_raw if isinstance(item, dict)]
    selected = select_balance_info(infos)
    if selected is None:
        currency = "USD"
        total = 0.0
        granted = 0.0
        topped = 0.0
        available = False
    else:
        currency = str(selected.get("currency") or "USD")
        total = _as_float(selected.get("total_balance")) or 0.0
        granted = _as_float(selected.get("granted_balance")) or 0.0
        topped = _as_float(selected.get("topped_up_balance")) or 0.0
        available = payload.get("is_available") is True
    return _balance_row(currency, total, granted, topped, available, source_plan="API key")


def _sum_wallets(wallets: Sequence[object], currency: str) -> float:
    total = 0.0
    for item in wallets:
        if not isinstance(item, dict):
            continue
        if str(item.get("currency") or "").upper() != currency.upper():
            continue
        amount = _as_float(item.get("balance"))
        if amount is not None:
            total += amount
    return total


def parse_platform_summary(
    payload: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Parse platform get_user_summary into usage, credits, and pace.

    Args:
        payload: Decoded platform summary JSON envelope.

    Returns:
        Tuple of usage dict, credits dict, and pace dict.

    Raises:
        ValueError: When the session is expired or wallets are unusable.
    """
    code = payload.get("code")
    if isinstance(code, int) and code in EXPIRED_CODES:
        raise ValueError("DeepSeek Platform session expired. Sign in again.")
    data = payload.get("data")
    if not isinstance(data, dict):
        biz = payload.get("biz_data") if isinstance(payload.get("biz_data"), dict) else None
        data = biz or payload
    else:
        biz_code = data.get("biz_code")
        if isinstance(biz_code, int) and biz_code in EXPIRED_CODES:
            raise ValueError("DeepSeek Platform session expired. Sign in again.")
        if isinstance(biz_code, int) and biz_code != 0 and "biz_data" not in data:
            raise ValueError(f"DeepSeek Platform returned biz_code {biz_code}.")
        nested = data.get("biz_data")
        if isinstance(nested, dict):
            data = nested
    normal = data.get("normal_wallets") if isinstance(data.get("normal_wallets"), list) else []
    bonus = data.get("bonus_wallets") if isinstance(data.get("bonus_wallets"), list) else []
    currencies: set[str] = set()
    for wallet in list(normal) + list(bonus):
        if isinstance(wallet, dict) and wallet.get("currency"):
            currencies.add(str(wallet["currency"]))
    if not currencies:
        return _balance_row("USD", 0.0, 0.0, 0.0, False, source_plan="Platform")
    ordered = sorted(currencies)
    selected = None
    for currency in ordered:
        if currency.upper() == "USD" and (
            _sum_wallets(normal, currency) + _sum_wallets(bonus, currency)
        ) > 0:
            selected = currency
            break
    if selected is None:
        for currency in ordered:
            if (_sum_wallets(normal, currency) + _sum_wallets(bonus, currency)) > 0:
                selected = currency
                break
    if selected is None:
        selected = next((c for c in ordered if c.upper() == "USD"), ordered[0])
    topped = _sum_wallets(normal, selected)
    granted = _sum_wallets(bonus, selected)
    total = topped + granted
    return _balance_row(selected, total, granted, topped, total > 0, source_plan="Platform")


def _balance_row(
    currency: str,
    total: float,
    granted: float,
    topped: float,
    available: bool,
    *,
    source_plan: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    symbol = _currency_symbol(currency)
    if total <= 0:
        summary = f"{symbol}0.00 — add credits at platform.deepseek.com"
    elif not available:
        summary = "Balance unavailable for API calls"
    else:
        summary = (
            f"{symbol}{total:.2f} (Paid: {symbol}{topped:.2f} / Granted: {symbol}{granted:.2f})"
        )
    usage: dict[str, object] = {
        "loginMethod": source_plan,
        "identity": {
            "providerID": "deepseek",
            "plan": source_plan,
        },
        "updatedAt": iso_now(),
    }
    pace: dict[str, object] = {"primary": {"summary": summary}}
    credits: dict[str, object] = {
        "remaining": total,
        "unit": "usd" if currency.upper() != "CNY" else "cny",
        "label": "Balance",
    }
    return usage, credits, pace


def _request_json(url: str, token: str, *, platform: bool = False) -> tuple[int, object]:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if platform:
        headers["x-client-platform"] = "web"
    status, body, _ = http(url, max_bytes=MAX_DEEPSEEK_RESPONSE_BYTES, headers=headers)
    if status == 0:
        raise ValueError(body.decode("utf-8", errors="replace") or "DeepSeek request failed.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not parse DeepSeek response: {exc}") from exc
    return status, payload


def fetch_deepseek() -> dict:
    """Fetch DeepSeek remaining credit balance.

    Returns:
        Snapshot row for the collector.
    """
    api_key = deepseek_api_key()
    if api_key:
        try:
            status, payload = _request_json(API_BALANCE_URL, api_key)
        except ValueError as exc:
            return row("deepseek", source="api", error=str(exc))
        if status != 200 or not isinstance(payload, dict):
            return row("deepseek", source="api", error=f"DeepSeek balance returned HTTP {status}.")
        try:
            usage, credits, pace = parse_api_balance(payload)
        except ValueError as exc:
            return row("deepseek", source="api", error=str(exc))
        return row("deepseek", source="api", usage=usage, credits=credits, pace=pace)

    platform_token = deepseek_platform_token()
    if not platform_token:
        return row(
            "deepseek",
            source="manual",
            error="Set DEEPSEEK_API_KEY, or DEEPSEEK_PLATFORM_TOKEN / CodexBar deepseek cookieHeader.",
        )
    try:
        status, payload = _request_json(PLATFORM_SUMMARY_URL, platform_token, platform=True)
    except ValueError as exc:
        return row("deepseek", source="platform", error=str(exc))
    if status in (401, 403):
        return row("deepseek", source="platform", error="DeepSeek Platform session expired. Sign in again.")
    if status != 200 or not isinstance(payload, dict):
        return row("deepseek", source="platform", error=f"DeepSeek Platform returned HTTP {status}.")
    try:
        usage, credits, pace = parse_platform_summary(payload)
    except ValueError as exc:
        return row("deepseek", source="platform", error=str(exc))
    return row(
        "deepseek",
        source="platform",
        usage=usage,
        credits=credits,
        pace=pace,
    )
