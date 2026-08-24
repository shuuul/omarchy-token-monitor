.pragma library

// Usage JSON parsing and formatting. QML owns theme and process I/O;
// this file is what the node tests exercise.

var DEFAULT_REFRESH_SEC = 300
var MIN_REFRESH_SEC = 30
var MAX_REFRESH_SEC = 3600
var MAX_PROCESS_STREAM_CHARS = 65536

function emptySnapshot() {
  return { providers: [] }
}

function emptyDisplay() {
  return {
    id: "",
    name: "",
    monogram: "",
    enabled: false,
    source: "",
    statusLevel: "",
    statusLabel: "",
    accountEmail: "",
    plan: "",
    windows: [],
    binding: null,
    creditsRemaining: null,
    creditsUnit: "",
    creditsLabel: "",
    costToday: null,
    costLast30Days: null,
    paceSummary: "",
    error: "",
    updatedAt: "",
    alarming: false
  }
}

function refreshIntervalSec(settings) {
  var raw = settings ? settings.refreshIntervalSec : undefined
  var value = parseInt(String(raw === undefined || raw === null ? DEFAULT_REFRESH_SEC : raw), 10)
  if (!isFinite(value)) value = DEFAULT_REFRESH_SEC
  return Math.max(MIN_REFRESH_SEC, Math.min(MAX_REFRESH_SEC, value))
}

function browserName(settings) {
  var value = String(settings && settings.browser ? settings.browser : "chrome").trim().toLowerCase()
  return value === "chromium" ? "chromium" : "chrome"
}

function refreshOnOpen(settings) {
  return !!(settings && settings.refreshOnOpen)
}

function showRemaining(settings) {
  if (!settings || settings.showRemaining === undefined || settings.showRemaining === null)
    return true
  return !!settings.showRemaining
}

function hideEmail(settings) {
  return !!(settings && settings.hideEmail)
}

function rememberedProviderId(settings) {
  return String(settings && settings.selectedProviderId ? settings.selectedProviderId : "")
}

function resolveSelectedProviderId(settings, providers, currentId) {
  var rows = Array.isArray(providers) ? providers : []
  function present(id) {
    var wanted = String(id || "")
    if (wanted === "") return ""
    for (var i = 0; i < rows.length; i++) {
      if (rows[i] && rows[i].id === wanted) return wanted
    }
    return ""
  }
  return present(rememberedProviderId(settings))
    || present(currentId)
    || (rows.length && rows[0] && rows[0].id ? rows[0].id : "")
}

function mergeSettings(current, values) {
  var entry = {}
  if (current && typeof current === "object") {
    for (var key in current) {
      if (key !== "id") entry[key] = current[key]
    }
  }
  if (values && typeof values === "object") {
    for (var next in values) entry[next] = values[next]
  }
  return entry
}

function withProviderEnabled(current, providerId, enabled) {
  var providers = {}
  var existing = current && current.providers && typeof current.providers === "object" ? current.providers : {}
  for (var key in existing) providers[key] = existing[key]
  var prior = providers[providerId] && typeof providers[providerId] === "object" ? providers[providerId] : {}
  var next = {}
  for (var field in prior) next[field] = prior[field]
  next.enabled = !!enabled
  providers[providerId] = next
  return mergeSettings(current, { providers: providers })
}

function withProviderOrder(current, order) {
  var ids = []
  var source = order && typeof order === "object" && order.length !== undefined ? order : []
  for (var i = 0; i < source.length; i++) ids.push(String(source[i] || ""))
  return mergeSettings(current, { providerOrder: ids })
}

function collectScript() {
  if (typeof Qt !== "undefined" && Qt.resolvedUrl)
    return Qt.resolvedUrl("collect.py").toString().replace(/^file:\/\//, "")
  return "collect.py"
}

function collectCommand(settings) {
  var script = settings && settings.collectPath ? String(settings.collectPath) : ""
  if (!script) script = collectScript()
  var command = ["/usr/bin/timeout", "45", "/usr/bin/python3", script]
  var only = settings && settings.only ? String(settings.only).trim() : ""
  if (only) command.push(only)
  return command
}

function appendBounded(current, chunk) {
  var before = String(current || "")
  if (before.length >= MAX_PROCESS_STREAM_CHARS) return before
  return (before + String(chunk || "")).slice(0, MAX_PROCESS_STREAM_CHARS)
}

function mergeProviderRows(existing, incoming) {
  var current = Array.isArray(existing) ? existing.slice() : []
  var updates = Array.isArray(incoming) ? incoming : []
  if (updates.length === 0) return current
  var byId = {}
  for (var i = 0; i < current.length; i++) {
    var row = current[i] || {}
    var id = String(row.provider || row.id || "")
    if (id) byId[id] = i
  }
  for (var j = 0; j < updates.length; j++) {
    var next = updates[j] || {}
    var nextId = String(next.provider || next.id || "")
    if (!nextId) {
      current.push(next)
      continue
    }
    if (byId.hasOwnProperty(nextId)) current[byId[nextId]] = next
    else current.push(next)
  }
  return current
}

function usageCommand(settings) {
  return collectCommand(settings)
}

function lastJsonValue(text) {
  var source = String(text || "").trim()
  if (source === "") return null
  try {
    return JSON.parse(source)
  } catch (ignored) {
  }
  var arrayStart = source.indexOf("[")
  var objectStart = source.indexOf("{")
  var start = -1
  if (arrayStart >= 0 && (objectStart < 0 || arrayStart < objectStart)) start = arrayStart
  else start = objectStart
  if (start < 0) return null
  try {
    return JSON.parse(source.slice(start))
  } catch (error) {
    return null
  }
}

function parseSnapshot(text) {
  var data = lastJsonValue(text)
  if (Array.isArray(data)) return { providers: data }
  if (data && typeof data === "object") {
    if (Array.isArray(data.providers)) return data
    if (data.provider || data.usage || data.error) return { providers: [data] }
  }
  return null
}

function stripControlChars(text) {
  return String(text || "")
    .replace(/\u001b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, "")
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "")
}

function parseError(text, exitCode) {
  var data = lastJsonValue(text)
  if (data && !Array.isArray(data) && data.error) return errorText(data.error)
  var trimmed = stripControlChars(text).trim()
  if (trimmed !== "") {
    var lines = trimmed.split("\n").map(function(line) { return line.trim() }).filter(Boolean)
    for (var i = lines.length - 1; i >= 0; i--) {
      if (/[A-Za-z]/.test(lines[i])) return lines[i]
    }
    return lines[lines.length - 1] || ""
  }
  if (exitCode === 2) return "python3 could not run collect.py"
  if (exitCode === 139) return "collect.py crashed"
  if (exitCode) return "collect.py exited " + exitCode
  return "collect.py returned no snapshot"
}

function asNumber(value) {
  if (value === undefined || value === null || value === "") return null
  var number = Number(value)
  return isFinite(number) ? number : null
}

function errorText(value) {
  if (value === undefined || value === null || value === false) return ""
  var text = ""
  if (typeof value === "string") text = value
  else if (typeof value === "object") {
    if (value.message) text = String(value.message)
    else if (value.error) return errorText(value.error)
    else text = String(value)
  } else text = String(value)
  return stripControlChars(text).trim()
}

function titleCaseLabel(label) {
  var plain = String(label || "").replace(/\s*\(.*\)\s*/, "").trim()
  if (plain === "") return "Limit"
  return plain.replace(/\b([a-z])/g, function(match) {
    return match.toUpperCase()
  })
}

function windowTitle(label, kind, minutes) {
  var text = String(label || "").toLowerCase()
  var kindText = String(kind || "").toLowerCase()
  if (kindText === "cursor-grok-bot" || text === "grok bot") return "Grok Bot"
  if (text.indexOf("core") >= 0) {
    if (text.indexOf("5h") >= 0 || text.indexOf("5-hour") >= 0 || text.indexOf("five-hour") >= 0 || minutes === 300)
      return "Core 5h"
    if (text.indexOf("week") >= 0 || text.indexOf("7-day") >= 0 || minutes === 10080)
      return "Core 7-day"
    if (text.indexOf("month") >= 0 || text.indexOf("30-day") >= 0)
      return "Core Monthly"
    return titleCaseLabel(label)
  }
  if (kindText === "weekly" || text.indexOf("week") >= 0 || text.indexOf("7-day") >= 0) {
    if (text.indexOf("spark") >= 0) return "Codex Spark Weekly"
    return "Weekly"
  }
  if (kindText === "session" || text.indexOf("session") >= 0) {
    if (text.indexOf("spark") >= 0) return "Codex Spark Session"
    return "Session"
  }
  if (text.indexOf("month") >= 0 || text.indexOf("30-day") >= 0) return "Monthly"
  if (text.indexOf("5h") >= 0 || text.indexOf("5-hour") >= 0 || text.indexOf("five-hour") >= 0 || text.indexOf("five hour") >= 0)
    return "5h"
  if (text.indexOf("roll") >= 0 || text.indexOf("6-hour") >= 0 || text.indexOf("6h") >= 0) return "Rolling"
  if (text.indexOf("day") >= 0 || text.indexOf("daily") >= 0) return "Daily"
  if (text.indexOf("credit") >= 0) return "Weekly"
  if (minutes === 10080) return "Weekly"
  if (minutes === 300) return "5h"
  return titleCaseLabel(label)
}

function normalizeRateWindow(raw, label, kind) {
  if (!raw || typeof raw !== "object") return null
  if (raw.idle === true) return null
  var used = asNumber(raw.usedPercent)
  if (used === null && asNumber(raw.remainingPercent) !== null)
    used = Math.max(0, Math.min(100, 100 - asNumber(raw.remainingPercent)))
  if (used === null) return null
  var minutes = asNumber(raw.windowMinutes)
  var title = windowTitle(label || raw.label || raw.title, kind || raw.kind, minutes)
  return {
    kind: String(kind || raw.kind || ""),
    label: String(label || raw.label || raw.title || title),
    title: title,
    usedPercent: used,
    remainingPercent: asNumber(raw.remainingPercent),
    resetAt: String(raw.resetAt || raw.resetsAt || "")
  }
}

function collectWindows(usage) {
  var out = []
  if (!usage || typeof usage !== "object") return out
  var primaryLabel = usage.primary && usage.primary.label ? usage.primary.label : "Session"
  var secondaryLabel = usage.secondary && usage.secondary.label ? usage.secondary.label : "Weekly"
  var primary = normalizeRateWindow(usage.primary, primaryLabel, "")
  var secondary = normalizeRateWindow(usage.secondary, secondaryLabel, "")
  var tertiary = normalizeRateWindow(usage.tertiary, usage.tertiary && usage.tertiary.label, "tertiary")
  if (primary) out.push(primary)
  if (secondary) out.push(secondary)
  if (tertiary) out.push(tertiary)
  var extras = Array.isArray(usage.extraRateWindows) ? usage.extraRateWindows : []
  for (var i = 0; i < extras.length; i++) {
    var extra = extras[i] || {}
    var window = normalizeRateWindow(extra.window || extra, extra.title || extra.label, extra.id || extra.kind)
    if (window) out.push(window)
  }
  var listed = Array.isArray(usage.windows) ? usage.windows : []
  for (var j = 0; j < listed.length; j++) {
    var listedWindow = normalizeRateWindow(listed[j], listed[j] && listed[j].label, listed[j] && listed[j].kind)
    if (listedWindow) out.push(listedWindow)
  }
  return out
}

function bindingWindow(windows) {
  var best = null
  for (var i = 0; i < windows.length; i++) {
    if (!best || windows[i].usedPercent > best.usedPercent) best = windows[i]
  }
  return best
}

function remainingPercent(window) {
  if (!window) return null
  if (asNumber(window.remainingPercent) !== null)
    return Math.max(0, Math.min(100, asNumber(window.remainingPercent)))
  if (asNumber(window.usedPercent) === null) return null
  return Math.max(0, Math.min(100, 100 - asNumber(window.usedPercent)))
}

function usedPercent(window) {
  if (!window) return null
  if (asNumber(window.usedPercent) !== null)
    return Math.max(0, Math.min(100, asNumber(window.usedPercent)))
  if (asNumber(window.remainingPercent) === null) return null
  return Math.max(0, Math.min(100, 100 - asNumber(window.remainingPercent)))
}

function displayPercent(window, remaining) {
  return remaining ? remainingPercent(window) : usedPercent(window)
}

function findWindowByTitle(windows, title) {
  var wanted = String(title || "").toLowerCase()
  var rows = Array.isArray(windows) ? windows : []
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i] || {}
    var titleText = String(row.title || "").toLowerCase()
    var labelText = String(row.label || "").toLowerCase()
    if (titleText === wanted || labelText === wanted) return row
  }
  return null
}

function iconWindows(provider) {
  var windows = provider && Array.isArray(provider.windows) ? provider.windows : []
  var named = []
  for (var i = 0; i < windows.length; i++) {
    var title = String(windows[i].title || windows[i].label || "")
    if (title && title !== "Plan") named.push(windows[i])
  }
  var weekly = findWindowByTitle(windows, "Weekly")
    || findWindowByTitle(windows, "Cursor Models")
    || findWindowByTitle(windows, "Premium")
    || findWindowByTitle(windows, "Monthly")
  var session = findWindowByTitle(windows, "Session")
    || findWindowByTitle(windows, "5h")
    || findWindowByTitle(windows, "5-hour")
    || findWindowByTitle(windows, "Third-Party")
    || findWindowByTitle(windows, "Third-party")
    || findWindowByTitle(windows, "Third party")
    || findWindowByTitle(windows, "Rolling")
    || findWindowByTitle(windows, "Standard")
  if (weekly && session && weekly === session) session = null
  if (!weekly && !session && named.length === 1) weekly = named[0]
  if (!weekly && named.length > 0 && named[0] !== session && String(named[0].title || "") !== "Session")
    weekly = named[0]
  if (!session && named.length > 1 && named[1] !== weekly && String(named[1].title || "").indexOf("Spark") < 0)
    session = named[1]
  if (weekly && session && weekly === session) session = null
  return {
    weeklyRemaining: remainingPercent(weekly),
    sessionRemaining: remainingPercent(session),
    weeklyUsed: usedPercent(weekly),
    sessionUsed: usedPercent(session)
  }
}

function firstPaceSummary(pace) {
  if (!pace || typeof pace !== "object") return ""
  var keys = ["primary", "secondary", "tertiary"]
  for (var i = 0; i < keys.length; i++) {
    var entry = pace[keys[i]]
    if (entry && entry.summary) return String(entry.summary)
  }
  return ""
}

function displayProvider(row, descriptor) {
  var display = emptyDisplay()
  var id = String((row && (row.id || row.provider)) || (descriptor && descriptor.id) || "")
  display.id = id
  display.name = (descriptor && descriptor.name) || String((row && row.name) || id)
  display.monogram = (descriptor && descriptor.monogram) || id.slice(0, 2)
  if (!row) return display

  display.enabled = row.enabled !== false
  display.source = String(row.source || "")
  var status = row.status || {}
  display.statusLevel = String(status.level || status.indicator || "")
  display.statusLabel = String(status.label || status.description || "")
  var usage = row.usage || {}
  var identity = usage.identity || row.identity || {}
  display.accountEmail = String(identity.accountEmail || usage.accountEmail || "")
  display.plan = String(identity.plan || identity.loginMethod || usage.loginMethod || "")
  display.windows = collectWindows(usage)
  if (display.windows.length === 0) display.windows = collectWindows(row)
  display.binding = bindingWindow(display.windows)
  var credits = row.credits || {}
  display.creditsRemaining = asNumber(credits.remaining)
  display.creditsUnit = String(credits.unit || "credits")
  display.creditsLabel = String(credits.label || "")
  var cost = row.cost || {}
  display.costToday = asNumber(cost.todayUSD)
  display.costLast30Days = asNumber(cost.last30DaysUSD)
  display.paceSummary = firstPaceSummary(row.pace)
  display.error = errorText(row.error)
  display.updatedAt = String(usage.updatedAt || row.updatedAt || "")
  display.alarming = false
  return display
}

function providersFromSnapshot(snapshot, enabledIds, catalog) {
  var rows = {}
  var list = snapshot && Array.isArray(snapshot.providers) ? snapshot.providers : []
  for (var i = 0; i < list.length; i++) {
    var row = list[i] || {}
    var id = String(row.id || row.provider || "")
    if (id !== "") rows[id] = row
  }

  var out = []
  var wanted = Array.isArray(enabledIds) ? enabledIds : []
  for (var j = 0; j < wanted.length; j++) {
    var providerId = wanted[j]
    var descriptor = null
    if (catalog) {
      for (var k = 0; k < catalog.length; k++) {
        if (catalog[k].id === providerId) {
          descriptor = catalog[k]
          break
        }
      }
    }
    var display = displayProvider(rows[providerId] || null, descriptor || { id: providerId })
    display.id = providerId
    if (descriptor) {
      display.name = descriptor.name
      display.monogram = descriptor.monogram
    }
    out.push(display)
  }
  return out
}

function providerById(providers, providerId) {
  var rows = Array.isArray(providers) ? providers : []
  var wanted = String(providerId || "")
  if (wanted === "") return null
  for (var i = 0; i < rows.length; i++) {
    if (rows[i] && rows[i].id === wanted) return rows[i]
  }
  return null
}

function barHeadline(providers, selectedId) {
  var selected = providerById(providers, selectedId)
  if (selected) return selected
  var rows = Array.isArray(providers) ? providers : []
  var best = null
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i]
    if (!row || row.error || !row.binding) continue
    if (!best || row.binding.usedPercent > best.binding.usedPercent) best = row
  }
  return best
}

function barCaption(provider) {
  if (!provider) return ""
  if (provider.binding) return provider.name + " " + Math.round(provider.binding.usedPercent) + "%"
  if (provider.error) return provider.name
  return provider.name || ""
}

function barSlotLabels(providers, loading) {
  var rows = Array.isArray(providers) ? providers : []
  var labels = []
  if (loading && rows.length === 0) return ["…"]
  for (var i = 0; i < rows.length; i++) {
    var caption = barCaption(rows[i])
    if (caption) labels.push(caption)
  }
  if (labels.length === 0) labels.push("Token Monitor")
  return labels
}

function longestBarLabel(providers, loading) {
  var labels = barSlotLabels(providers, loading)
  var best = labels.length ? labels[0] : "Token Monitor"
  for (var i = 1; i < labels.length; i++) {
    if (labels[i].length > best.length) best = labels[i]
  }
  return best
}

function barText(providers, loading, selectedId) {
  if (loading && (!providers || providers.length === 0)) return "…"
  var headline = barHeadline(providers, selectedId)
  var caption = barCaption(headline)
  if (caption) return caption
  if (!providers || providers.length === 0) return "—"
  return "Token Monitor"
}

function barIconId(providers, loading, selectedId) {
  var headline = barHeadline(providers, selectedId)
  if (headline && headline.id) return headline.id
  var rows = Array.isArray(providers) ? providers : []
  for (var i = 0; i < rows.length; i++) {
    if (rows[i] && rows[i].id) return rows[i].id
  }
  return "codex"
}

function barTooltip(providers, missingCli) {
  if (missingCli) return "python3 could not run collect.py. Install Python 3, then refresh."
  var rows = Array.isArray(providers) ? providers : []
  if (rows.length === 0) return "Token Monitor"
  var lines = []
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i]
    if (!row) continue
    if (row.error) {
      lines.push(row.name + ": " + row.error)
      continue
    }
    if (row.binding) {
      lines.push(row.name + " " + Math.round(row.binding.usedPercent) + "% · " + row.binding.title)
      continue
    }
    if (row.creditsRemaining !== null) {
      lines.push(row.name + " " + formatCredits(row.creditsRemaining, row.creditsUnit))
      continue
    }
    lines.push(row.name + ": waiting for CodexBar")
  }
  return lines.join("\n")
}

function formatCredits(remaining, unit) {
  var amount = asNumber(remaining)
  if (amount === null) return ""
  var label = String(unit || "credits")
  if (label === "usd" || label === "USD" || label === "$") return "$" + amount.toFixed(2)
  var rounded = Math.abs(amount - Math.round(amount)) < 0.05 ? String(Math.round(amount)) : amount.toFixed(1)
  return rounded + " " + label
}

function formatMoney(value) {
  var amount = asNumber(value)
  if (amount === null) return ""
  return "$" + amount.toFixed(2)
}

function formatDuration(ms) {
  if (!(ms > 0)) return "now"
  var minutes = Math.floor(ms / 60000)
  var hours = Math.floor(minutes / 60)
  var days = Math.floor(hours / 24)
  if (days > 0) return days + "d " + (hours % 24) + "h"
  if (hours > 0) return hours + "h " + (minutes % 60) + "m"
  return Math.max(1, minutes) + "m"
}

function parseStampMs(stamp) {
  var ms = Date.parse(String(stamp || ""))
  return isFinite(ms) ? ms : null
}

// True when no provider row carries a readable updatedAt, or the newest
// one is older than the refresh interval. Used to refresh on panel open
// even when the refresh-on-open setting is off.
function snapshotStale(providers, intervalSec, nowMs) {
  var rows = Array.isArray(providers) ? providers : []
  var newest = null
  for (var i = 0; i < rows.length; i++) {
    var ms = parseStampMs(rows[i] && rows[i].updatedAt)
    if (ms !== null && (newest === null || ms > newest)) newest = ms
  }
  if (newest === null) return true
  var now = isFinite(nowMs) ? nowMs : Date.now()
  var interval = isFinite(intervalSec) && intervalSec > 0 ? intervalSec : DEFAULT_REFRESH_SEC
  return now - newest >= interval * 1000
}

function pad2(value) {
  return (value < 10 ? "0" : "") + value
}

function formatClock(stamp) {
  var ms = parseStampMs(stamp)
  if (ms === null) return ""
  var date = new Date(ms)
  return pad2(date.getHours()) + ":" + pad2(date.getMinutes())
}

function formatUpdatedAgo(stamp, nowMs) {
  var ms = parseStampMs(stamp)
  if (ms === null) return ""
  var now = isFinite(nowMs) ? nowMs : Date.now()
  var delta = now - ms
  if (delta < 0) delta = 0
  if (delta < 15000) return "just now"
  if (delta < 60000) return Math.floor(delta / 1000) + "s ago"
  if (delta < 3600000) return Math.floor(delta / 60000) + "m ago"
  if (delta < 86400000) return Math.floor(delta / 3600000) + "h ago"
  return Math.floor(delta / 86400000) + "d ago"
}

function formatUpdatedAt(stamp, nowMs) {
  var ago = formatUpdatedAgo(stamp, nowMs)
  if (ago === "") return ""
  var clock = formatClock(stamp)
  if (clock) return "Updated " + clock + " · " + ago
  return "Updated " + ago
}

function resetRemainingMs(resetAt, nowMs) {
  var stamp = String(resetAt || "")
  if (stamp === "") return -1
  var ms = Date.parse(stamp)
  if (!isFinite(ms)) return -1
  var now = isFinite(nowMs) ? nowMs : Date.now()
  return ms - now
}

function prettyPlanPart(providerId, raw) {
  var value = String(raw || "").trim()
  if (value === "") return ""
  var id = String(providerId || "")
  var key = value.toLowerCase().replace(/[\s-]+/g, "_")
  var maps = {
    codex: {
      guest: "Guest",
      free: "Free",
      go: "Go",
      plus: "Plus",
      plus_plan: "Plus",
      chatgpt_plus: "Plus",
      pro: "Pro 20x",
      codex_pro: "Pro 20x",
      prolite: "Pro 5x",
      pro_lite: "Pro 5x",
      prolite_plan: "Pro 5x",
      codex_pro_lite: "Pro 5x",
      free_workspace: "Free Workspace",
      team: "Team",
      business: "Business",
      education: "Education",
      enterprise: "Enterprise",
      edu: "Edu"
    },
    cursor: {
      hobby: "Hobby",
      pro: "Pro",
      pro_student: "Pro",
      pro_plus: "Pro+",
      ultra: "Ultra",
      team: "Team",
      enterprise: "Enterprise"
    },
    kimi: {
      level_free: "Free",
      adagio: "Adagio",
      andante: "Andante",
      moderato: "Moderato",
      allegretto: "Allegretto",
      allegro: "Allegro",
      vivace: "Vivace"
    },
    grok: {
      free: "Free",
      premium: "X Premium",
      x_premium: "X Premium",
      premiumplus: "X Premium+",
      premium_plus: "X Premium+",
      x_premium_plus: "X Premium+",
      lite: "SuperGrok Lite",
      supergrok_lite: "SuperGrok Lite",
      supergrok: "SuperGrok",
      super_grok: "SuperGrok",
      plus: "SuperGrok Plus",
      supergrok_plus: "SuperGrok Plus",
      heavy: "SuperGrok Heavy",
      supergrok_heavy: "SuperGrok Heavy",
      super_grok_heavy: "SuperGrok Heavy"
    },
    notion: {
      free: "Free",
      plus: "Plus",
      business: "Business",
      enterprise: "Enterprise"
    },
    zed: {
      zed_free: "Free",
      zed_pro: "Pro",
      zed_trial: "Trial",
      zed_student: "Student",
      zed_business: "Business"
    },
    factory: {
      hobby: "Hobby",
      pro: "Pro",
      team: "Team",
      team_annual: "Team Annual",
      enterprise: "Enterprise",
      factory_pro_annual_plan: "Factory Pro Annual Plan"
    }
  }
  var mapped = maps[id] && maps[id][key]
  if (mapped) return mapped
  if (value.indexOf(".") >= 0) return value
  if (value.indexOf("_") >= 0 || value === value.toLowerCase()) {
    return value.split(/[_\s]+/).map(function(part) {
      return part ? part.charAt(0).toUpperCase() + part.slice(1) : ""
    }).join(" ")
  }
  return value
}

function prettyPlan(providerId, raw) {
  var value = String(raw || "").trim()
  if (value === "") return ""
  return value.split(" · ").map(function(part) {
    return part.split(" + ").map(function(item) {
      return prettyPlanPart(providerId, item)
    }).join(" + ")
  }).join(" · ")
}

function heroMeta(provider, settings) {
  if (!provider) return ""
  if (provider.error) return provider.error
  var plan = prettyPlan(provider.id, provider.plan)
  var email = hideEmail(settings) ? "" : String(provider.accountEmail || "")
  if (plan && email) return plan + " · " + email
  if (plan) return plan
  if (email) return email
  if (provider.source) return provider.source
  return "Waiting for usage"
}

function clamp(value, lo, hi) {
  return Math.max(lo, Math.min(hi, value))
}
