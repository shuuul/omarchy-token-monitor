.pragma library

// The providers this plugin is allowed to show. IDs must match CodexBar
// exactly: amp, codex, kimi, cursor, grok, notion, zed, factory. Adding any
// other ID here is a product change, not a display tweak. factory displays
// as Droid.

var SUPPORTED = [
  { id: "amp", name: "Amp", monogram: "A" },
  { id: "codex", name: "Codex", monogram: "C" },
  { id: "kimi", name: "Kimi Code", monogram: "K" },
  { id: "cursor", name: "Cursor", monogram: "Cu" },
  { id: "grok", name: "Grok", monogram: "G" },
  { id: "notion", name: "Notion AI", monogram: "N" },
  { id: "zed", name: "Zed", monogram: "Z" },
  { id: "factory", name: "Droid", monogram: "D" }
]

var DEFAULT_PROVIDERS = {
  amp: { enabled: true },
  codex: { enabled: true },
  kimi: { enabled: true },
  cursor: { enabled: true },
  grok: { enabled: true },
  notion: { enabled: true },
  zed: { enabled: true },
  factory: { enabled: true }
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

function orderedIds(settings) {
  var known = ids()
  var wanted = settings && settings.providerOrder
  var out = []
  var seen = {}
  if (wanted && typeof wanted === "object" && wanted.length !== undefined) {
    for (var i = 0; i < wanted.length; i++) {
      var id = String(wanted[i] || "")
      if (!isSupported(id) || seen[id]) continue
      seen[id] = true
      out.push(id)
    }
  }
  for (var j = 0; j < known.length; j++) {
    if (!seen[known[j]]) out.push(known[j])
  }
  return out
}

function moveId(order, fromIndex, toIndex) {
  var next = []
  var source = order && typeof order === "object" && order.length !== undefined ? order : []
  for (var i = 0; i < source.length; i++) next.push(source[i])
  if (fromIndex < 0 || fromIndex >= next.length) return next
  var target = toIndex
  if (target < 0) target = 0
  if (target >= next.length) target = next.length - 1
  if (fromIndex === target) return next
  var item = next.splice(fromIndex, 1)[0]
  next.splice(target, 0, item)
  return next
}

function enabledIds(settings) {
  var order = orderedIds(settings)
  var out = []
  for (var i = 0; i < order.length; i++) {
    if (providerEnabled(settings, order[i])) out.push(order[i])
  }
  return out
}

function settingsCatalog(settings) {
  var order = orderedIds(settings)
  var out = []
  for (var i = 0; i < order.length; i++) {
    var item = descriptor(order[i])
    if (!item) continue
    out.push({
      id: item.id,
      name: item.name,
      monogram: item.monogram,
      enabled: providerEnabled(settings, item.id)
    })
  }
  return out
}
