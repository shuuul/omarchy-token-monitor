const assert = require("assert")
const { load } = require("./load")

const model = load("Model.js")
const providers = load("Providers.js")

assert.deepStrictEqual(Array.from(model.dashboardCommand({})), [
  "codexbar",
  "dashboard",
  "--identity",
  "full",
  "--timeout",
  "60",
])
assert.deepStrictEqual(
  Array.from(model.dashboardCommand({
    codexbarPath: "/opt/codexbar",
    identityMode: "redacted",
  })),
  ["/opt/codexbar", "dashboard", "--identity", "redacted", "--timeout", "60"],
)
assert.strictEqual(model.refreshIntervalSec({ refreshIntervalSec: 12 }), 30)
assert.strictEqual(model.refreshIntervalSec({ refreshIntervalSec: 9000 }), 3600)

const snapshot = {
  schemaVersion: 1,
  generatedAt: "2026-08-23T12:00:00Z",
  staleAfterSeconds: 180,
  host: { codexBarVersion: "0.47.0", refreshIntervalSeconds: 0 },
  providers: [
    {
      id: "codex",
      name: "Codex",
      enabled: true,
      source: "oauth",
      status: { level: "ok", label: "Operational" },
      identity: { accountEmail: "user@example.com", plan: "Plus" },
      windows: [
        {
          kind: "session",
          label: "Session",
          usedPercent: 28,
          remainingPercent: 72,
          resetAt: "2026-08-23T17:15:00Z",
        },
        {
          kind: "weekly",
          label: "Weekly",
          usedPercent: 59,
          remainingPercent: 41,
          resetAt: "2026-08-24T12:00:00Z",
        },
      ],
      credits: { remaining: 112.4, unit: "credits" },
      cost: { todayUSD: 1.04, last30DaysUSD: 18.22 },
      pace: {
        primary: { summary: "12% in deficit | Projected empty in 2h 30m" },
      },
      error: null,
      updatedAt: "2026-08-23T11:59:45Z",
    },
    {
      id: "cursor",
      name: "Cursor",
      enabled: true,
      source: "api",
      windows: [
        { kind: "session", label: "Plan", usedPercent: 91, remainingPercent: 9 },
      ],
      error: null,
    },
    {
      id: "claude",
      name: "Claude",
      windows: [{ kind: "session", usedPercent: 99 }],
    },
  ],
}

assert.ok(model.parseSnapshot(JSON.stringify(snapshot)))
assert.strictEqual(model.parseSnapshot('{"schemaVersion":2,"providers":[]}'), null)
assert.strictEqual(model.parseError("", 2), "codexbar is not on PATH")

const rows = model.providersFromSnapshot(
  snapshot,
  providers.enabledIds({}),
  providers.catalog(),
)
assert.strictEqual(rows.length, 7)
assert.strictEqual(rows.every((row) => providers.isSupported(row.id)), true)
assert.strictEqual(rows.some((row) => row.id === "claude"), false)

const codex = rows.find((row) => row.id === "codex")
assert.strictEqual(codex.name, "Codex")
assert.strictEqual(codex.windows.length, 2)
assert.strictEqual(codex.binding.title, "Weekly")
assert.strictEqual(codex.binding.usedPercent, 59)
assert.strictEqual(codex.creditsRemaining, 112.4)
assert.strictEqual(codex.paceSummary.includes("deficit"), true)
assert.strictEqual(codex.alarming, false)

const cursor = rows.find((row) => row.id === "cursor")
assert.strictEqual(cursor.alarming, true)
assert.strictEqual(cursor.binding.usedPercent, 91)

const kimi = rows.find((row) => row.id === "kimi")
assert.strictEqual(kimi.windows.length, 0)
assert.strictEqual(kimi.binding, null)

assert.strictEqual(model.barHeadline(rows).id, "cursor")
assert.strictEqual(model.barText(rows, false), "Cu 91%")
assert.ok(model.barTooltip(rows, false).includes("Cursor 91%"))
assert.strictEqual(model.formatCredits(112.4, "credits"), "112.4 credits")
assert.strictEqual(model.formatMoney(1.04), "$1.04")
assert.strictEqual(model.heroMeta(codex), "Plus")
assert.strictEqual(
  model.formatDuration(2 * 3600 * 1000 + 12 * 60 * 1000),
  "2h 12m",
)

const idleSnapshot = {
  schemaVersion: 1,
  providers: [
    {
      id: "amp",
      windows: [
        { kind: "session", label: "Daily", usedPercent: 10, idle: true },
        { kind: "weekly", label: "Other usage", usedPercent: 22 },
      ],
    },
  ],
}
const ampRows = model.providersFromSnapshot(idleSnapshot, ["amp"], providers.catalog())
assert.strictEqual(ampRows[0].windows.length, 1)
assert.strictEqual(ampRows[0].windows[0].title, "Weekly")

console.log("model tests passed")
