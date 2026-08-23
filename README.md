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

This plugin does not talk to those vendors. It runs `codexbar usage --format json --json-only` and draws that snapshot. `codexbar dashboard` 0.53.0 segfaults on this machine.

## Why wrap CodexBar

There is no existing Omarchy plugin that covers this set.

Closest references:

- First-party `omarchy.agents` — Claude, Codex, Fireworks only; local collectors, not CodexBar.
- [robzolkos/omarchy-agent-usage](https://github.com/robzolkos/omarchy-agent-usage) — Claude + Codex only.
- [noctalia-codex-usage](https://github.com/rayoplateado/noctalia-codex-usage) and [CodexBar Meter](https://github.com/noctalia-dev/community-plugins/tree/main/codexbar-meter) — Quickshell, but Noctalia, not Omarchy.
- [codexbar-waybar](https://github.com/Marouan-chak/codexbar-waybar) — official Linux integration pattern: UI wraps the CodexBar CLI.

Reimplementing Amp / Codex / Kimi / Cursor / Grok / Notion / Zed auth would drift from CodexBar. The Linux CLI is the portable core.

## Install

1. Install the CodexBar Linux CLI (`yay -S codexbar-cli`, or a [release tarball](https://github.com/steipete/CodexBar/releases)).
2. Sign in through each vendor's own CLI or put credentials in `~/.config/codexbar/config.json`.
3. Enable only the seven providers above:

```bash
codexbar config enable --provider amp
codexbar config enable --provider codex
codexbar config enable --provider kimi
codexbar config enable --provider cursor
codexbar config enable --provider grok
codexbar config enable --provider notion
codexbar config enable --provider zed
```

4. Add the plugin:

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
| `codexbarPath` | `codexbar` | CLI command or absolute path |
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
