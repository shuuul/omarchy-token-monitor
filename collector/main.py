from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from collector.cookies import preferred_jars
from collector.providers.amp import fetch_amp
from collector.providers.codex import fetch_codex
from collector.providers.cursor import fetch_cursor
from collector.providers.factory import fetch_factory
from collector.providers.grok import fetch_grok
from collector.providers.kimi import fetch_kimi
from collector.providers.notion import fetch_notion
from collector.providers.zed import fetch_zed
from collector.schema import row
from collector.security import MAX_SNAPSHOT_BYTES, snapshot_json

PROVIDERS = ("amp", "codex", "kimi", "cursor", "grok", "notion", "zed", "factory")

def requested_providers(settings: dict, argv: list[str] | None = None) -> tuple[str, ...]:
    args = list(argv or [])
    wanted: list[str] = []
    skip = False
    for item in args:
        if skip:
            skip = False
            continue
        if item in ("-p", "--provider"):
            skip = True
            continue
        if item.startswith("--provider="):
            wanted.append(item.split("=", 1)[1])
            continue
        if item.startswith("-") or item.endswith(".py"):
            continue
        wanted.append(item)
    only = str((settings or {}).get("only") or "").strip()
    if only:
        wanted.append(only)
    names = []
    for name in wanted:
        if name in PROVIDERS and name not in names:
            names.append(name)
    return tuple(names) if names else PROVIDERS


def collect(settings: dict | None = None, argv: list[str] | None = None) -> list[dict]:
    settings = settings or {}
    enabled = settings.get("providers") or {}
    browser, jars = preferred_jars(settings)
    fetchers = {
        "amp": lambda: fetch_amp(jars),
        "codex": fetch_codex,
        "kimi": lambda: fetch_kimi(jars),
        "cursor": lambda: fetch_cursor(jars),
        "grok": lambda: fetch_grok(jars),
        "notion": lambda: fetch_notion(jars),
        "zed": lambda: fetch_zed(jars),
        "factory": lambda: fetch_factory(jars),
    }
    wanted = []
    for provider in requested_providers(settings, argv):
        entry = enabled.get(provider) if isinstance(enabled, dict) else None
        if entry and entry.get("enabled") is False:
            continue
        wanted.append(provider)

    def fetch(provider: str) -> dict:
        try:
            return fetchers[provider]()
        except Exception as exc:
            return row(provider, source=browser, error=str(exc))

    if not wanted:
        return []
    # Providers are fetched in parallel so a full snapshot stays well under
    # the timeout the QML side wraps around collect.py.
    with ThreadPoolExecutor(max_workers=len(wanted)) as pool:
        return list(pool.map(fetch, wanted))


def main() -> int:
    settings = {}
    raw = os.environ.get("OTM_SETTINGS_JSON")
    if raw:
        try:
            if len(raw.encode("utf-8")) <= MAX_SNAPSHOT_BYTES:
                settings = json.loads(raw)
        except json.JSONDecodeError:
            settings = {}
    try:
        rows = collect(settings, sys.argv[1:])
    except Exception as exc:
        rows = [row("collector", source="local", error=str(exc))]
    sys.stdout.write(snapshot_json(rows) + "\n")
    return 0
