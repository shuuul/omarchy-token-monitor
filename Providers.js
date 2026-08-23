.pragma library

// The seven providers this plugin is allowed to show. IDs must match CodexBar
// exactly: amp, codex, kimi, cursor, grok, notion, zed. Adding any other ID
// here is a product change, not a display tweak.

var SUPPORTED = [
  { id: "amp", name: "Amp", monogram: "A" },
  { id: "codex", name: "Codex", monogram: "C" },
  { id: "kimi", name: "Kimi Code", monogram: "K" },
  { id: "cursor", name: "Cursor", monogram: "Cu" },
  { id: "grok", name: "Grok", monogram: "G" },
  { id: "notion", name: "Notion AI", monogram: "N" },
  { id: "zed", name: "Zed", monogram: "Z" }
]

var DEFAULT_PROVIDERS = {
  amp: { enabled: true },
  codex: { enabled: true },
  kimi: { enabled: true },
  cursor: { enabled: true },
  grok: { enabled: true },
  notion: { enabled: true },
  zed: { enabled: true }
}

function catalog() {
  return SUPPORTED.slice()
}

function ids() {
  var out = []
  for (var i = 0; i < SUPPORTED.length; i++) out.push(SUPPORTED[i].id)
  return out
}

function isSupported(id) {
  return indexOfId(id) >= 0
}

function indexOfId(id) {
  var wanted = String(id || "")
  for (var i = 0; i < SUPPORTED.length; i++) {
    if (SUPPORTED[i].id === wanted) return i
  }
  return -1
}

function descriptor(id) {
  var index = indexOfId(id)
  return index >= 0 ? SUPPORTED[index] : null
}

function displayName(id) {
  var item = descriptor(id)
  return item ? item.name : String(id || "")
}

function monogram(id) {
  var item = descriptor(id)
  return item ? item.monogram : String(id || "?").slice(0, 2)
}

function providerEnabled(settings, id) {
  if (!isSupported(id)) return false
  var providers = settings && settings.providers ? settings.providers : {}
  var entry = providers[id]
  if (entry && entry.enabled === false) return false
  return true
}

function enabledIds(settings) {
  var out = []
  for (var i = 0; i < SUPPORTED.length; i++) {
    var id = SUPPORTED[i].id
    if (providerEnabled(settings, id)) out.push(id)
  }
  return out
}
