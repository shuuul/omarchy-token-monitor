const assert = require("assert")
const { load } = require("./load")

const providers = load("Providers.js")

assert.deepStrictEqual(
  Array.from(providers.ids()),
  ["amp", "codex", "kimi", "cursor", "grok", "notion", "zed"],
)

assert.strictEqual(providers.displayName("kimi"), "Kimi Code")
assert.strictEqual(providers.displayName("notion"), "Notion AI")
assert.strictEqual(providers.displayName("amp"), "Amp")
assert.strictEqual(providers.isSupported("claude"), false)
assert.strictEqual(providers.isSupported("xai"), false)
assert.strictEqual(providers.providerEnabled({}, "codex"), true)
assert.strictEqual(
  providers.providerEnabled({ providers: { cursor: { enabled: false } } }, "cursor"),
  false,
)
assert.deepStrictEqual(
  Array.from(providers.enabledIds({ providers: { grok: { enabled: false }, zed: { enabled: false } } })),
  ["amp", "codex", "kimi", "cursor", "notion"],
)

console.log("provider catalog tests passed")
