const assert = require("assert")
const { load } = require("./load")

const model = load("Model.js")
const providers = load("Providers.js")

assert.deepStrictEqual(Array.from(model.collectCommand({})), [
  "/usr/bin/timeout",
  "45",
  "/usr/bin/python3",
  "collect.py",
])
assert.deepStrictEqual(
  Array.from(model.collectCommand({ collectPath: "/tmp/collect.py" })),
  ["/usr/bin/timeout", "45", "/usr/bin/python3", "/tmp/collect.py"],
)
assert.deepStrictEqual(
  Array.from(model.collectCommand({ collectPath: "/tmp/collect.py", only: "grok" })),
  ["/usr/bin/timeout", "45", "/usr/bin/python3", "/tmp/collect.py", "grok"],
)
assert.strictEqual(model.appendBounded("a", "b"), "ab")
assert.strictEqual(
  model.errorText("amp usage failed: Error: Unexpected error inside Amp CLI.\n\u001b[=0u\u001b[<u\u001b[?25h"),
  "amp usage failed: Error: Unexpected error inside Amp CLI.",
)
assert.strictEqual(
  model.parseError("Error: Unexpected error inside Amp CLI.\n\u001b[=0u\u001b[<u\u001b[?25h", 1),
  "Error: Unexpected error inside Amp CLI.",
)
assert.strictEqual(model.appendBounded("x".repeat(65536), "overflow").length, 65536)
assert.deepStrictEqual(
  model.mergeProviderRows(
    [{ provider: "codex", usage: { loginMethod: "old" } }, { provider: "grok", usage: { loginMethod: "keep" } }],
    [{ provider: "codex", usage: { loginMethod: "new" } }],
  ),
  [{ provider: "codex", usage: { loginMethod: "new" } }, { provider: "grok", usage: { loginMethod: "keep" } }],
)
assert.strictEqual(model.refreshIntervalSec({}), 300)
assert.strictEqual(model.refreshIntervalSec({ refreshIntervalSec: 12 }), 30)
assert.strictEqual(model.refreshIntervalSec({ refreshIntervalSec: 9000 }), 3600)
assert.strictEqual(model.browserName({}), "chrome")
assert.strictEqual(model.browserName({ browser: "chromium" }), "chromium")
assert.strictEqual(model.refreshOnOpen({}), false)
assert.strictEqual(model.refreshOnOpen({ refreshOnOpen: false }), false)
assert.strictEqual(model.refreshOnOpen({ refreshOnOpen: true }), true)
assert.strictEqual(model.snapshotStale([], 300, 1000000), true)
assert.strictEqual(model.snapshotStale([{ updatedAt: "not a date" }], 300, 1000000), true)
assert.strictEqual(model.snapshotStale([{ updatedAt: new Date(1000000).toISOString() }], 300, 1000000), false)
assert.strictEqual(model.snapshotStale([{ updatedAt: new Date(1000000 - 301000).toISOString() }], 300, 1000000), true)
assert.strictEqual(
  model.snapshotStale(
    [{ updatedAt: new Date(1000000 - 301000).toISOString() }, { updatedAt: new Date(1000000).toISOString() }],
    300,
    1000000,
  ),
  false,
)
assert.strictEqual(model.showRemaining({}), true)
assert.strictEqual(model.showRemaining({ showRemaining: false }), false)
assert.strictEqual(model.showRemaining({ showRemaining: true }), true)
assert.strictEqual(model.displayPercent({ usedPercent: 28 }, true), 72)
assert.strictEqual(model.displayPercent({ usedPercent: 28 }, false), 28)
assert.strictEqual(model.displayPercent({ remainingPercent: 41 }, true), 41)
assert.strictEqual(model.displayPercent({ remainingPercent: 41 }, false), 59)
assert.strictEqual(model.mergeSettings({ browser: "chrome" }, { refreshIntervalSec: 300 }).refreshIntervalSec, 300)
assert.strictEqual(model.withProviderEnabled({ providers: { grok: { enabled: true } } }, "grok", false).providers.grok.enabled, false)
assert.deepStrictEqual(
  Array.from(model.withProviderOrder({ browser: "chrome" }, ["factory", "cursor"]).providerOrder),
  ["factory", "cursor"],
)

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
assert.strictEqual(model.parseError("", 2), "python3 could not run collect.py")

const parsed = model.parseSnapshot(JSON.stringify(snapshot))
const rows = model.providersFromSnapshot(
  parsed,
  Array.from(providers.enabledIds({})),
  providers.catalog(),
)
assert.strictEqual(rows.length, 8)
const orderedRows = model.providersFromSnapshot(
  parsed,
  Array.from(providers.enabledIds({ providerOrder: ["factory", "cursor", "codex"] })),
  providers.catalog(),
)
assert.deepStrictEqual(
  Array.from(orderedRows.map((row) => row.id)).slice(0, 3),
  ["factory", "cursor", "codex"],
)
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
assert.strictEqual(cursor.alarming, false)
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
assert.strictEqual(codexIcon.weeklyUsed, 59)
assert.strictEqual(codexIcon.sessionUsed, 28)
const cursorIcon = model.iconWindows(cursor)
assert.strictEqual(cursorIcon.weeklyRemaining, null)
assert.strictEqual(cursorIcon.sessionRemaining, 9)
const cursorNamed = {
  windows: [
    { title: "Plan", usedPercent: 8.6 },
    { title: "Cursor Models", usedPercent: 9.73 },
    { title: "Third-Party", usedPercent: 0.39 },
    { title: "Grok Bot", usedPercent: 13.09 }
  ]
}
const cursorNamedIcon = model.iconWindows(cursorNamed)
assert.strictEqual(Math.round(cursorNamedIcon.weeklyRemaining), 90)
assert.strictEqual(Math.round(cursorNamedIcon.sessionRemaining), 100)
assert.strictEqual(model.windowTitle("Cursor models", "", null), "Cursor Models")
assert.strictEqual(model.windowTitle("Third-party", "", null), "Third-Party")
assert.strictEqual(model.windowTitle("Grok Bot", "cursor-grok-bot", 10080), "Grok Bot")
const cursorWithGrok = model.displayProvider({
  provider: "cursor",
  usage: {
    extraRateWindows: [{
      id: "cursor-grok-bot",
      title: "Grok Bot",
      window: { usedPercent: 13.09, windowMinutes: 10080, resetsAt: "2026-08-31T02:28:01.719Z" }
    }]
  }
}, providers.descriptor("cursor"))
assert.strictEqual(cursorWithGrok.windows.length, 1)
assert.strictEqual(cursorWithGrok.windows[0].title, "Grok Bot")
assert.strictEqual(cursorWithGrok.windows[0].usedPercent, 13.09)
const grokRow = {
  windows: [{ title: "Weekly", usedPercent: 92 }]
}
const grokIcon = model.iconWindows(grokRow)
assert.strictEqual(grokIcon.weeklyRemaining, 8)
assert.strictEqual(grokIcon.sessionRemaining, null)
assert.strictEqual(model.windowTitle("Credits", "", null), "Weekly")
assert.strictEqual(model.windowTitle("5h", "", 300), "5h")
assert.strictEqual(model.windowTitle("5-hour", "", 300), "5h")
assert.strictEqual(model.windowTitle("7-day", "", 10080), "Weekly")
assert.strictEqual(model.windowTitle("Core 5h", "", 300), "Core 5h")
assert.strictEqual(model.windowTitle("Core 7-day", "", 10080), "Core 7-day")
assert.strictEqual(model.windowTitle("Core Monthly", "", null), "Core Monthly")
assert.strictEqual(model.windowTitle("6-hour", "", 360), "Rolling")
assert.strictEqual(model.windowTitle("Rolling", "", 360), "Rolling")
const notionWindows = {
  windows: [
    { title: "Rolling", usedPercent: 0 },
    { title: "Monthly", usedPercent: 0.68 }
  ]
}
const notionIcon = model.iconWindows(notionWindows)
assert.strictEqual(Math.round(notionIcon.weeklyRemaining), 99)
assert.strictEqual(notionIcon.sessionRemaining, 100)
assert.strictEqual(model.windowTitle("GPT-5.3-Codex-Spark session", "", 300), "Codex Spark Session")
assert.strictEqual(model.windowTitle("GPT-5.3-Codex-Spark weekly", "", 10080), "Codex Spark Weekly")
const sparkWindows = {
  windows: [
    { title: "Weekly", usedPercent: 10 },
    { title: "Codex Spark Session", usedPercent: 0 },
    { title: "Codex Spark Weekly", usedPercent: 13 }
  ]
}
const sparkIcon = model.iconWindows(sparkWindows)
assert.strictEqual(sparkIcon.weeklyRemaining, 90)
assert.strictEqual(sparkIcon.sessionRemaining, null)
const factoryLimits = {
  windows: [
    { title: "5h", usedPercent: 2 },
    { title: "Weekly", usedPercent: 8 },
    { title: "Monthly", usedPercent: 27 },
    { title: "Core 5h", usedPercent: 0 },
    { title: "Core 7-day", usedPercent: 0 },
    { title: "Core Monthly", usedPercent: 0 }
  ]
}
const factoryIcon = model.iconWindows(factoryLimits)
assert.strictEqual(factoryIcon.weeklyRemaining, 92)
assert.strictEqual(factoryIcon.sessionRemaining, 98)
const factorySnapshot = {
  providers: [{
    provider: "factory",
    usage: {
      primary: { usedPercent: 2, windowMinutes: 300, label: "5h" },
      secondary: { usedPercent: 8, windowMinutes: 10080, label: "Weekly" },
      tertiary: { usedPercent: 27, label: "Monthly" },
      extraRateWindows: [
        { title: "Core 5h", window: { usedPercent: 0, windowMinutes: 300, label: "Core 5h" } },
        { title: "Core 7-day", window: { usedPercent: 0, windowMinutes: 10080, label: "Core 7-day" } },
        { title: "Core Monthly", window: { usedPercent: 0, label: "Core Monthly" } }
      ]
    },
    credits: { remaining: 0, unit: "usd", label: "Extra usage" }
  }]
}
const factoryRows = model.providersFromSnapshot(factorySnapshot, ["factory"], providers.catalog())
assert.strictEqual(
  Array.from(factoryRows[0].windows).map((row) => row.title).join("|"),
  "5h|Weekly|Monthly|Core 5h|Core 7-day|Core Monthly",
)
assert.strictEqual(factoryRows[0].creditsLabel, "Extra usage")
assert.strictEqual(factoryRows[0].creditsRemaining, 0)
const factoryLegacy = {
  windows: [
    { title: "Standard", usedPercent: 40 },
    { title: "Premium", usedPercent: 10 }
  ]
}
const factoryLegacyIcon = model.iconWindows(factoryLegacy)
assert.strictEqual(factoryLegacyIcon.weeklyRemaining, 90)
assert.strictEqual(factoryLegacyIcon.sessionRemaining, 60)
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
assert.strictEqual(model.prettyPlan("factory", "team_annual"), "Team Annual")
assert.strictEqual(model.heroMeta(codex), "Plus · user@example.com")
assert.strictEqual(model.heroMeta(codex, { hideEmail: true }), "Plus")
assert.strictEqual(model.hideEmail({}), false)
assert.strictEqual(model.hideEmail({ hideEmail: true }), true)
assert.strictEqual(model.rememberedProviderId({}), "")
assert.strictEqual(model.rememberedProviderId({ selectedProviderId: "codex" }), "codex")
assert.strictEqual(
  model.resolveSelectedProviderId({ selectedProviderId: "codex" }, [{ id: "grok" }, { id: "codex" }], "grok"),
  "codex",
)
assert.strictEqual(
  model.resolveSelectedProviderId({ selectedProviderId: "missing" }, [{ id: "cursor" }, { id: "grok" }], "cursor"),
  "cursor",
)
assert.strictEqual(
  model.resolveSelectedProviderId({}, [{ id: "amp" }, { id: "grok" }], ""),
  "amp",
)
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
