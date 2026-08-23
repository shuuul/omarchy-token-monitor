.pragma library

// Pure CodexBar usage JSON parsing and formatting. QML owns theme and
// process I/O; this file is what the node tests exercise.

var DEFAULT_CODEXBAR_PATH = "codexbar"
var DEFAULT_REFRESH_SEC = 300
var MIN_REFRESH_SEC = 30
var MAX_REFRESH_SEC = 3600

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

function commandPath(settings) {
  var raw = settings ? settings.codexbarPath : undefined
  var value = String(raw === undefined || raw === null ? "" : raw).trim()
  return value === "" ? DEFAULT_CODEXBAR_PATH : value
}

function usageCommand(settings) {
  return [
    commandPath(settings),
    "usage",
    "--format", "json",
    "--json-only"
  ]
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

function parseError(text, exitCode) {
  var data = lastJsonValue(text)
  if (data && !Array.isArray(data) && data.error) return errorText(data.error)
  var trimmed = String(text || "").trim()
  if (trimmed !== "") {
    var lines = trimmed.split("\n")
    return lines[lines.length - 1]
  }
  if (exitCode === 2) return "codexbar is not on PATH"
  if (exitCode === 139) return "codexbar crashed"
  if (exitCode) return "codexbar exited " + exitCode
  return "codexbar returned no snapshot"
}

function asNumber(value) {
  if (value === undefined || value === null || value === "") return null
  var number = Number(value)
  return isFinite(number) ? number : null
}

function errorText(value) {
  if (value === undefined || value === null || value === false) return ""
  if (typeof value === "string") return value
  if (typeof value === "object") {
    if (value.message) return String(value.message)
    if (value.error) return errorText(value.error)
  }
  return String(value)
}

function windowTitle(label, kind, minutes) {
  var text = String(label || "").toLowerCase()
  var kindText = String(kind || "").toLowerCase()
  if (kindText === "session" || text.indexOf("session") >= 0) return "Session"
  if (kindText === "weekly" || text.indexOf("week") >= 0 || text.indexOf("7-day") >= 0) return "Weekly"
  if (text.indexOf("month") >= 0 || text.indexOf("30-day") >= 0) return "Monthly"
  if (text.indexOf("day") >= 0 || text.indexOf("daily") >= 0) return "Daily"
  if (minutes === 300) return "Session"
  if (minutes === 10080) return "Weekly"
  var plain = String(label || "").replace(/\s*\(.*\)\s*/, "").trim()
  return plain === "" ? "Limit" : plain
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
  var primary = normalizeRateWindow(usage.primary, "Session", "session")
  var secondary = normalizeRateWindow(usage.secondary, "Weekly", "weekly")
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
  var cost = row.cost || {}
  display.costToday = asNumber(cost.todayUSD)
  display.costLast30Days = asNumber(cost.last30DaysUSD)
  display.paceSummary = firstPaceSummary(row.pace)
  display.error = errorText(row.error)
  display.updatedAt = String(usage.updatedAt || row.updatedAt || "")
  display.alarming = (!!display.binding && display.binding.usedPercent >= 90)
    || display.statusLevel === "critical"
    || display.error !== ""
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

function barHeadline(providers) {
  var rows = Array.isArray(providers) ? providers : []
  var best = null
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i]
    if (!row || row.error || !row.binding) continue
    if (!best || row.binding.usedPercent > best.binding.usedPercent) best = row
  }
  return best
}

function barText(providers, loading) {
  if (loading && (!providers || providers.length === 0)) return "…"
  var headline = barHeadline(providers)
  if (headline) return headline.monogram + " " + Math.round(headline.binding.usedPercent) + "%"
  if (!providers || providers.length === 0) return "—"
  for (var i = 0; i < providers.length; i++) {
    if (providers[i] && providers[i].error) return "ERR"
  }
  return "—"
}

function barTooltip(providers, missingCli) {
  if (missingCli) return "Install the CodexBar Linux CLI, then enable Amp, Codex, Kimi, Cursor, Grok, Notion, or Zed."
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

function resetRemainingMs(resetAt, nowMs) {
  var stamp = String(resetAt || "")
  if (stamp === "") return -1
  var ms = Date.parse(stamp)
  if (!isFinite(ms)) return -1
  var now = isFinite(nowMs) ? nowMs : Date.now()
  return ms - now
}

function heroMeta(provider) {
  if (!provider) return ""
  if (provider.error) return provider.error
  if (provider.plan) return provider.plan
  if (provider.accountEmail) return provider.accountEmail
  if (provider.source) return provider.source
  return "Waiting for CodexBar"
}

function clamp(value, lo, hi) {
  return Math.max(lo, Math.min(hi, value))
}
