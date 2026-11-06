"""Read one CodexBar provider entry from the local CLI config.

Only the matching providers[] row is examined. Secrets stay behind
bounded_secret and are never logged or returned wholesale.
"""

from __future__ import annotations

from typing import Mapping

from collector.cookies import HOME
from collector.security import bounded_secret, read_json

CODEXBAR_CONFIG = HOME / ".config" / "codexbar" / "config.json"


def provider_entry(provider_id: str, config: Mapping[str, object] | None = None) -> dict[str, object] | None:
    """Return the first providers[] object whose id matches provider_id.

    Args:
        provider_id: CodexBar provider id to look up.
        config: Optional already-parsed config mapping. When omitted, reads
            ``~/.config/codexbar/config.json`` through read_json.

    Returns:
        The matching provider dict, or None when absent or malformed.
    """
    wanted = str(provider_id or "").strip()
    if not wanted:
        return None
    data = config
    if data is None:
        try:
            loaded = read_json(CODEXBAR_CONFIG)
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(loaded, dict):
            return None
        data = loaded
    providers = data.get("providers")
    if not isinstance(providers, list):
        return None
    for item in providers:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "").strip() != wanted:
            continue
        return item
    return None


def provider_secret(entry: Mapping[str, object] | None, key: str = "cookieHeader") -> str | None:
    """Extract a bounded secret field from a CodexBar provider entry.

    Args:
        entry: Provider dict from provider_entry.
        key: Field name holding the credential (default cookieHeader).

    Returns:
        Bounded secret string, or None.
    """
    if not entry:
        return None
    return bounded_secret(entry.get(key))


def provider_workspace_id(entry: Mapping[str, object] | None) -> str | None:
    """Extract a bounded workspace / organization id from a provider entry.

    Args:
        entry: Provider dict from provider_entry.

    Returns:
        Bounded workspaceID string, or None.
    """
    if not entry:
        return None
    return bounded_secret(entry.get("workspaceID"))
