import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model
import "Providers.js" as Providers

// CodexBar owns auth, fetch, and provider mapping. This object only runs
// `codexbar dashboard` and keeps the last good snapshot for the panel.
Item {
  id: root
  visible: false

  property var settings: ({})

  property var snapshot: Model.emptySnapshot()
  property string lastError: ""
  property bool missingCli: false
  property bool hasSnapshot: false
  property int dataRevision: 0

  readonly property int refreshIntervalSec: Model.refreshIntervalSec(settings)
  readonly property var enabledIds: Providers.enabledIds(settings)
  readonly property var providers: {
    var rev = dataRevision
    return Model.providersFromSnapshot(snapshot, enabledIds, Providers.catalog())
  }
  readonly property var headline: Model.barHeadline(providers)
  readonly property bool alarming: {
    for (var i = 0; i < providers.length; i++)
      if (providers[i] && providers[i].alarming) return true
    return false
  }
  readonly property bool busy: dashboardProcess.running
  function barLabelFor(selectedId) {
    return Model.barText(providers, busy && !hasSnapshot, selectedId)
  }
  function barIconIdFor(selectedId) {
    return Model.barIconId(providers, busy && !hasSnapshot, selectedId)
  }
  readonly property string barLabel: barLabelFor("")
  readonly property string barIconId: barIconIdFor("")
  readonly property string barTooltip: Model.barTooltip(providers, missingCli)

  readonly property string pluginDir: {
    var url = Qt.resolvedUrl("collect.py").toString()
    return url.replace(/^file:\/\//, "").replace(/\/collect\.py$/, "")
  }

  function refresh() {
    if (dashboardProcess.running) return
    dashboardProcess.command = Model.collectCommand({
      collectPath: root.pluginDir + "/collect.py"
    })
    dashboardProcess.running = true
  }

  function applyOutput(text, exitCode) {
    var next = Model.parseSnapshot(text)
    if (next) {
      snapshot = next
      lastError = ""
      missingCli = false
      hasSnapshot = true
      dataRevision++
      return
    }
    lastError = Model.parseError(text, exitCode)
    missingCli = exitCode === 2
    dataRevision++
  }

  Component.onCompleted: refresh()

  Timer {
    interval: root.refreshIntervalSec * 1000
    running: true
    repeat: true
    onTriggered: root.refresh()
  }

  Process {
    id: dashboardProcess
    running: false

    stdout: StdioCollector {
      id: dashboardStdout
      waitForEnd: true
    }

    stderr: StdioCollector {
      id: dashboardStderr
      waitForEnd: true
    }

    onExited: function(exitCode) {
      var stdout = String(dashboardStdout.text || "")
      var stderr = String(dashboardStderr.text || "")
      root.applyOutput(stdout !== "" ? stdout : stderr, exitCode)
      if (exitCode !== 0 && stderr !== "")
        console.warn("token-monitor", stderr.trim())
    }
  }
}
