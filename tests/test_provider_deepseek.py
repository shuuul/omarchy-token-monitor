#!/usr/bin/env python3
"""DeepSeek collector parsing tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers.deepseek import parse_api_balance, parse_platform_summary, select_balance_info


selected = select_balance_info([
    {"currency": "USD", "total_balance": "0.00", "granted_balance": "0", "topped_up_balance": "0"},
    {"currency": "CNY", "total_balance": "8.50", "granted_balance": "1.50", "topped_up_balance": "7.00"},
])
assert selected["currency"] == "CNY"

usage, credits, pace = parse_api_balance({
    "is_available": True,
    "balance_infos": [
        {
            "currency": "USD",
            "total_balance": "50.00",
            "granted_balance": "10.00",
            "topped_up_balance": "40.00",
        }
    ],
})
assert credits["remaining"] == 50.0
assert credits["label"] == "Balance"
assert credits["unit"] == "usd"
assert "primary" not in usage
assert "Paid: $40.00" in pace["primary"]["summary"]
assert usage["loginMethod"] == "API key"

zero_usage, zero_credits, zero_pace = parse_api_balance({
    "is_available": False,
    "balance_infos": [
        {
            "currency": "USD",
            "total_balance": "0",
            "granted_balance": "0",
            "topped_up_balance": "0",
        }
    ],
})
assert zero_credits["remaining"] == 0.0
assert "add credits" in zero_pace["primary"]["summary"]

platform_usage, platform_credits, platform_pace = parse_platform_summary({
    "code": 0,
    "data": {
        "biz_code": 0,
        "biz_data": {
            "normal_wallets": [{"currency": "USD", "balance": 12.0}],
            "bonus_wallets": [{"currency": "USD", "balance": 3.0}],
        },
    },
})
assert platform_credits["remaining"] == 15.0
assert "Paid: $12.00" in platform_pace["primary"]["summary"]
assert platform_usage["loginMethod"] == "Platform"

try:
    parse_platform_summary({"code": 40002})
    raise AssertionError("expired platform session was accepted")
except ValueError as exc:
    assert "expired" in str(exc).lower()

print("deepseek collector tests passed")
