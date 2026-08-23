const assert = require("assert")
const { load } = require("./load")

const providers = load("Providers.js")

assert.deepStrictEqual(
  Array.from(providers.ids()),
  ["amp", "codex", "kimi", "cursor", "grok", "notion", "zed", "factory"],
)

assert.strictEqual(providers.displayName("kimi"), "Kimi Code")
assert.strictEqual(providers.displayName("notion"), "Notion AI")
assert.strictEqual(providers.displayName("amp"), "Amp")
assert.strictEqual(providers.displayName("factory"), "Droid")
assert.strictEqual(providers.isSupported("claude"), false)
assert.strictEqual(providers.isSupported("xai"), false)
assert.strictEqual(providers.providerEnabled({}, "codex"), true)
assert.strictEqual(
  providers.providerEnabled({ providers: { cursor: { enabled: false } } }, "cursor"),
  false,
)
assert.deepStrictEqual(
  Array.from(providers.enabledIds({ providers: { grok: { enabled: false }, zed: { enabled: false } } })),
  ["amp", "codex", "kimi", "cursor", "notion", "factory"],
)
assert.deepStrictEqual(
  Array.from(providers.orderedIds({ providerOrder: ["factory", "cursor", "unknown", "factory"] })),
  ["factory", "cursor", "amp", "codex", "kimi", "grok", "notion", "zed"],
)
assert.deepStrictEqual(
  Array.from(providers.enabledIds({
    providerOrder: ["factory", "cursor", "amp"],
    providers: { cursor: { enabled: false } },
  })),
  ["factory", "amp", "codex", "kimi", "grok", "notion", "zed"],
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
assert.strictEqual(catalog.length, 8)

console.log("provider catalog tests passed")
