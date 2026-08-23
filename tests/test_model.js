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
assert.deepStrictEqual(
  Array.from(model.collectCommand({ collectPath: "/tmp/collect.py", only: "grok" })),
  ["/usr/bin/timeout", "25", "/usr/bin/python3", "/tmp/collect.py", "grok"],
)
assert.deepStrictEqual(
  model.mergeProviderRows(
    [{ provider: "codex", usage: { loginMethod: "old" } }, { provider: "grok", usage: { loginMethod: "keep" } }],
    [{ provider: "codex", usage: { loginMethod: "new" } }],
  ),
  [{ provider: "codex", usage: { loginMethod: "new" } }, { provider: "grok", usage: { loginMethod: "keep" } }],
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
assert.strictEqual(model.barIconId(rows, false), "cursor")
assert.strictEqual(model.barHeadline(rows, "codex").id, "codex")
assert.strictEqual(model.barIconId(rows, false, "codex"), "codex")
assert.strictEqual(model.barIconId(rows, false, "kimi"), "kimi")
const codexIcon = model.iconWindows(codex)
assert.strictEqual(codexIcon.weeklyRemaining, 41)
assert.strictEqual(codexIcon.sessionRemaining, 72)
const cursorIcon = model.iconWindows(cursor)
assert.strictEqual(cursorIcon.weeklyRemaining, 9)
assert.strictEqual(cursorIcon.sessionRemaining, 9)
assert.strictEqual(model.prettyPlan("grok", "SuperGrok Heavy"), "SuperGrok Heavy")
assert.strictEqual(model.prettyPlan("grok", "Premium"), "X Premium")
assert.strictEqual(model.prettyPlan("grok", "Free"), "Free")
assert.ok(model.barTooltip(rows, false).includes("Cursor 91%"))
assert.strictEqual(model.formatCredits(112.4, "credits"), "112.4 credits")
assert.strictEqual(model.formatMoney(1.04), "$1.04")
assert.strictEqual(model.prettyPlan("codex", "prolite"), "Pro 5x")
assert.strictEqual(model.prettyPlan("codex", "pro"), "Pro 20x")
assert.strictEqual(model.prettyPlan("kimi", "Allegretto"), "Allegretto")
assert.strictEqual(model.prettyPlan("kimi", "Allegretto · kimi.com"), "Allegretto · kimi.com")
assert.strictEqual(model.prettyPlan("kimi", "LEVEL_INTERMEDIATE"), "LEVEL INTERMEDIATE")
assert.strictEqual(model.prettyPlan("notion", "business"), "Business")
assert.strictEqual(model.prettyPlan("cursor", "pro_plus"), "Pro+")
assert.strictEqual(model.prettyPlan("zed", "zed_student"), "Student")
assert.strictEqual(model.heroMeta(codex), "Plus · user@example.com")
assert.strictEqual(
  model.formatDuration(2 * 3600 * 1000 + 12 * 60 * 1000),
  "2h 12m",
)
assert.strictEqual(model.formatUpdatedAgo("", 1), "")
assert.strictEqual(model.formatUpdatedAgo("2026-08-23T11:00:00Z", Date.parse("2026-08-23T11:00:08Z")), "just now")
assert.strictEqual(model.formatUpdatedAgo("2026-08-23T11:00:00Z", Date.parse("2026-08-23T11:12:00Z")), "12m ago")
assert.strictEqual(model.formatUpdatedAgo("2026-08-23T11:00:00Z", Date.parse("2026-08-23T14:00:00Z")), "3h ago")
assert.ok(model.formatUpdatedAt("2026-08-23T11:00:00Z", Date.parse("2026-08-23T11:12:00Z")).includes("12m ago"))

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
