# Token Monitor

Omarchy bar plugin for [CodexBar](https://github.com/steipete/CodexBar) quotas.

Supported providers, IDs matching CodexBar exactly:

| Display | CodexBar ID |
| --- | --- |
| Amp | `amp` |
| Codex | `codex` |
| Kimi Code | `kimi` |
| Cursor | `cursor` |
| Grok | `grok` |
| Notion AI | `notion` |
| Zed | `zed` |

This plugin talks to the vendor APIs itself. Chrome/Chromium cookies cover Cursor, Notion, Grok, and Amp. Codex uses `~/.codex/auth.json`. Amp prefers `amp usage`. Kimi uses the Kimi Code CLI token. Zed has no Linux cookie path yet.

## Why wrap CodexBar

There is no existing Omarchy plugin that covers this set.

Closest references:

- First-party `omarchy.agents` — Claude, Codex, Fireworks only; local collectors, not CodexBar.
- [robzolkos/omarchy-agent-usage](https://github.com/robzolkos/omarchy-agent-usage) — Claude + Codex only.
- [noctalia-codex-usage](https://github.com/rayoplateado/noctalia-codex-usage) and [CodexBar Meter](https://github.com/noctalia-dev/community-plugins/tree/main/codexbar-meter) — Quickshell, but Noctalia, not Omarchy.
- [codexbar-waybar](https://github.com/Marouan-chak/codexbar-waybar) — official Linux integration pattern: UI wraps the CodexBar CLI.

Reimplementing Amp / Codex / Kimi / Cursor / Grok / Notion / Zed auth would drift from CodexBar. The Linux CLI is the portable core.

## Install

1. Sign in to Chrome (or Chromium) for Cursor, Notion, Grok, and Amp.
2. Sign in locally for Codex (`codex login`) and Amp (`amp`).
3. Add the plugin:

```bash
omarchy plugin add <this-git-url> --enable
```

During local development:

```bash
ln -sfn "$PWD" ~/.config/omarchy/plugins/shuuul.token-monitor
omarchy-shell shell rescanPlugins
```

`omarchy plugin add` refuses symlinks inside a plugin folder. Use a real git checkout for install, a symlink only for development.

## Use

- Left click: open the panel
- Right click: refresh
- Middle click / `h` `l`: next provider
- `r` or Enter: refresh
- Esc: close

Bar text is `Cu 91%` — monogram plus the fullest window across enabled providers.

## Settings

In `~/.config/omarchy/shell.json`, on the `shuuul.token-monitor` entry:

| Key | Default | Meaning |
| --- | --- | --- |
| `browser` | `chrome` | `chrome` or `chromium` cookies |
| `refreshIntervalSec` | `300` | Poll interval |
| `providers.<id>.enabled` | `true` | Hide one of the seven without changing CodexBar |

Nested enablement needs the whole object:

```bash
omarchy bar set shuuul.token-monitor providers '{
  "amp": { "enabled": true },
  "codex": { "enabled": true },
  "kimi": { "enabled": true },
  "cursor": { "enabled": true },
  "grok": { "enabled": false },
  "notion": { "enabled": false },
  "zed": { "enabled": true }
}' --json
```

## Linux auth notes

CodexBar's macOS browser-cookie import is not available here. Prefer CLI / OAuth / API / manual cookie paths:

- Amp: `amp usage` or an Amp access token
- Codex: `~/.codex/auth.json` or Codex CLI RPC
- Kimi: `KIMI_CODE_API_KEY` or `~/.kimi-code/credentials/kimi-code.json`
- Cursor: manual cookie header in CodexBar config
- Grok: `~/.grok/auth.json` or `grok` CLI
- Notion: manual `token_v2` / Cookie header
- Zed: Linux credential store, same `{user_id} {access_token}` request as CodexBar

## Develop

```bash
make test
make qml-check    # needs Omarchy + qmllint
make validate
```

## License

MIT
