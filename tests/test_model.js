const assert = require("assert")
const { load } = require("./load")

const model = load("Model.js")
const providers = load("Providers.js")

assert.deepStrictEqual(Array.from(model.collectCommand({})), [
  "/usr/bin/timeout",
  "25",
  "/usr/bin/python3",
  "collect.py",
])
assert.deepStrictEqual(
  Array.from(model.collectCommand({ collectPath: "/tmp/collect.py" })),
  ["/usr/bin/timeout", "25", "/usr/bin/python3", "/tmp/collect.py"],
)
assert.strictEqual(model.refreshIntervalSec({ refreshIntervalSec: 12 }), 30)
assert.strictEqual(model.refreshIntervalSec({ refreshIntervalSec: 9000 }), 3600)

const snapshot = [
  {
    provider: "codex",
    source: "oauth",
    usage: {
      accountEmail: "user@example.com",
      loginMethod: "plus",
      identity: { accountEmail: "user@example.com", loginMethod: "plus" },
      primary: { usedPercent: 28, windowMinutes: 300, resetsAt: "2026-08-23T17:15:00Z" },
      secondary: { usedPercent: 59, windowMinutes: 10080, resetsAt: "2026-08-24T12:00:00Z" },
      tertiary: null,
      extraRateWindows: [
        { id: "codex-spark", title: "Codex Spark 5-hour", window: { usedPercent: 0, windowMinutes: 300 } },
      ],
    },
    credits: { remaining: 112.4 },
    pace: {
      primary: { summary: "12% in deficit | Projected empty in 2h 30m" },
    },
    error: null,
  },
  {
    provider: "cursor",
    source: "api",
    usage: {
      primary: { usedPercent: 91, windowMinutes: 300 },
    },
    error: null,
  },
  {
    provider: "claude",
    usage: {
      primary: { usedPercent: 99 },
    },
  },
]

assert.ok(model.parseSnapshot(JSON.stringify(snapshot)))
assert.strictEqual(model.parseSnapshot("not-json"), null)
assert.strictEqual(model.parseError("", 2), "codexbar is not on PATH")

const parsed = model.parseSnapshot(JSON.stringify(snapshot))
const rows = model.providersFromSnapshot(
  parsed,
  Array.from(providers.enabledIds({})),
  providers.catalog(),
)
assert.strictEqual(rows.length, 7)
assert.strictEqual(rows.every((row) => providers.isSupported(row.id)), true)
assert.strictEqual(rows.some((row) => row.id === "claude"), false)

const codex = rows.find((row) => row.id === "codex")
assert.strictEqual(codex.name, "Codex")
assert.strictEqual(codex.windows.length, 3)
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
assert.strictEqual(model.barText(rows, false), "Cursor 91%")
assert.strictEqual(model.barIconId(rows, false), "cursor")
assert.ok(model.barTooltip(rows, false).includes("Cursor 91%"))
assert.strictEqual(model.formatCredits(112.4, "credits"), "112.4 credits")
assert.strictEqual(model.formatMoney(1.04), "$1.04")
assert.strictEqual(model.heroMeta(codex), "plus")
assert.strictEqual(
  model.formatDuration(2 * 3600 * 1000 + 12 * 60 * 1000),
  "2h 12m",
)

assert.strictEqual(codex.windows.length, 3)
assert.strictEqual(codex.plan, "plus")

const idleSnapshot = {
  providers: [
    {
      provider: "amp",
      usage: {
        primary: { usedPercent: 10, idle: true },
        secondary: { usedPercent: 22, windowMinutes: 10080 },
      },
    },
  ],
}
const ampRows = model.providersFromSnapshot(idleSnapshot, ["amp"], providers.catalog())
assert.strictEqual(ampRows[0].windows.length, 1)
assert.strictEqual(ampRows[0].windows[0].title, "Weekly")

console.log("model tests passed")
