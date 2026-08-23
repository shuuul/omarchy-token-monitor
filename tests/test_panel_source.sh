#!/usr/bin/env bash
set -euo pipefail

# Vendor HTTP stays in collect.py. QML only renders.
grep -Fq 'collect.py' Model.js
grep -Fq '/usr/bin/python3' Model.js
! grep -Fq 'PATH=' Model.js
grep -Fq 'Model.collectCommand({' Service.qml
! grep -Eq 'ampcode.com|chatgpt.com|api.kimi.com|cursor.com|cli-chat-proxy.grok.com|app.notion.com|cloud.zed.dev' \
  Model.js Providers.js Service.qml Panel.qml
grep -Fq 'ampcode.com' collect.py
grep -Fq 'auth.kimi.com/api/oauth/token' collect.py
grep -Fq 'auth.kimi.ai/api/oauth/token' collect.py
grep -Fq 'zed-github-account' collect.py

# The supported set is closed and uses CodexBar IDs exactly.
grep -Fq '{ id: "amp", name: "Amp"' Providers.js
grep -Fq '{ id: "codex", name: "Codex"' Providers.js
grep -Fq '{ id: "kimi", name: "Kimi Code"' Providers.js
grep -Fq '{ id: "cursor", name: "Cursor"' Providers.js
grep -Fq '{ id: "grok", name: "Grok"' Providers.js
grep -Fq '{ id: "notion", name: "Notion AI"' Providers.js
grep -Fq '{ id: "zed", name: "Zed"' Providers.js
grep -Fq '{ id: "factory", name: "Droid"' Providers.js
[[ "$(grep -c '{ id: "' Providers.js)" -eq 8 ]]

# Provider marks come from CodexBar ProviderIcon-*.svg. Qt paints currentColor
# as black, so fills must be white for MultiEffect to tint the bar foreground.
for id in amp codex kimi cursor grok notion zed factory; do
  grep -Fq '#ffffff' "assets/${id}.svg"
  ! grep -Fq 'currentColor' "assets/${id}.svg"
done
# Distinct official marks, not the old monogram placeholders.
! grep -Fq 'M12 3 4 21h3.1l1.5-3.4h6.8L16.9 21H20L12 3zm0 6.2' assets/amp.svg
grep -Fq 'M13.9197 13.61L17.3816 26.566L14.242 27.4049' assets/amp.svg
grep -Fq 'M83.7733 42.8087' assets/codex.svg
grep -Fq 'M84.0704 28.9353L51.9066 10.4454' assets/cursor.svg
grep -Fq 'M9.27 15.29l7.978-5.897' assets/grok.svg
grep -Fq 'M21.7202 0.939941' assets/kimi.svg
grep -Fq 'M15.257.055l-13.31.98' assets/notion.svg
grep -Fq 'M2.25 1.5a.75.75 0 0 0-.75.75v16.5H0V2.25' assets/zed.svg
grep -Fq 'M67.8515 23.9286C67.6213 23.8754' assets/factory.svg

# Panel wiring follows the Omarchy agents / clock contract.
grep -Fq 'text: modelData.name' Panel.qml
grep -Fq 'assets/" + modelData.id + ".svg' Panel.qml
grep -Fq 'Model.iconWindows' Panel.qml
grep -Fq 'id: usageBars' Panel.qml
grep -Fq 'colorizationColor' Panel.qml
grep -Fq 'Style.bar.iconCanvas' Panel.qml
grep -Fq 'anchors.verticalCenter: parent.verticalCenter' Panel.qml
grep -Fq 'formatUpdatedAt' Panel.qml
grep -Fq 'Refresh " + root.provider.name' Panel.qml
grep -Fq 'text: "Usage dashboard"' Panel.qml
grep -Fq 'Qt.openUrlExternally' Panel.qml
grep -Fq 'dashboardUrl: "https://ampcode.com/settings/usage"' Providers.js
grep -Fq 'dashboardUrl: "https://chatgpt.com/codex/settings/usage"' Providers.js
grep -Fq 'dashboardUrl: "https://www.kimi.com/code/console"' Providers.js
grep -Fq 'dashboardUrl: "https://cursor.com/dashboard?tab=usage"' Providers.js
grep -Fq 'dashboardUrl: "https://grok.com/?_s=usage"' Providers.js
grep -Fq 'dashboardUrl: "https://app.notion.com/"' Providers.js
grep -Fq 'dashboardUrl: "https://app.factory.ai/settings/billing"' Providers.js
grep -Fq 'text: "Extra usage"' Panel.qml
grep -Fq 'tooltipText: "Settings"' Panel.qml
grep -Fq 'Refresh interval' Panel.qml
grep -Fq 'Browser cookies' Panel.qml
grep -Fq 'Drag a row to reorder the main panel.' Panel.qml
grep -Fq 'settingsProviderModel.move' Panel.qml
grep -Fq 'providerOrder' Panel.qml
grep -Fq 'Flow {' Panel.qml
! grep -Fq 'leftAlign: true' Panel.qml
! grep -Fq 'width: providerSwitch.width' Panel.qml
grep -Fq 'moduleName: "shuuul.token-monitor"' Panel.qml
grep -Fq 'ipcTarget: "shuuul.token-monitor"' Panel.qml
grep -Fq 'function refresh(): string' Panel.qml
grep -Fq 'function next(): string' Panel.qml
# Opening the panel fetches every provider only when Settings → Refresh
# on open is on. The default stays off.
grep -Fq 'label: "Refresh on open"' Panel.qml
grep -Fq 'label: "Show remaining"' Panel.qml
grep -Fq 'label: "Hide email"' Panel.qml
grep -Fq 'Model.refreshOnOpen(root.settings)' Panel.qml
grep -Fq 'if (Model.refreshOnOpen(root.settings)) usage.refresh("")' Panel.qml
grep -Fq 'usage.refresh(onlyId || selectedProviderId)' Panel.qml
! grep -Eq '\broot\.state\b' Service.qml Panel.qml

# Nested Component blocks must not use an ambiguous `root.`
python3 - <<'PY'
import re
import sys

source = open("Panel.qml").read()
problems = []
for match in re.finditer(r"Component\s*\{", source):
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                body = source[start:index + 1]
                if re.search(r"\broot\.", body):
                    problems.append(body.strip()[:80])
                break

if problems:
    print("Component blocks reference an ambiguous `root.`.", file=sys.stderr)
    sys.exit(1)
print("component scoping ok")
PY

echo "panel source tests passed"
