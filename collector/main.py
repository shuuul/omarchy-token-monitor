from __future__ import annotations

import json
import os
import sys

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
        "zed": fetch_zed,
        "factory": lambda: fetch_factory(jars),
    }
    out = []
    for provider in requested_providers(settings, argv):
        entry = enabled.get(provider) if isinstance(enabled, dict) else None
        if entry and entry.get("enabled") is False:
            continue
        try:
            out.append(fetchers[provider]())
        except Exception as exc:
            out.append(row(provider, source=browser, error=str(exc)))
    return out


def main() -> int:
    settings = {}
    raw = os.environ.get("OTM_SETTINGS_JSON")
    if raw:
        settings = json.loads(raw)
    print(json.dumps(collect(settings, sys.argv[1:]), separators=(",", ":")))
    return 0
