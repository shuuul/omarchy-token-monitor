import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "shuuul.token-monitor"
  ipcTarget: "shuuul.token-monitor"
  manageIpc: false

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property color track: Style.selectedFillFor(foreground, Color.accent)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  readonly property var providers: usage.providers
  property string selectedProviderId: ""
  readonly property int providerIndex: {
    for (var i = 0; i < providers.length; i++)
      if (providers[i].id === selectedProviderId) return i
    return 0
  }
  readonly property var provider: providers.length > 0 ? providers[providerIndex] : null
  readonly property var limits: provider ? provider.windows : []
  readonly property bool alarming: usage.alarming

  property bool cursorActive: false
  property double nowMs: Date.now()

  function clamp(v, lo, hi) { return Model.clamp(v, lo, hi) }
  function alpha(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }

  function selectProvider(index) {
    if (providers.length === 0) return
    var wrapped = ((index % providers.length) + providers.length) % providers.length
    selectedProviderId = providers[wrapped].id
  }

  function refreshNow(onlyId) {
    usage.refresh(onlyId || selectedProviderId)
  }

  function resetMsFor(window) {
    return Model.resetRemainingMs(window ? window.resetAt : "", root.nowMs)
  }

  function heroMeta(p) {
    return Model.heroMeta(p)
  }

  function creditsText(p) {
    if (!p || p.creditsRemaining === null) return ""
    return Model.formatCredits(p.creditsRemaining, p.creditsUnit)
  }

  visible: true
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onProviderIndexChanged: if (panelFlick) panelFlick.contentY = 0
  onProvidersChanged: {
    if (selectedProviderId !== "") return
    if (usage.headline && usage.headline.id) selectedProviderId = usage.headline.id
  }
  onOpenedChanged: if (opened) {
    cursorActive = false
    nowMs = Date.now()
    if (panelFlick) panelFlick.contentY = 0
    if (usage.headline && usage.headline.id) selectedProviderId = usage.headline.id
    usage.refresh("")
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  Service {
    id: usage
    settings: root.settings
  }

  Timer {
    interval: 30000
    running: root.opened
    repeat: true
    onTriggered: root.nowMs = Date.now()
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): string { root.refreshNow(); return "ok" }
    function next(): string { root.selectProvider(root.providerIndex + 1); return "ok" }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: usage.barLabelFor(selectedProviderId)
    labelVisible: false
    tooltipText: usage.barTooltip
    active: root.alarming
    horizontalMargin: 10
    hasVisualContent: true
    fixedWidth: barSlot.width + Style.space(16)
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) root.refreshNow()
      else if (buttonCode === Qt.MiddleButton) root.selectProvider(root.providerIndex + 1)
      else root.toggle()
    }

    readonly property var iconWindows: Model.iconWindows(root.provider)
    readonly property real weeklyRemaining: iconWindows.weeklyRemaining === null ? -1 : iconWindows.weeklyRemaining / 100
    readonly property real sessionRemaining: iconWindows.sessionRemaining === null ? -1 : iconWindows.sessionRemaining / 100
    readonly property int markSize: Style.bar.iconCanvas
    readonly property int meterGap: Math.max(2, Math.round(markSize * 0.12))
    readonly property int weeklyHeight: Math.max(4, Math.round((markSize - meterGap) * 0.58))
    readonly property int sessionHeight: Math.max(3, markSize - meterGap - weeklyHeight)
    readonly property int meterWidth: markSize

    Item {
      id: barSlot
      anchors.verticalCenter: parent.verticalCenter
      anchors.horizontalCenter: parent.horizontalCenter
      width: button.markSize + Style.space(6) + usageBars.width
      height: button.markSize

      Image {
        id: barIcon
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: button.markSize
        height: button.markSize
        source: Qt.resolvedUrl("assets/" + usage.barIconIdFor(selectedProviderId) + ".svg")
        sourceSize.width: button.markSize * 2
        sourceSize.height: button.markSize * 2
        fillMode: Image.PreserveAspectFit
        asynchronous: false
        visible: false
        layer.enabled: true
      }

      MultiEffect {
        id: barIconTint
        anchors.fill: barIcon
        source: barIcon
        colorization: 1.0
        colorizationColor: button.active ? button.activeColor : button.foreground
      }

      Column {
        id: usageBars
        anchors.left: barIcon.right
        anchors.leftMargin: Style.space(6)
        anchors.verticalCenter: parent.verticalCenter
        spacing: button.meterGap
        width: button.meterWidth
        height: button.markSize

        UsageBar {
          remaining: button.weeklyRemaining
          barHeight: button.weeklyHeight
        }

        UsageBar {
          remaining: button.sessionRemaining
          barHeight: button.sessionHeight
        }
      }
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(640))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent

      onMoveRequested: function(dx, dy) {
        if (dx !== 0) {
          root.cursorActive = true
          root.selectProvider(root.providerIndex + dx)
        }
        if (dy !== 0)
          panelFlick.contentY = root.clamp(panelFlick.contentY + dy * Style.space(56), 0,
                                           Math.max(0, panelFlick.contentHeight - panelFlick.height))
      }
      onActivateRequested: root.refreshNow()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) { if (t === "r" || t === "R") root.refreshNow() }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: panelFlick.width
          spacing: Style.space(12)

          PanelHero {
            id: hero
            visible: !!root.provider
            width: parent.width
            title: root.provider ? root.provider.name : ""
            meta: root.heroMeta(root.provider)
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Text {
            visible: root.providers.length === 0
            width: parent.width
            topPadding: Style.space(24)
            text: usage.lastError !== ""
              ? usage.lastError
              : "Waiting for Amp, Codex, Kimi, Cursor, Grok, Notion, and Zed."
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
          }

          Flow {
            id: providerSwitch
            visible: root.providers.length > 1
            width: parent.width
            spacing: Style.space(6)

            Repeater {
              model: root.providers

              Button {
                required property var modelData
                required property int index

                text: modelData.name
                selected: index === root.providerIndex
                hasCursor: root.cursorActive && index === root.providerIndex
                bordered: true
                foreground: root.foreground
                fontFamily: root.fontFamily
                fontSize: Style.font.body
                verticalPadding: Style.spacing.controlPaddingY
                onClicked: {
                  root.cursorActive = true
                  root.selectProvider(index)
                }
                onHovered: function(isHovered) { if (isHovered) root.cursorActive = true }
              }
            }
          }

          BorderSurface {
            visible: !!root.provider && root.provider.error !== ""
            width: parent.width
            implicitHeight: statusText.implicitHeight + Style.spacing.xl * 2
            color: root.alpha(root.urgent, 0.10)
            borderSpec: Border.flat(root.alpha(root.urgent, 0.35), 1)
            radius: Style.cornerRadius

            Text {
              id: statusText
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.leftMargin: Style.space(12)
              anchors.rightMargin: Style.space(12)
              text: root.provider ? root.provider.error : ""
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }
          }

          Column {
            visible: !!root.provider && root.provider.accountEmail !== ""
            width: parent.width

            Text {
              width: parent.width
              text: root.provider ? root.provider.accountEmail : ""
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }
          }

          PanelSeparator {
            visible: creditsSection.visible || limitsSection.visible
            foreground: root.foreground
          }

          Column {
            id: creditsSection
            visible: !!root.provider && root.provider.creditsRemaining !== null
            width: parent.width
            spacing: Style.space(10)

            PanelSectionHeader {
              width: parent.width
              text: "CREDITS"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Item {
              width: parent.width
              implicitHeight: Math.max(creditsLabel.implicitHeight, creditsValue.implicitHeight)

              Text {
                id: creditsLabel
                text: "Remaining"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
              }

              Text {
                id: creditsValue
                text: root.creditsText(root.provider)
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
              }
            }

            Text {
              visible: !!root.provider && root.provider.costToday !== null
              width: parent.width
              text: root.provider ? "Today " + Model.formatMoney(root.provider.costToday) : ""
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }
          }

          Column {
            id: limitsSection
            visible: root.limits.length > 0
            width: parent.width
            spacing: Style.space(10)

            PanelSectionHeader {
              text: "LIMITS"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Repeater {
              model: root.limits

              LimitRow {
                required property var modelData
                width: limitsSection.width
                window: modelData
              }
            }
          }

          Text {
            visible: !!root.provider && root.provider.paceSummary !== ""
            width: parent.width
            text: root.provider ? root.provider.paceSummary : ""
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }

          Text {
            visible: !!root.provider && (root.provider.updatedAt !== "" || root.provider.source !== "")
            width: parent.width
            text: {
              if (!root.provider) return ""
              var stamp = Model.formatUpdatedAt(root.provider.updatedAt, root.nowMs)
              if (stamp && root.provider.source) return stamp + " · " + root.provider.source
              if (stamp) return stamp
              return root.provider.source ? "Source " + root.provider.source : ""
            }
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Button {
            width: parent.width
            text: usage.busy ? "Refreshing…" : (root.provider ? "Refresh " + root.provider.name : "Refresh")
            enabled: !usage.busy && !!root.provider
            bordered: true
            foreground: root.foreground
            fontFamily: root.fontFamily
            fontSize: Style.font.body
            verticalPadding: Style.spacing.controlPaddingY
            onClicked: root.refreshNow(root.selectedProviderId)
          }
        }
      }
    }
  }

  component LimitRow: Column {
    id: limitRow
    property var window: null
    readonly property bool alarming: window && window.usedPercent >= 90

    spacing: Style.space(6)

    Item {
      width: parent.width
      implicitHeight: Math.max(limitLabel.implicitHeight, limitValue.implicitHeight)

      Text {
        id: limitLabel
        text: limitRow.window ? limitRow.window.title : ""
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        elide: Text.ElideRight
        anchors.left: parent.left
        anchors.right: limitValue.left
        anchors.rightMargin: Style.spacing.sm
        anchors.verticalCenter: parent.verticalCenter
      }

      Text {
        id: limitValue
        text: limitRow.window ? Math.round(limitRow.window.usedPercent) + "%" : "—"
        color: limitRow.alarming ? root.urgent : root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
      }
    }

    Meter {
      width: parent.width
      value: limitRow.window ? limitRow.window.usedPercent / 100 : -1
      alarming: limitRow.alarming
    }

    Text {
      width: parent.width
      text: {
        var remainingMs = root.resetMsFor(limitRow.window)
        return remainingMs > 0 ? "Resets in " + Model.formatDuration(remainingMs) : ""
      }
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  component UsageBar: Item {
    id: usageBar
    property real remaining: -1
    property real barHeight: Math.max(4, Math.round(Style.space(5)))

    width: parent ? parent.width : Style.space(18)
    implicitHeight: barHeight
    height: barHeight

    Rectangle {
      id: usageTrack
      anchors.fill: parent
      radius: height / 2
      color: root.alpha(button.foreground, 0.28)
      border.width: 1
      border.color: root.alpha(button.foreground, 0.44)
    }

    Rectangle {
      visible: usageBar.remaining >= 0
      anchors.left: usageTrack.left
      anchors.verticalCenter: usageTrack.verticalCenter
      height: usageTrack.height
      radius: usageTrack.radius
      width: usageTrack.width * root.clamp(usageBar.remaining, 0, 1)
      color: button.active ? button.activeColor : button.foreground
    }
  }

  component Meter: Item {
    id: meter
    property real value: -1
    property bool alarming: false
    property real thickness: Math.max(Style.space(4), Math.round(Style.spacing.controlHeight * 0.14))

    implicitHeight: thickness

    Rectangle {
      id: meterTrack
      anchors.fill: parent
      radius: height / 2
      color: root.track
    }

    Rectangle {
      anchors.left: meterTrack.left
      anchors.verticalCenter: meterTrack.verticalCenter
      height: meterTrack.height
      radius: meterTrack.radius
      width: meterTrack.width * root.clamp(meter.value, 0, 1)
      color: meter.alarming ? root.urgent : root.foreground

      Behavior on width {
        NumberAnimation { duration: 160; easing.type: Easing.OutCubic }
      }
    }
  }
}
