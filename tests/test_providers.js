const assert = require("assert")
const { load } = require("./load")

const providers = load("Providers.js")

assert.deepStrictEqual(
  Array.from(providers.ids()),
  ["amp", "antigravity", "codex", "kimi", "cursor", "grok", "notion", "zed", "factory", "deepseek", "devin"],
)

assert.strictEqual(providers.displayName("kimi"), "Kimi Code")
assert.strictEqual(providers.displayName("notion"), "Notion AI")
assert.strictEqual(providers.displayName("amp"), "Amp")
assert.strictEqual(providers.displayName("antigravity"), "Antigravity")
assert.strictEqual(providers.displayName("factory"), "Droid")
assert.strictEqual(providers.displayName("deepseek"), "DeepSeek")
assert.strictEqual(providers.displayName("devin"), "Devin")
assert.strictEqual(providers.monogram("antigravity"), "Ag")
assert.strictEqual(providers.dashboardUrl("amp"), "https://ampcode.com/settings/usage")
assert.strictEqual(providers.dashboardUrl("antigravity"), "")
assert.strictEqual(providers.dashboardUrl("codex"), "https://chatgpt.com/codex/settings/usage")
assert.strictEqual(providers.dashboardUrl("kimi"), "https://www.kimi.com/code/console")
assert.strictEqual(providers.dashboardUrl("kimi", { plan: "Allegretto · kimi.ai" }), "https://www.kimi.ai/code/console")
assert.strictEqual(providers.dashboardUrl("cursor"), "https://cursor.com/dashboard?tab=usage")
assert.strictEqual(providers.dashboardUrl("grok"), "https://grok.com/?_s=usage")
assert.strictEqual(providers.dashboardUrl("notion"), "https://app.notion.com/")
assert.strictEqual(providers.dashboardUrl("zed"), "")
assert.strictEqual(providers.dashboardUrl("factory"), "https://app.factory.ai/settings/billing")
assert.strictEqual(providers.dashboardUrl("deepseek"), "https://platform.deepseek.com/usage")
assert.strictEqual(providers.dashboardUrl("devin"), "https://app.devin.ai/settings/usage")
assert.strictEqual(providers.isSupported("claude"), false)
assert.strictEqual(providers.isSupported("xai"), false)
assert.strictEqual(providers.providerEnabled({}, "codex"), true)
assert.strictEqual(
  providers.providerEnabled({ providers: { cursor: { enabled: false } } }, "cursor"),
  false,
)
assert.deepStrictEqual(
  Array.from(providers.enabledIds({ providers: { grok: { enabled: false }, zed: { enabled: false } } })),
  ["amp", "antigravity", "codex", "kimi", "cursor", "notion", "factory", "deepseek", "devin"],
)
assert.deepStrictEqual(
  Array.from(providers.orderedIds({ providerOrder: ["factory", "cursor", "unknown", "factory"] })),
  ["factory", "cursor", "amp", "antigravity", "codex", "kimi", "grok", "notion", "zed", "deepseek", "devin"],
)
assert.deepStrictEqual(
  Array.from(providers.enabledIds({
    providerOrder: ["factory", "cursor", "amp"],
    providers: { cursor: { enabled: false } },
  })),
  ["factory", "amp", "antigravity", "codex", "kimi", "grok", "notion", "zed", "deepseek", "devin"],
)
assert.deepStrictEqual(
  Array.from(providers.moveId(["amp", "codex", "kimi"], 2, 0)),
  ["kimi", "amp", "codex"],
)
const catalog = providers.settingsCatalog({
  providerOrder: ["zed", "amp"],
  providers: { amp: { enabled: false } },
})
assert.strictEqual(catalog[0].id, "zed")
assert.strictEqual(catalog[0].enabled, true)
assert.strictEqual(catalog[1].id, "amp")
assert.strictEqual(catalog[1].enabled, false)
assert.strictEqual(catalog.length, 11)

console.log("provider catalog tests passed")
