"""Antigravity usage from the local language server.

Google's Antigravity desktop app (and the `agy` CLI) runs a local HTTPS
language server on 127.0.0.1. The protocol is internal; CodexBar documents
the shapes this collector relies on:

- `RetrieveUserQuotaSummary` quota groups (Gemini / Claude+GPT, each with a
  5-hour and a weekly bucket), falling back to
- `GetUserStatus` legacy model quotas, which also carries the account email
  and plan name, then `GetCommandModelConfigs`.

The server port is never in the process arguments (`--https_server_port 0`),
so it is recovered by matching the process's socket inodes against its own
net/tcp tables, with `lsof` as a fallback. The `--csrf_token` argument stays
in the header and never reaches stdout.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from collector.http import loopback_http
from collector.schema import iso_from_unix, iso_now, row, window
from collector.security import bounded_secret, read_proc_bytes, run_bounded

MAX_PROBE_BYTES = 256 * 1024
MAX_PS_BYTES = 512 * 1024
MAX_LSOF_BYTES = 128 * 1024
MAX_PROC_TABLE_BYTES = 512 * 1024
MAX_PROC_FD_ENTRIES = 4096
MAX_PORTS_PER_PROCESS = 8
MAX_CANDIDATE_PROCESSES = 4
PROBE_TIMEOUT = 3
FETCH_DEADLINE_SECONDS = 30

UNLEASH_PATH = "/exa.language_server_pb.LanguageServerService/GetUnleashData"
QUOTA_SUMMARY_PATH = "/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary"
USER_STATUS_PATH = "/exa.language_server_pb.LanguageServerService/GetUserStatus"
MODEL_CONFIGS_PATH = "/exa.language_server_pb.LanguageServerService/GetCommandModelConfigs"

REQUEST_BODY = json.dumps({
    "metadata": {
        "ideName": "antigravity",
        "extensionName": "antigravity",
        "ideVersion": "unknown",
        "locale": "en",
    }
}).encode()

SESSION_MINUTES = 300
WEEKLY_MINUTES = 7 * 24 * 60

LANGUAGE_SERVER_PATTERN = re.compile(
    r"(^|[/\\])language(?:_|-)server(?:[_-][a-z0-9]+)*(?:\.exe)?(\s|$)")
CLI_PATH_PATTERN = re.compile(r"(^|[/\\])(antigravity-cli|antigravity_cli)([\s/\\]|$)")
AGY_PATTERN = re.compile(r"(^|[/\\])agy(\s|$)")
SOCKET_LINK_PATTERN = re.compile(r"socket:\[(\d+)\]")
FLAG_PATTERN_TEMPLATE = "{}[=\\s]+([^\\s]+)"

IDE_MARKERS = (
    "--app_data_dir antigravity-ide",
    "--app_data_dir=antigravity-ide",
    "/extensions/antigravity/bin/language_server",
    "\\extensions\\antigravity\\bin\\language_server",
)

KIND_ORDER = {"app": 0, "cli": 1, "ide": 2}


def _extract_flag(flag: str, command: str) -> str | None:
    match = re.search(FLAG_PATTERN_TEMPLATE.format(re.escape(flag)), command, re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def classify_process(command: str) -> str | None:
    """Classify one command line as app/cli/ide language server or None."""
    lower = command.lower()
    if LANGUAGE_SERVER_PATTERN.search(lower) and _is_antigravity_command(lower):
        return "ide" if any(marker in lower for marker in IDE_MARKERS) else "app"
    if CLI_PATH_PATTERN.search(lower) or AGY_PATTERN.search(lower):
        return "cli"
    return None


def _is_antigravity_command(lower: str) -> bool:
    if "--app_data_dir" in lower and "antigravity" in lower:
        return True
    if "antigravity.app/" in lower or "antigravity.app\\" in lower:
        return True
    if "/gemini.app/" in lower or "\\gemini.app\\" in lower:
        return True
    if "antigravity ide.app/" in lower or "antigravity ide.app\\" in lower:
        return True
    if "/antigravity/" in lower or "\\antigravity\\" in lower:
        return True
    return False


def candidate_processes(ps_output: str) -> list[dict]:
    """Pick language-server candidates out of `ps -ax -o pid=,command=` text."""
    found = []
    for line in ps_output.splitlines()[:4096]:
        trimmed = line.strip()
        if not trimmed:
            continue
        parts = trimmed.split(" ", 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        command = parts[1]
        kind = classify_process(command)
        if not kind:
            continue
        if kind == "cli":
            # The CLI language server requires no CSRF token.
            token = ""
        else:
            token = _extract_flag("--csrf_token", command)
            if not token:
                # App and IDE matches must authenticate with --csrf_token; a
                # tokenless match is skipped so a valid server can still win.
                continue
            token = bounded_secret(token)
            if token is None:
                continue
        extension_port = _extract_flag("--extension_server_port", command)
        extension_port = int(extension_port) if extension_port and extension_port.isdigit() else None
        if extension_port is not None and not 1 <= extension_port <= 65535:
            extension_port = None
        extension_token = _extract_flag("--extension_server_csrf_token", command)
        extension_token = bounded_secret(extension_token or "")
        found.append({
            "pid": int(parts[0]),
            "kind": kind,
            "csrf": token,
            "extensionPort": extension_port,
            "extensionCsrf": extension_token or token,
        })
    found.sort(key=lambda entry: KIND_ORDER[entry["kind"]])
    return found[:MAX_CANDIDATE_PROCESSES]


def parse_proc_tcp_listeners(content: str, socket_inodes: set[str]) -> set[int]:
    """Parse /proc/<pid>/net/tcp{,6} LISTEN ports owned by socket_inodes."""
    ports: set[int] = set()
    for line in content.splitlines()[:16384]:
        columns = line.split()
        if len(columns) < 10 or columns[3] != "0A":
            continue
        if columns[9] not in socket_inodes:
            continue
        local = columns[1]
        if ":" not in local:
            continue
        try:
            port = int(local.rsplit(":", 1)[1], 16)
        except ValueError:
            continue
        if 1 <= port <= 65535:
            ports.add(port)
    return ports


def proc_listening_ports(pid: int) -> list[int]:
    fd_dir = f"/proc/{pid}/fd"
    try:
        entries = os.listdir(fd_dir)[:MAX_PROC_FD_ENTRIES]
    except OSError:
        return []
    inodes: set[str] = set()
    for entry in entries:
        try:
            target = os.readlink(f"{fd_dir}/{entry}")
        except OSError:
            continue
        match = SOCKET_LINK_PATTERN.fullmatch(target[:128])
        if match:
            inodes.add(match.group(1))
    if not inodes:
        return []
    ports: set[int] = set()
    for table in (f"/proc/{pid}/net/tcp", f"/proc/{pid}/net/tcp6"):
        try:
            content = read_proc_bytes(Path(table), MAX_PROC_TABLE_BYTES).decode(
                "ascii", errors="replace")
        except (OSError, ValueError):
            continue
        ports.update(parse_proc_tcp_listeners(content, inodes))
    return sorted(ports)[:MAX_PORTS_PER_PROCESS]


def lsof_listening_ports(pid: int) -> list[int]:
    try:
        result = run_bounded(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", str(pid)],
            timeout=5,
            max_bytes=MAX_LSOF_BYTES,
            text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    ports = set()
    for raw in re.findall(r":(\d+)\s+\(LISTEN\)", result.stdout)[:MAX_PORTS_PER_PROCESS * 4]:
        port = int(raw)
        if 1 <= port <= 65535:
            ports.add(port)
    return sorted(ports)[:MAX_PORTS_PER_PROCESS]


def listening_ports(pid: int) -> list[int]:
    ports = proc_listening_ports(pid)
    if ports:
        return ports
    return lsof_listening_ports(pid)


def _post(endpoint: dict, path: str) -> tuple[int, bytes]:
    headers = {}
    if endpoint["csrf"]:
        headers["X-Codeium-Csrf-Token"] = endpoint["csrf"]
    return loopback_http(
        endpoint["port"],
        path,
        body=REQUEST_BODY,
        headers=headers,
        max_bytes=MAX_PROBE_BYTES,
        timeout=PROBE_TIMEOUT,
        tls=endpoint["tls"],
    )


def _payload_ok(payload: dict) -> bool:
    code = payload.get("code")
    if code is None:
        return True
    if isinstance(code, bool):
        return code
    if isinstance(code, int):
        return code == 0
    if isinstance(code, str):
        return code.lower() in ("ok", "success", "0")
    return True


def _fetch_payload(endpoint: dict, path: str) -> dict | None:
    if time.monotonic() >= endpoint["deadline"]:
        return None
    status, body, _ = _post(endpoint, path)
    if status != 200:
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not _payload_ok(payload):
        return None
    return payload


def _endpoint_candidates(entry: dict, deadline: float) -> list[dict]:
    endpoints = []
    for port in listening_ports(entry["pid"]):
        endpoints.append({"port": port, "tls": True, "csrf": entry["csrf"], "deadline": deadline})
    if entry["extensionPort"]:
        endpoints.append({
            "port": entry["extensionPort"],
            "tls": False,
            "csrf": entry["extensionCsrf"],
            "deadline": deadline,
        })
    return endpoints


def _probe_endpoints(endpoints: list[dict]) -> dict | None:
    """First endpoint whose language server answers GetUnleashData with 200."""
    for endpoint in endpoints:
        if time.monotonic() >= endpoint["deadline"]:
            return None
        status, _, _ = _post(endpoint, UNLEASH_PATH)
        if status == 200:
            return endpoint
    return None


def _fraction(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    fraction = float(value)
    if 0 <= fraction <= 1:
        return fraction
    return None


def _bucket_remaining_fraction(bucket: dict) -> float | None:
    fraction = _fraction(bucket.get("remainingFraction"))
    if fraction is not None:
        return fraction
    remaining = bucket.get("remaining")
    if not isinstance(remaining, dict):
        return None
    fraction = _fraction(remaining.get("remainingFraction"))
    if fraction is not None:
        return fraction
    if remaining.get("case") == "remainingFraction":
        return _fraction(remaining.get("value"))
    return None


def _reset_time(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        text = str(value or "").strip()[:64]
        if re.match(r"^\d{4}-\d{2}-\d{2}T", text):
            return text
        if text.isdigit():
            return iso_from_unix(int(text))
        return None
    seconds = float(value)
    if seconds > 10**12:
        seconds /= 1000.0
    return iso_from_unix(seconds)


SESSION_CADENCE_ALIASES = ("session", "5h", "5-hour", "five hour", "five-hour")


def bucket_window_minutes(bucket_id: str, display_name: str) -> int | None:
    """Infer the cadence from the bucket id/display name, like the quota UI."""
    candidates: set[str] = set()
    for raw in (bucket_id, display_name):
        normalized = str(raw or "").strip().lower().replace("_", "-")
        if not normalized:
            continue
        variants = [normalized]
        if normalized.endswith(" limit"):
            variants.append(normalized[: -len(" limit")])
        for variant in variants:
            candidates.add(variant)
            for alias in SESSION_CADENCE_ALIASES + ("weekly",):
                if variant.endswith("-" + alias):
                    candidates.add(alias)
    if candidates.intersection(SESSION_CADENCE_ALIASES):
        return SESSION_MINUTES
    if "weekly" in candidates:
        return WEEKLY_MINUTES
    return None


def _group_title(name: str) -> str:
    lowered = name.strip().lower()
    if "gemini" in lowered:
        return "Gemini"
    if "claude" in lowered or "gpt" in lowered:
        return "Claude/GPT"
    return name.strip()[:48] or "Quota"


def _summary_rows(payload: dict) -> list[dict]:
    groups = None
    for key in ("response", "summary"):
        node = payload.get(key)
        if isinstance(node, dict) and isinstance(node.get("groups"), list):
            groups = node["groups"]
            break
    if groups is None and isinstance(payload.get("groups"), list):
        groups = payload["groups"]
    if not groups:
        return []
    rows = []
    for group in groups[:16]:
        if not isinstance(group, dict):
            continue
        title = _group_title(str(group.get("displayName") or ""))
        buckets = group.get("buckets")
        if not isinstance(buckets, list):
            continue
        for bucket in buckets[:32]:
            if not isinstance(bucket, dict):
                continue
            bucket_id = str(bucket.get("bucketId") or "").strip()
            if not bucket_id:
                continue
            display_name = str(bucket.get("displayName") or "").strip() or bucket_id
            fraction = _bucket_remaining_fraction(bucket)
            known = bucket.get("disabled") is not True and fraction is not None
            rows.append({
                "title": f"{title} {display_name}",
                "known": known,
                "usedPercent": max(0.0, min(100.0, 100.0 - fraction * 100.0)) if fraction is not None else 0.0,
                "windowMinutes": bucket_window_minutes(bucket_id, display_name),
                "resetsAt": _reset_time(bucket.get("resetTime")),
            })
    return rows


def _worst_row(rows: list[dict], minutes: int) -> dict | None:
    known = [entry for entry in rows if entry["known"] and entry["windowMinutes"] == minutes]
    if not known:
        return None
    return max(known, key=lambda entry: entry["usedPercent"])


def _legacy_client_model_configs(payload: dict) -> list:
    user_status = payload.get("userStatus")
    if isinstance(user_status, dict):
        cascade = user_status.get("cascadeModelConfigData")
        if isinstance(cascade, dict) and isinstance(cascade.get("clientModelConfigs"), list):
            return cascade["clientModelConfigs"][:32]
    configs = payload.get("clientModelConfigs")
    if isinstance(configs, list):
        return configs[:32]
    return []


def _legacy_session_window(payload: dict) -> dict | None:
    worst: dict | None = None
    for config in _legacy_client_model_configs(payload):
        if not isinstance(config, dict):
            continue
        quota = config.get("quotaInfo")
        if not isinstance(quota, dict):
            continue
        fraction = _fraction(quota.get("remainingFraction"))
        if fraction is None:
            continue
        used = max(0.0, min(100.0, 100.0 - fraction * 100.0))
        if worst is None or used > worst["usedPercent"]:
            worst = {
                "known": True,
                "usedPercent": used,
                "resetsAt": _reset_time(quota.get("resetTime")),
            }
    if not worst:
        return None
    return window(worst["usedPercent"], None, worst["resetsAt"], "Session")


def _identity(payload: dict | None) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return "", ""
    user_status = payload.get("userStatus")
    if not isinstance(user_status, dict):
        return "", ""
    email_value = user_status.get("email")
    email = email_value.strip()[:254] if isinstance(email_value, str) else ""
    plan = ""
    plan_status = user_status.get("planStatus")
    plan_info = plan_status.get("planInfo") if isinstance(plan_status, dict) else None
    if isinstance(plan_info, dict):
        for key in ("planDisplayName", "displayName", "productName", "planName", "planShortName"):
            value = plan_info.get(key)
            if isinstance(value, str) and value.strip():
                plan = value.strip()[:128]
                break
    if not plan:
        tier = user_status.get("userTier")
        if isinstance(tier, dict) and isinstance(tier.get("name"), str) and tier["name"].strip():
            plan = tier["name"].strip()[:128]
    return email, plan


def _usage_rows(entry: dict, deadline: float) -> dict | None:
    endpoints = _endpoint_candidates(entry, deadline)
    if not endpoints:
        return None
    endpoint = _probe_endpoints(endpoints)
    if endpoint is None:
        return None
    summary_payload = _fetch_payload(endpoint, QUOTA_SUMMARY_PATH)
    status_payload = _fetch_payload(endpoint, USER_STATUS_PATH)
    email, plan = _identity(status_payload)
    primary = secondary = None
    summary_rows = _summary_rows(summary_payload) if summary_payload else []
    if summary_rows:
        worst_session = _worst_row(summary_rows, SESSION_MINUTES)
        worst_weekly = _worst_row(summary_rows, WEEKLY_MINUTES)
        if worst_session:
            primary = window(
                worst_session["usedPercent"], SESSION_MINUTES,
                worst_session["resetsAt"], "Session")
        if worst_weekly:
            secondary = window(
                worst_weekly["usedPercent"], WEEKLY_MINUTES,
                worst_weekly["resetsAt"], "Weekly")
    if primary is None and secondary is None:
        if status_payload:
            primary = _legacy_session_window(status_payload)
        if primary is None:
            configs_payload = _fetch_payload(endpoint, MODEL_CONFIGS_PATH)
            if configs_payload:
                primary = _legacy_session_window(configs_payload)
    if primary is None and secondary is None:
        return None
    usage = {
        "accountEmail": email,
        "loginMethod": plan,
        "identity": {
            "providerID": "antigravity",
            "accountEmail": email,
            "plan": plan,
            "loginMethod": plan,
        },
        "primary": primary,
        "secondary": secondary,
        "tertiary": None,
        "extraRateWindows": [],
        "updatedAt": iso_now(),
    }
    return usage


def fetch_antigravity() -> dict:
    try:
        ps_result = run_bounded(
            ["ps", "-ax", "-o", "pid=,command="],
            timeout=5,
            max_bytes=MAX_PS_BYTES,
            text=True,
        )
    except OSError:
        ps_result = None
    candidates = candidate_processes(ps_result.stdout) if ps_result and ps_result.returncode == 0 else []
    if not candidates:
        return row(
            "antigravity",
            source="local",
            error="Open Antigravity (or run `agy` and sign in) to read usage.",
        )
    deadline = time.monotonic() + FETCH_DEADLINE_SECONDS
    for entry in candidates:
        usage = _usage_rows(entry, deadline)
        if usage is not None:
            return row("antigravity", source="local", usage=usage)
    return row(
        "antigravity",
        source="local",
        error="Antigravity is signed in, but its local usage server did not answer.",
    )
