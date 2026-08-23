import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model
import "Providers.js" as Providers

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
  property bool settingsOpen: false
  property bool providerDragActive: false
  property double nowMs: Date.now()

  function clamp(v, lo, hi) { return Model.clamp(v, lo, hi) }
  function alpha(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }

  function setSelectedProvider(id) {
    var next = String(id || "")
    selectedProviderId = next
    if (next && Model.rememberedProviderId(root.settings) !== next)
      persistSettings({ selectedProviderId: next })
  }

  function selectProvider(index) {
    if (providers.length === 0) return
    var wrapped = ((index % providers.length) + providers.length) % providers.length
    setSelectedProvider(providers[wrapped].id)
  }

  function restoreSelectedProvider() {
    var next = Model.resolveSelectedProviderId(root.settings, providers, selectedProviderId)
    if (next && next !== selectedProviderId) selectedProviderId = next
  }

  function refreshNow(onlyId) {
    usage.refresh(onlyId || selectedProviderId)
  }

  function persistSettings(values) {
    var entry = Model.mergeSettings(root.settings, values)
    entry.id = root.moduleName
    root.settings = entry
    if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  function setBrowser(name) {
    persistSettings({ browser: Model.browserName({ browser: name }) })
  }

  function setRefreshMinutes(minutes) {
    persistSettings({ refreshIntervalSec: Model.refreshIntervalSec({ refreshIntervalSec: minutes * 60 }) })
  }

  function setRefreshOnOpen(enabled) {
    persistSettings({ refreshOnOpen: !!enabled })
  }

  function setShowRemaining(enabled) {
    persistSettings({ showRemaining: !!enabled })
  }

  function setHideEmail(enabled) {
    persistSettings({ hideEmail: !!enabled })
  }

  function setProviderEnabled(id, enabled) {
    persistSettings({ providers: Model.withProviderEnabled(root.settings, id, enabled).providers })
  }

  function setProviderOrder(ids) {
    persistSettings({ providerOrder: Providers.orderedIds({ providerOrder: ids }) })
  }

  function reloadSettingsModel() {
    if (!settingsProviderModel || root.providerDragActive) return
    var rows = Providers.settingsCatalog(root.settings)
    if (settingsProviderModel.count === rows.length) {
      var same = true
      for (var i = 0; i < rows.length; i++) {
        if (settingsProviderModel.get(i).id !== rows[i].id) {
          same = false
          break
        }
      }
      if (same) {
        for (var j = 0; j < rows.length; j++)
          settingsProviderModel.setProperty(j, "enabled", rows[j].enabled)
        return
      }
    }
    settingsProviderModel.clear()
    for (var k = 0; k < rows.length; k++) settingsProviderModel.append(rows[k])
  }

  function persistSettingsOrder() {
    var ids = []
    for (var i = 0; i < settingsProviderModel.count; i++)
      ids.push(settingsProviderModel.get(i).id)
    setProviderOrder(ids)
  }

  function providerIndexAt(y) {
    var count = settingsProviderModel.count
    if (count <= 1) return 0
    var height = 0
    for (var i = 0; i < providerColumn.children.length; i++) {
      var child = providerColumn.children[i]
      if (child && child.height > 0) {
        height = child.height
        break
      }
    }
    if (!(height > 0)) return 0
    var stride = height + providerColumn.spacing
    var idx = Math.floor(y / stride)
    if (idx < 0) return 0
    if (idx >= count) return count - 1
    return idx
  }

  function resetMsFor(window) {
    return Model.resetRemainingMs(window ? window.resetAt : "", root.nowMs)
  }

  function heroMeta(p) {
    return Model.heroMeta(p, root.settings)
  }

  function creditsText(p) {
    if (!p || p.creditsRemaining === null) return ""
    return Model.formatCredits(p.creditsRemaining, p.creditsUnit)
  }

  visible: true
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onProviderIndexChanged: if (panelFlick) panelFlick.contentY = 0
  onProvidersChanged: root.restoreSelectedProvider()
  // Opening the panel fetches only when Settings → Refresh on open is on.
  // Default is off: data then comes from the interval timer and Refresh.
  // Do not jump to the most-used headline; keep the last selected provider.
  onOpenedChanged: if (opened) {
    cursorActive = false
    nowMs = Date.now()
    if (panelFlick) panelFlick.contentY = 0
    root.restoreSelectedProvider()
    if (Model.refreshOnOpen(root.settings)) usage.refresh("")
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }
  onSettingsChanged: {
    root.reloadSettingsModel()
    root.restoreSelectedProvider()
  }
  Component.onCompleted: {
    root.reloadSettingsModel()
    root.restoreSelectedProvider()
  }

  ListModel {
    id: settingsProviderModel
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
    active: false
    horizontalMargin: 10
    hasVisualContent: true
    fixedWidth: barSlot.width + Style.space(16)
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) root.refreshNow()
      else if (buttonCode === Qt.MiddleButton) root.selectProvider(root.providerIndex + 1)
      else root.toggle()
    }

    readonly property var iconWindows: Model.iconWindows(root.provider)
    readonly property bool showRemaining: Model.showRemaining(root.settings)
    readonly property real weeklyFill: {
      var value = button.showRemaining ? iconWindows.weeklyRemaining : iconWindows.weeklyUsed
      return value === null ? -1 : value / 100
    }
    readonly property real sessionFill: {
      var value = button.showRemaining ? iconWindows.sessionRemaining : iconWindows.sessionUsed
      return value === null ? -1 : value / 100
    }
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
        colorizationColor: root.foreground
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
          remaining: button.weeklyFill
          barHeight: button.weeklyHeight
        }

        UsageBar {
          remaining: button.sessionFill
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
    // No height cap: the panel expands to fit every provider row.
    // fittedContentHeight still clamps to the screen, and panelFlick
    // scrolls (ScrollBar.AsNeeded) when content outgrows the screen.
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

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

          Item {
            visible: !!root.provider && !root.settingsOpen
            width: parent.width
            implicitHeight: Math.max(hero.implicitHeight, settingsButton.implicitHeight)

            PanelHero {
              id: hero
              anchors.left: parent.left
              anchors.right: settingsButton.left
              anchors.rightMargin: Style.space(8)
              anchors.verticalCenter: parent.verticalCenter
              title: root.provider ? root.provider.name : ""
              meta: root.heroMeta(root.provider)
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            PanelActionButton {
              id: settingsButton
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              iconText: "󰒓"
              tooltipText: "Settings"
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.settingsOpen = true
            }
          }

          Item {
            visible: root.settingsOpen
            width: parent.width
            implicitHeight: settingsHeader.implicitHeight

            Text {
              id: settingsHeader
              text: "Settings"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
            }

            PanelActionButton {
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              iconText: "󰅖"
              tooltipText: "Close settings"
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.settingsOpen = false
            }
          }

          Column {
            visible: root.settingsOpen
            width: parent.width
            spacing: Style.space(12)

            Dropdown {
              width: parent.width
              label: "Refresh interval"
              value: String(Math.round(usage.refreshIntervalSec / 60))
              options: [
                { value: "1", label: "1 minute" },
                { value: "5", label: "5 minutes" },
                { value: "10", label: "10 minutes" },
                { value: "15", label: "15 minutes" },
                { value: "30", label: "30 minutes" },
                { value: "60", label: "60 minutes" }
              ]
              foreground: root.foreground
              fontFamily: root.fontFamily
              onChanged: function(value) { root.setRefreshMinutes(parseInt(value, 10)) }
            }

            Toggle {
              width: parent.width
              label: "Refresh on open"
              description: "Fetch every provider when the panel opens."
              checked: Model.refreshOnOpen(root.settings)
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.setRefreshOnOpen(!Model.refreshOnOpen(root.settings))
            }

            Toggle {
              width: parent.width
              label: "Show remaining"
              description: "Bar and limits show leftover quota. Off shows used."
              checked: Model.showRemaining(root.settings)
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.setShowRemaining(!Model.showRemaining(root.settings))
            }

            Toggle {
              width: parent.width
              label: "Hide email"
              description: "Do not show the account email on the panel."
              checked: Model.hideEmail(root.settings)
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.setHideEmail(!Model.hideEmail(root.settings))
            }

            Dropdown {
              width: parent.width
              label: "Browser cookies"
              value: Model.browserName(root.settings)
              options: [
                { value: "chrome", label: "Chrome" },
                { value: "chromium", label: "Chromium" }
              ]
              foreground: root.foreground
              fontFamily: root.fontFamily
              onChanged: function(value) { root.setBrowser(value) }
            }

            Text {
              text: "Providers"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
            }

            Text {
              width: parent.width
              text: "Drag a row to reorder the main panel."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }

            Item {
              id: providerList
              width: parent.width
              implicitHeight: providerColumn.implicitHeight
              height: implicitHeight

              Column {
                id: providerColumn
                width: parent.width
                spacing: Style.space(6)
                move: Transition {
                  NumberAnimation { properties: "y"; duration: 120; easing.type: Easing.OutCubic }
                }

                Repeater {
                  model: settingsProviderModel

                  Toggle {
                    required property var model
                    width: providerColumn.width
                    label: model.name
                    checked: model.enabled
                    foreground: root.foreground
                    fontFamily: root.fontFamily
                  }
                }
              }

              MouseArea {
                id: providerDrag
                anchors.fill: parent
                hoverEnabled: true
                preventStealing: true
                cursorShape: dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                property bool dragging: false
                property bool moved: false
                property int fromIndex: -1
                property real pressY: 0

                onPressed: function(mouse) {
                  fromIndex = root.providerIndexAt(mouse.y)
                  pressY = mouse.y
                  dragging = false
                  moved = false
                  root.providerDragActive = true
                }
                onPositionChanged: function(mouse) {
                  if (!pressed) return
                  if (Math.abs(mouse.y - pressY) < 8) return
                  dragging = true
                  var nextIndex = root.providerIndexAt(mouse.y)
                  if (nextIndex < 0 || nextIndex === fromIndex) return
                  settingsProviderModel.move(fromIndex, nextIndex, 1)
                  fromIndex = nextIndex
                  moved = true
                }
                onReleased: {
                  root.providerDragActive = false
                  if (moved) root.persistSettingsOrder()
                  else if (fromIndex >= 0) {
                    var row = settingsProviderModel.get(fromIndex)
                    if (row) root.setProviderEnabled(row.id, !row.enabled)
                  }
                  dragging = false
                  moved = false
                  fromIndex = -1
                }
                onCanceled: {
                  root.providerDragActive = false
                  dragging = false
                  moved = false
                  fromIndex = -1
                }
              }
            }
          }

          Text {
            visible: !root.settingsOpen && root.providers.length === 0
            width: parent.width
            topPadding: Style.space(24)
            text: usage.lastError !== ""
              ? usage.lastError
              : "Waiting for Amp, Codex, Kimi, Cursor, Grok, Notion, Zed, and Droid."
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
          }

          Flow {
            id: providerSwitch
            visible: !root.settingsOpen && root.providers.length > 1
            width: parent.width
            spacing: Style.space(6)

            Repeater {
              model: root.providers

              // Delegate root must be a module type (BorderSurface): local
              // file types do not receive Repeater's modelData/index in
              // compiled QML. qs.Ui.Button only paints font glyphs
              // (`iconText`), so mirror its state tokens here, with the
              // official provider SVG before the name (same MultiEffect
              // tint pattern as the bar slot icon).
              BorderSurface {
                id: switchButton
                required property var modelData
                required property int index

                property bool selected: index === root.providerIndex
                property bool hasCursor: root.cursorActive && index === root.providerIndex
                property bool bordered: true
                property color foreground: root.foreground
                property color accent: Color.accent
                property string fontFamily: root.fontFamily
                property real fontSize: Style.font.body
                property real iconSize: Math.max(14, Math.round(Style.space(16)))

                signal clicked()
                signal hovered(bool isHovered)

                readonly property bool hot: mouseArea.containsMouse || hasCursor
                readonly property color selectedColor: Style.selectedStateColor(foreground, accent)
                readonly property var hoverBorderSpec: Border.controlSpec("hover-cursor", foreground, accent)
                readonly property var selectedBorderSpec: Border.controlSpec("selected", foreground, accent)
                readonly property var normalBorderSpec: Border.controlSpec("normal", foreground, accent)
                readonly property real reservedTop: Math.max(Border.top(hoverBorderSpec), Border.top(selectedBorderSpec), bordered ? Border.top(normalBorderSpec) : 0)
                readonly property real reservedRight: Math.max(Border.right(hoverBorderSpec), Border.right(selectedBorderSpec), bordered ? Border.right(normalBorderSpec) : 0)
                readonly property real reservedBottom: Math.max(Border.bottom(hoverBorderSpec), Border.bottom(selectedBorderSpec), bordered ? Border.bottom(normalBorderSpec) : 0)
                readonly property real reservedLeft: Math.max(Border.left(hoverBorderSpec), Border.left(selectedBorderSpec), bordered ? Border.left(normalBorderSpec) : 0)

                leftPadding: Style.spacing.controlPaddingX
                rightPadding: Style.spacing.controlPaddingX
                topPadding: Style.spacing.controlPaddingY
                bottomPadding: Style.spacing.controlPaddingY

                implicitWidth: row.implicitWidth + leftPadding + rightPadding + reservedLeft + reservedRight
                implicitHeight: row.implicitHeight + topPadding + bottomPadding + reservedTop + reservedBottom
                radius: Style.cornerRadius

                color: mouseArea.pressed ? Style.pressedFillFor(foreground, accent)
                  : hot ? Style.hoverFillFor(foreground, accent)
                  : selected ? Style.selectedFillFor(foreground, accent)
                  : "transparent"

                borderSpec: hot ? hoverBorderSpec
                  : selected && Border.controlHasWidth("selected") ? selectedBorderSpec
                  : bordered ? normalBorderSpec
                  : Border.none()

                Behavior on color { ColorAnimation { duration: 120 } }

                onClicked: {
                  root.cursorActive = true
                  root.selectProvider(index)
                }
                onHovered: function(isHovered) { if (isHovered) root.cursorActive = true }

                Row {
                  id: row
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.horizontalCenter: parent.horizontalCenter
                  spacing: Style.spacing.controlGap

                  Item {
                    width: switchButton.iconSize
                    height: switchButton.iconSize

                    Image {
                      id: providerIcon
                      anchors.fill: parent
                      source: Qt.resolvedUrl("assets/" + modelData.id + ".svg")
                      sourceSize.width: width * 2
                      sourceSize.height: height * 2
                      fillMode: Image.PreserveAspectFit
                      asynchronous: false
                      visible: false
                      layer.enabled: true
                    }

                    MultiEffect {
                      anchors.fill: providerIcon
                      source: providerIcon
                      colorization: 1.0
                      colorizationColor: switchButton.selected ? switchButton.selectedColor : switchButton.foreground
                    }
                  }

                  Text {
                    text: modelData.name
                    color: switchButton.selected ? switchButton.selectedColor : switchButton.foreground
                    font.family: switchButton.fontFamily
                    font.pixelSize: switchButton.fontSize
                    font.bold: switchButton.selected
                    anchors.verticalCenter: parent.verticalCenter
                  }
                }

                MouseArea {
                  id: mouseArea
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  acceptedButtons: Qt.LeftButton
                  onClicked: switchButton.clicked()
                }

                HoverHandler {
                  onHoveredChanged: switchButton.hovered(hovered)
                }
              }
            }
          }

          BorderSurface {
            visible: !root.settingsOpen && !!root.provider && root.provider.error !== ""
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

          PanelSeparator {
            visible: creditsSection.visible || limitsSection.visible
            foreground: root.foreground
          }

          Column {
            id: creditsSection
            visible: !root.settingsOpen && !!root.provider && root.provider.creditsRemaining !== null && root.provider.creditsLabel !== "Extra usage"
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
            visible: !root.settingsOpen && root.limits.length > 0
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

            Item {
              visible: !!root.provider && root.provider.creditsLabel === "Extra usage" && root.provider.creditsRemaining !== null
              width: parent.width
              implicitHeight: Math.max(extraUsageLabel.implicitHeight, extraUsageValue.implicitHeight)

              Text {
                id: extraUsageLabel
                text: "Extra usage"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
              }

              Text {
                id: extraUsageValue
                text: root.creditsText(root.provider)
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
              }
            }
          }

          Text {
            visible: !root.settingsOpen && !!root.provider && root.provider.paceSummary !== ""
            width: parent.width
            text: root.provider ? root.provider.paceSummary : ""
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }

          Text {
            visible: !root.settingsOpen && !!root.provider && (root.provider.updatedAt !== "" || root.provider.source !== "")
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
            visible: !root.settingsOpen && !!root.provider && Providers.dashboardUrl(root.provider.id, root.provider) !== ""
            text: "Usage dashboard"
            bordered: true
            foreground: root.foreground
            fontFamily: root.fontFamily
            fontSize: Style.font.body
            verticalPadding: Style.spacing.controlPaddingY
            onClicked: {
              var url = Providers.dashboardUrl(root.provider.id, root.provider)
              if (url) Qt.openUrlExternally(url)
            }
          }

          Button {
            width: parent.width
            visible: !root.settingsOpen
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
    readonly property bool alarming: false

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
        text: {
          var value = Model.displayPercent(limitRow.window, Model.showRemaining(root.settings))
          return value === null ? "—" : Math.round(value) + "%"
        }
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
      }
    }

    Meter {
      width: parent.width
      value: {
        var value = Model.displayPercent(limitRow.window, Model.showRemaining(root.settings))
        return value === null ? -1 : value / 100
      }
      alarming: false
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
      color: button.foreground
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
      color: root.foreground

      Behavior on width {
        NumberAnimation { duration: 160; easing.type: Easing.OutCubic }
      }
    }
  }
}
