#!/usr/bin/env python3
"""Antigravity local language-server parsing and process classification tests."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers.antigravity import (
    _identity,
    _legacy_session_window,
    _reset_time,
    _summary_rows,
    _worst_row,
    bucket_window_minutes,
    candidate_processes,
    classify_process,
    parse_proc_tcp_listeners,
)

APP_COMMAND = (
    "/opt/Antigravity/resources/bin/language_server --standalone --override_ide_name antigravity "
    "--subclient_type hub --override_ide_version 2.11.0 --https_server_port 0 "
    "--csrf_token 1ee266e1-53ea-4f70-a229-91058083b0ba --app_data_dir antigravity "
    "--host_bridge_url=http://127.0.0.1:34381 --host_bridge_token=****"
)
IDE_COMMAND = (
    "/opt/Antigravity IDE.app/Contents/resources/app/extensions/antigravity/bin/language_server "
    "--app_data_dir antigravity-ide --csrf_token 2222"
)
CLI_COMMAND = "/usr/bin/agy serve --quiet"

assert classify_process(APP_COMMAND) == "app"
assert classify_process(IDE_COMMAND) == "ide"
assert classify_process(CLI_COMMAND) == "cli"
assert classify_process("/usr/bin/language_server --port 1") is None
assert classify_process("/usr/bin/python3 -m http.server") is None

ps_output = "\n".join([
    f"  1019781 /usr/bin/antigravity",
    f"  1020202 {APP_COMMAND}",
    f"  1030000 {IDE_COMMAND}",
    f"  1040000 {CLI_COMMAND}",
    "  1050000 language_server --csrf_token tokenless-app",
])
candidates = candidate_processes(ps_output)
assert [entry["kind"] for entry in candidates] == ["app", "cli", "ide"]
assert candidates[0]["pid"] == 1020202
assert candidates[0]["csrf"] == "1ee266e1-53ea-4f70-a229-91058083b0ba"
assert candidates[1]["kind"] == "cli" and candidates[1]["csrf"] == ""
assert candidates[2]["csrf"] == "2222"
assert candidate_processes("") == []
assert all("csrf_token" not in json.dumps(entry) or entry["csrf"] for entry in candidates)

# /proc/net/tcp fixture: row format is documented in proc(5); inode 12345 LISTENs on 0x1F90.
tcp_fixture = (
    "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  "
    "timeout inode\n"
    "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000"
    "        0 12345 1\n"
    "   1: 0100007F:1F91 00000000:0000 01 00000000:00000000 00:00000000 00000000  1000"
    "        0 12346 1\n"
    "   2: 00000000:0035 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000"
    "        0 99999 1\n"
)
ports = parse_proc_tcp_listeners(tcp_fixture, {"12345"})
assert ports == {8080}
assert parse_proc_tcp_listeners(tcp_fixture, set()) == set()
assert parse_proc_tcp_listeners(tcp_fixture, {"12345", "99999"}) == {8080, 53}

assert bucket_window_minutes("gemini-weekly", "Weekly Limit") == 10080
assert bucket_window_minutes("gemini-5h", "Gemini quota") == 300
assert bucket_window_minutes("gemini-5h limit", "Gemini quota") == 300
assert bucket_window_minutes("gemini_session", "Gemini") == 300
assert bucket_window_minutes("claude-gpt-weekly", "Weekly") == 10080
assert bucket_window_minutes("gemini-session-history", "Session History") is None

summary_payload = {
    "code": 0,
    "response": {
        "description": "Within each group, models share a weekly limit and a 5-hour limit.",
        "groups": [
            {
                "displayName": "Gemini Models",
                "buckets": [
                    {
                        "bucketId": "gemini-weekly",
                        "displayName": "Weekly Limit",
                        "remaining": {"remainingFraction": 0.5},
                        "resetTime": "2026-06-19T08:45:39Z",
                    },
                    {
                        "bucketId": "gemini-5h",
                        "displayName": "5h Limit",
                        "remaining": {"remainingFraction": 0.75},
                    },
                ],
            },
            {
                "displayName": "Claude and GPT Models",
                "buckets": [
                    {
                        "bucketId": "claude-gpt-weekly",
                        "displayName": "Weekly Limit",
                        "remaining": {"case": "remainingFraction", "value": 0.9},
                    },
                    {
                        "bucketId": "claude-gpt-5h",
                        "displayName": "5h Limit",
                        "disabled": True,
                        "remainingFraction": 0.1,
                    },
                ],
            },
        ],
    },
}
rows = _summary_rows(summary_payload)
assert len(rows) == 4
gemini_weekly = _worst_row(rows, 10080)
assert gemini_weekly and gemini_weekly["usedPercent"] == 50.0
assert gemini_weekly["resetsAt"] == "2026-06-19T08:45:39Z"
gemini_session = _worst_row(rows, 300)
assert gemini_session and gemini_session["usedPercent"] == 25.0
# A disabled bucket is never a known quota lane.
assert _worst_row(rows, 300) is not rows[3]
assert _worst_row(rows, 300)["usedPercent"] == 25.0
assert _worst_row([r for r in rows if r["known"]], 300)["usedPercent"] == 25.0
# The oneof remaining shape resolves through case/value.
assert rows[2]["usedPercent"] == 10.0

status_payload = {
    "userStatus": {
        "email": "dev@example.com",
        "planStatus": {"planInfo": {"planDisplayName": "AI Pro", "planName": "pro"}},
        "userTier": {"name": "Free tier"},
        "cascadeModelConfigData": {
            "clientModelConfigs": [
                {"label": "claude", "quotaInfo": {"remainingFraction": 0.25, "resetTime": 1760000000}},
                {"label": "gemini-pro", "quotaInfo": {"remainingFraction": 0.5, "resetTime": 1760000000}},
                {"label": "no-quota", "quotaInfo": {"resetTime": 1760000000}},
            ]
        },
    }
}
email, plan = _identity(status_payload)
assert email == "dev@example.com"
assert plan == "AI Pro"
legacy = _legacy_session_window(status_payload)
assert legacy["usedPercent"] == 75.0
assert legacy["label"] == "Session"
assert legacy["resetsAt"] == "2025-10-09T08:53:20Z"
assert _legacy_session_window({"userStatus": {}}) is None
tier_email, tier_plan = _identity({"userStatus": {"userTier": {"name": "Ultra"}}})
assert tier_email == "" and tier_plan == "Ultra"

assert _reset_time("2026-06-19T08:45:39Z") == "2026-06-19T08:45:39Z"
assert _reset_time(1760000000) == "2025-10-09T08:53:20Z"
assert _reset_time(1760000000000) == "2025-10-09T08:53:20Z"
assert _reset_time(None) is None
assert _reset_time("soon") is None

print("antigravity provider tests passed")
