#!/usr/bin/env bash
set -euo pipefail

# Vendor HTTP stays in collect.py. QML only renders.
grep -Fq 'collect.py' Model.js
grep -Fq '/usr/bin/python3' Model.js
grep -Fq 'Model.collectCommand({' Service.qml
! grep -Eq 'ampcode.com|chatgpt.com|api.kimi.com|cursor.com|cli-chat-proxy.grok.com|app.notion.com|cloud.zed.dev' \
  Model.js Providers.js Service.qml Panel.qml
grep -Fq 'ampcode.com' collect.py

# The supported set is closed and uses CodexBar IDs exactly.
grep -Fq '{ id: "amp", name: "Amp"' Providers.js
grep -Fq '{ id: "codex", name: "Codex"' Providers.js
grep -Fq '{ id: "kimi", name: "Kimi Code"' Providers.js
grep -Fq '{ id: "cursor", name: "Cursor"' Providers.js
grep -Fq '{ id: "grok", name: "Grok"' Providers.js
grep -Fq '{ id: "notion", name: "Notion AI"' Providers.js
grep -Fq '{ id: "zed", name: "Zed"' Providers.js
[[ "$(grep -c '{ id: "' Providers.js)" -eq 7 ]]

# Panel wiring follows the Omarchy agents / clock contract.
grep -Fq 'moduleName: "shuuul.token-monitor"' Panel.qml
grep -Fq 'ipcTarget: "shuuul.token-monitor"' Panel.qml
grep -Fq 'function refresh(): string' Panel.qml
grep -Fq 'function next(): string' Panel.qml
grep -Fq 'usage.refresh()' Panel.qml
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
