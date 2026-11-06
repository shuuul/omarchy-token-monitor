#!/usr/bin/env python3
"""Devin collector parsing and auth helper tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers.devin import (
    candidate_paths,
    normalized_organization,
    parse_devin_usage,
    strip_bearer,
)


assert strip_bearer("Bearer abc.def") == "abc.def"
assert strip_bearer("Authorization: Bearer xyz") == "xyz"
assert strip_bearer("  token-only  ") == "token-only"
assert normalized_organization("acme") == "org/acme"
assert normalized_organization("org_abc123") == "organizations/org_abc123"
assert normalized_organization("org-abc123") == "organizations/org-abc123"
assert "org_abc123/billing/quota/usage" in candidate_paths(
    "organizations/org_abc123",
    "org_abc123",
)
assert "org/acme/billing/quota/usage" in candidate_paths("org/acme", None)

usage, credits = parse_devin_usage(
    {
        "daily_percentage": 0.25,
        "daily_reset_at": "2026-11-07T00:00:00Z",
        "weekly_percentage": 40,
        "weekly_reset_at": "2026-11-10T00:00:00Z",
        "plan_name": "pro",
        "overage_balance": 12.5,
    },
    "org_abc123",
)
assert usage["primary"]["label"] == "Daily"
assert usage["primary"]["usedPercent"] == 25.0
assert usage["primary"]["windowMinutes"] == 1440
assert usage["secondary"]["label"] == "Weekly"
assert usage["secondary"]["usedPercent"] == 40.0
assert usage["identity"]["plan"] == "Pro"
assert credits["remaining"] == 12.5
assert credits["label"] == "Extra usage balance"

hidden, no_credits = parse_devin_usage(
    {
        "hide_daily_quota": True,
        "weekly_percentage": 10,
        "overage_balance_cents": 250,
    },
    "acme",
)
assert "primary" not in hidden
assert hidden["secondary"]["usedPercent"] == 10.0
assert no_credits["remaining"] == 2.5

try:
    parse_devin_usage({"plan_name": "free"}, "acme")
    raise AssertionError("empty quota payload was accepted")
except ValueError:
    pass

print("devin collector tests passed")
