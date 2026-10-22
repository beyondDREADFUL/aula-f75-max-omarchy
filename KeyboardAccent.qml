import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Bar swatch for the keyboard accent colour. The dot shows what the keyboard
// is set to: filled when it matches the theme, ringed when a custom colour is
// set. Left-click opens the picker, right-click returns to the theme colour.
//
// All keyboard access goes through bin/keyboard-accent, which prints one line
// of JSON per command. Commands run one at a time from a queue.
Panel {
  id: root

  moduleName: "beyond.keyboard-accent"
  ipcTarget: moduleName
  manageIpc: false

  // From the helper's status command.
  property string themeHex: ""
  property string keyboardHex: ""
  property bool matches: false
  property bool pinned: false        // a pinned colour overrides the theme

  // Picker state.
  property bool keep: false           // pin the colour across theme changes
  property bool pickTheme: false      // Apply returns to the theme colour
  property var previews: ({})         // typed hex -> colour the keys will show
  property string previewHex: ""      // same, for the hex field
  property string message: ""
  property bool failed: false

  readonly property string helperPath: String(Qt.resolvedUrl("bin/keyboard-accent")).replace(/^file:\/\//, "")
  readonly property var presets: ["#FF0000", "#FF8000", "#FFD000", "#00C853", "#00A0FF", "#8839EF", "#FF2D95"]
  readonly property color fg: bar ? bar.foreground : "#cacccc"
  readonly property color bg: bar ? bar.background : "#101315"
  readonly property color dim: Qt.darker(fg, 1.4)
  readonly property string family: bar ? bar.fontFamily : "monospace"
  readonly property string tooltipText: keyboardHex === ""
    ? "Keyboard accent: no colour applied yet"
    : "Keyboard " + keyboardHex + (pinned ? " · pinned (theme " + themeHex + ")" : matches ? " · matches theme" : " · custom (theme " + themeHex + ")")

  // The message line keeps a fixed height so the popup never resizes while
  // it comes and goes.
  FontMetrics {
    id: lineMetrics
    font.family: root.family
    font.pixelSize: Style.font.caption
  }

  implicitWidth: bar ? bar.barSize : 26
  implicitHeight: bar ? bar.barSize : 26

  // ---- helpers ------------------------------------------------------------

  function normalize(text) {
    var value = String(text || "").trim().replace(/^#/, "")
    return /^[0-9a-fA-F]{6}$/.test(value) ? "#" + value.toUpperCase() : ""
  }

  // Readable label colour for text drawn on a swatch.
  function textOn(hex) {
    var value = String(hex || "").replace("#", "")
    if (value.length !== 6) return root.fg
    var r = parseInt(value.substr(0, 2), 16)
    var g = parseInt(value.substr(2, 2), 16)
    var b = parseInt(value.substr(4, 2), 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? "#101315" : "#FFFFFF"
  }

  function shown(hex) {
    return root.previews[hex] || hex
  }

  // ---- command queue ------------------------------------------------------
  // One helper process at a time. A queued entry with the same key as a new
  // one is replaced, so rapid typing only previews the latest value.

  property var queue: []

  function enqueue(args, key, handler) {
    var pending = root.queue.filter(function(item) { return key === "" || item.key !== key })
    pending.push({ args: args, key: key, handler: handler })
    root.queue = pending
    root.pump()
  }

  function pump() {
    if (helperProcess.running || root.queue.length === 0) return
    var next = root.queue[0]
    root.queue = root.queue.slice(1)
    helperProcess.handler = next.handler
    helperProcess.command = [root.helperPath].concat(next.args)
    helperProcess.running = true
  }

  function parse(text) {
    try {
      return JSON.parse(text)
    } catch (error) {
      return { ok: false, error: "unexpected helper output" }
    }
  }

  Process {
    id: helperProcess
    property var handler: null
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var handler = helperProcess.handler
        if (handler) handler(root.parse(text.trim()))
      }
    }
    onRunningChanged: {
      if (!running) Qt.callLater(root.pump)
    }
  }

  // ---- actions ------------------------------------------------------------

  // Colours picked here are applied as written, without the theme's
  // saturation and lightness limits.
  function exactArgs() {
    return ["--exact"]
  }

  function report(result, success) {
    root.failed = !result.ok
    root.message = result.ok ? success : (result.error || "failed")
  }

  function refresh() {
    root.enqueue(["status"], "status", function(result) {
      if (!result.ok) {
        root.report(result, "")
        return
      }
      root.themeHex = String(result.theme).toUpperCase()
      root.keyboardHex = String(result.keyboard || "").toUpperCase()
      root.matches = result.matches === true
      root.pinned = result.pinned === true
      root.keep = root.pinned
    })
  }

  function loadPreviews() {
    var args = ["targets"].concat(root.exactArgs(), root.presets)
    root.enqueue(args, "targets", function(result) {
      if (!result.ok) return
      var map = {}
      Object.keys(result.map || {}).forEach(function(key) {
        map[key.toUpperCase()] = String(result.map[key]).toUpperCase()
      })
      root.previews = map
    })
  }

  function requestPreview(text) {
    var hex = root.normalize(text)
    if (hex === "") {
      root.previewHex = ""
      return
    }
    root.enqueue(["preview"].concat(root.exactArgs(), [hex]), "preview", function(result) {
      root.previewHex = result.ok ? String(result.keyboard).toUpperCase() : ""
    })
  }

  function setColour(hex) {
    root.message = "Applying " + hex + "…"
    root.failed = false
    root.enqueue(["apply"].concat(root.exactArgs(), root.keep ? ["--pin"] : [], [hex]), "", function(result) {
      root.report(result, "Applied " + hex)
      Qt.callLater(root.refresh)
    })
  }

  function resetToTheme() {
    root.message = "Returning to the theme colour…"
    root.failed = false
    root.enqueue(["reset"], "", function(result) {
      root.report(result, "Back on the theme colour")
      root.previewHex = ""
      Qt.callLater(root.refresh)
    })
  }

  function applyFromInput() {
    if (root.pickTheme) {
      root.resetToTheme()
      return
    }
    var hex = root.normalize(hexInput.text)
    if (hex === "") {
      root.failed = true
      root.message = "Enter a 6-digit hex colour"
      return
    }
    root.setColour(hex)
  }

  onOpenedChanged: {
    if (!opened) return
    root.refresh()
    root.loadPreviews()
    hexInput.text = root.keyboardHex.replace("#", "")
    root.pickTheme = false
    root.previewHex = ""
    root.message = ""
  }

  Component.onCompleted: Qt.callLater(root.refresh)

  // The theme change is the event that moves the keyboard colour. The hook
  // applies it a moment later, so wait for that before reading state back.
  Connections {
    target: Commons.Color

    function onAccentChanged() {
      settleTimer.restart()
    }
  }

  Timer {
    id: settleTimer
    interval: 2500
    onTriggered: root.refresh()
  }

  IpcHandler {
    target: root.moduleName

    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh() }
    function reset(): void { root.resetToTheme() }
  }

  // ---- bar swatch ---------------------------------------------------------

  Rectangle {
    id: pill
    anchors.centerIn: parent
    width: Style.space(12)
    height: width
    radius: width / 2
    color: root.keyboardHex !== "" ? root.keyboardHex : "transparent"
    border.width: Math.max(1, Style.space(2))
    border.color: root.keyboardHex === "" ? root.dim : (root.matches ? "transparent" : root.fg)
  }

  MouseArea {
    anchors.fill: parent
    acceptedButtons: Qt.LeftButton | Qt.RightButton
    hoverEnabled: true
    onClicked: function(mouse) {
      if (mouse.button === Qt.RightButton) root.resetToTheme()
      else root.toggle()
    }
    onEntered: if (root.bar) root.bar.showTooltip(root, root.tooltipText)
    onExited: if (root.bar) root.bar.hideTooltip(root)
  }

  // ---- picker -------------------------------------------------------------

  KeyboardPanel {
    id: panel
    anchorItem: pill
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(320))
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight, Style.space(640))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()

      Column {
        id: panelColumn
        width: parent.width
        spacing: Style.space(14)

        // Title and match state.
        Item {
          width: parent.width
          implicitHeight: titleText.implicitHeight

          Text {
            id: titleText
            text: "Keyboard Accent"
            color: root.fg
            font.family: root.family
            font.pixelSize: Style.font.title
            font.bold: true
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            text: root.keyboardHex === "" ? "NOT SET" : (root.pinned ? "PINNED" : root.matches ? "MATCHES THEME" : "CUSTOM")
            color: root.dim
            font.family: root.family
            font.pixelSize: Style.font.caption
            font.bold: true
            font.letterSpacing: 1.2
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
          }
        }

        // Keyboard and theme side by side. Clicking the theme returns to it.
        Row {
          width: parent.width
          spacing: Style.space(8)

          Repeater {
            model: [
              { label: "KEYBOARD", hex: root.keyboardHex, theme: false },
              { label: "THEME", hex: root.themeHex, theme: true }
            ]

            Rectangle {
              required property var modelData
              width: (panelColumn.width - Style.space(8)) / 2
              height: Style.space(56)
              radius: Style.space(6)
              color: modelData.hex !== "" ? modelData.hex : "transparent"
              border.width: modelData.theme && root.pickTheme ? Style.space(2) : Math.max(1, Style.space(1))
              border.color: modelData.theme && root.pickTheme ? root.fg : Qt.darker(root.fg, 1.8)

              Column {
                anchors.centerIn: parent
                spacing: Style.space(2)

                Text {
                  anchors.horizontalCenter: parent.horizontalCenter
                  text: modelData.label
                  color: root.textOn(modelData.hex)
                  font.family: root.family
                  font.pixelSize: Style.font.caption
                  font.bold: true
                  font.letterSpacing: 1.2
                }

                Text {
                  anchors.horizontalCenter: parent.horizontalCenter
                  text: modelData.hex !== "" ? modelData.hex : "—"
                  color: root.textOn(modelData.hex)
                  font.family: root.family
                  font.pixelSize: Style.font.caption
                }
              }

              MouseArea {
                anchors.fill: parent
                enabled: modelData.theme
                onClicked: {
                  root.pickTheme = true
                  hexInput.text = ""
                  root.previewHex = ""
                  root.failed = false
                  root.message = "Press Apply to use the theme colour"
                }
              }
            }
          }
        }

        PanelSeparator {
          foreground: root.fg
        }

        // Presets, drawn in the colour the keys will really show.
        PanelSectionHeader {
          text: "PRESETS"
          foreground: root.fg
          fontFamily: root.family
        }

        Flow {
          width: parent.width
          spacing: Style.space(8)

          Repeater {
            model: root.presets

            Rectangle {
              required property string modelData
              width: Style.space(28)
              height: width
              radius: width / 2
              color: root.shown(modelData)
              readonly property bool picked: !root.pickTheme && root.normalize(hexInput.text) === modelData
              border.width: picked ? Style.space(2) : Math.max(1, Style.space(1))
              border.color: picked ? root.fg : Qt.darker(root.fg, 2.0)

              MouseArea {
                anchors.fill: parent
                onClicked: {
                  root.pickTheme = false
                  hexInput.text = modelData.replace("#", "")
                  root.requestPreview(hexInput.text)
                  root.message = "Press Apply to set " + modelData
                  root.failed = false
                }
              }
            }
          }
        }

        // Free hex entry with a live preview of the result.
        PanelSectionHeader {
          text: "CUSTOM"
          foreground: root.fg
          fontFamily: root.family
        }

        Rectangle {
          width: parent.width
          height: Style.space(32)
          radius: Style.space(4)
          color: "transparent"
          border.width: Math.max(1, Style.space(1))
          border.color: Qt.darker(root.fg, 1.8)

          TextInput {
            id: hexInput
            anchors.fill: parent
            anchors.leftMargin: Style.space(10)
            anchors.rightMargin: Style.space(10) + previewDot.width
            verticalAlignment: TextInput.AlignVCenter
            maximumLength: 7
            color: root.fg
            selectionColor: root.fg
            selectedTextColor: root.bg
            font.family: root.family
            font.pixelSize: Style.font.caption
            onTextEdited: {
              root.pickTheme = false
              root.requestPreview(text)
            }
            Keys.onReturnPressed: root.applyFromInput()
            Keys.onEnterPressed: root.applyFromInput()
          }

          Text {
            anchors.left: parent.left
            anchors.leftMargin: Style.space(10)
            anchors.verticalCenter: parent.verticalCenter
            visible: hexInput.text === ""
            text: "#RRGGBB"
            color: Qt.darker(root.fg, 1.8)
            font.family: root.family
            font.pixelSize: Style.font.caption
          }

          Rectangle {
            id: previewDot
            anchors.right: parent.right
            anchors.rightMargin: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(16)
            height: width
            radius: width / 2
            visible: root.previewHex !== ""
            color: root.previewHex !== "" ? root.previewHex : "transparent"
            border.width: Math.max(1, Style.space(1))
            border.color: Qt.darker(root.fg, 1.8)
          }
        }

        // Keep-colour switch.
        Item {
          width: parent.width
          implicitHeight: Math.max(keepLabels.implicitHeight, keepSwitch.height)

          Column {
            id: keepLabels
            anchors.left: parent.left
            anchors.right: keepSwitch.left
            anchors.rightMargin: Style.space(10)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              width: parent.width
              text: "Keep this colour"
              color: root.fg
              font.family: root.family
              font.pixelSize: Style.font.caption
              font.bold: true
            }

            Text {
              width: parent.width
              text: "Stay on it through theme changes and reconnects, until you reset"
              wrapMode: Text.WordWrap
              color: root.dim
              font.family: root.family
              font.pixelSize: Style.font.caption
            }
          }

          Rectangle {
            id: keepSwitch
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(36)
            height: Style.space(20)
            radius: height / 2
            color: root.keep ? root.fg : "transparent"
            border.width: Math.max(1, Style.space(1))
            border.color: root.fg

            Rectangle {
              width: parent.height - Style.space(6)
              height: width
              radius: width / 2
              anchors.verticalCenter: parent.verticalCenter
              x: root.keep ? parent.width - width - Style.space(3) : Style.space(3)
              color: root.keep ? root.bg : root.fg
            }

            MouseArea {
              anchors.fill: parent
              onClicked: root.keep = !root.keep
            }
          }
        }

        Row {
          width: parent.width
          spacing: Style.space(8)

          Rectangle {
            width: (parent.width - Style.space(8)) / 2
            height: Style.space(32)
            radius: Style.space(4)
            color: root.fg

            Text {
              anchors.centerIn: parent
              text: "Apply"
              color: root.bg
              font.family: root.family
              font.pixelSize: Style.font.caption
              font.bold: true
            }

            MouseArea {
              anchors.fill: parent
              onClicked: root.applyFromInput()
            }
          }

          Rectangle {
            width: (parent.width - Style.space(8)) / 2
            height: Style.space(32)
            radius: Style.space(4)
            color: "transparent"
            border.width: Math.max(1, Style.space(1))
            border.color: root.fg

            Text {
              anchors.centerIn: parent
              text: "Reset to theme"
              color: root.fg
              font.family: root.family
              font.pixelSize: Style.font.caption
              font.bold: true
            }

            MouseArea {
              anchors.fill: parent
              onClicked: root.resetToTheme()
            }
          }
        }

        Text {
          width: parent.width
          height: lineMetrics.height
          text: root.message === "" ? " " : root.message
          maximumLineCount: 1
          elide: Text.ElideRight
          color: root.failed ? "#E5484D" : root.dim
          font.family: root.family
          font.pixelSize: Style.font.caption
        }
      }
    }
  }
}
