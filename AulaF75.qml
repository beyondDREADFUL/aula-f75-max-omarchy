import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Bar widget for the AULA F75 Max: the keyboard's colour, brightness, effect and music.
// The bar shows a fixed keyboard icon in the bar's colour; left-click opens the panel, right-click
// returns the keyboard to the theme colour.
//
// Every choice applies at once, except the hex field, which waits for Apply. All
// keyboard access goes through bin/aula-f75, which prints one line of JSON per
// command; commands run one at a time from a queue.
Panel {
  id: root

  moduleName: "beyond.aula-f75"
  ipcTarget: moduleName
  manageIpc: false

  // From the helper's status command.
  property string themeHex: ""
  property string keyboardHex: ""
  property bool matches: false
  property bool pinned: false
  property int brightness: 5
  property string effect: "static"
  property int speed: 3
  property string transition: "wave"  // how the keys change colour over the cable
  property var devices: []
  property bool musicOn: false
  property int battery: -1           // percent over 2.4 GHz, -1 when unknown

  // Panel state.
  property var palette: []           // [{source, target}] from the theme
  property string previewHex: ""      // what the keys would show for the hex field
  property string musicBackground: "off"
  property bool effectsOpen: false    // the effect list is folded out
  property string message: ""
  property bool failed: false

  readonly property string helperPath: String(Qt.resolvedUrl("bin/aula-f75")).replace(/^file:\/\//, "")
  readonly property var brights: ["#FF0000", "#FF8000", "#FFD000", "#00C853", "#00A0FF", "#8839EF", "#FF2D95"]
  readonly property var effects: ["static", "breath", "pulsating", "glittering", "falling",
    "single-on", "single-off", "ripples", "outward", "explode", "launch", "scrolling", "rolling",
    "rotating", "flowing", "tilt", "shuttle", "colourful", "spectrum"]
  readonly property bool wired: devices.indexOf("wired") >= 0
  readonly property bool wireless: devices.indexOf("wireless") >= 0
  readonly property color fg: bar ? bar.foreground : "#cacccc"
  readonly property color bg: bar ? bar.background : "#101315"
  readonly property color dim: Qt.darker(fg, 1.4)
  readonly property string family: bar ? bar.fontFamily : "monospace"
  readonly property string connection: wired ? "CABLE" : wireless ? "2.4G" : "NOT CONNECTED"
  readonly property string tooltipText: devices.length === 0
    ? "Keyboard not connected"
    : "Keyboard " + (keyboardHex || "—") + " · " + effect + " · " + brightness + "/5 · "
      + (wired ? "cable" : "2.4G") + (musicOn ? " · music on" : "") + (pinned ? " · pinned" : "")

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  // The status line keeps a fixed height so the panel never resizes while it changes.
  FontMetrics {
    id: lineMetrics
    font.family: root.family
    font.pixelSize: Style.font.caption
  }

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

  // ---- command queue ------------------------------------------------------
  // One helper process at a time. A queued entry with the same key as a new one is
  // replaced, so rapid clicks (brightness, speed, typing) only send the latest value.

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

  function report(result, success) {
    root.failed = !result.ok
    root.message = result.ok ? success : (result.error || "failed")
  }

  // Run a helper command that changes the keyboard, report it, then re-read state.
  function act(args, key, busy, done) {
    root.message = busy
    root.failed = false
    root.enqueue(args, key, function(result) {
      root.report(result, done)
      Qt.callLater(root.refresh)
    })
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
      root.brightness = Math.max(1, Math.min(5, Number(result.brightness) || 5))
      root.effect = String(result.effect || "static")
      root.speed = Number(result.speed)
      root.transition = String(result.transition || "wave")
      root.devices = result.devices || []
      root.musicOn = result.music === true
      if (root.musicOn && result.musicBackground) root.musicBackground = String(result.musicBackground)
    })
  }

  function loadPalette() {
    root.enqueue(["palette"], "palette", function(result) {
      if (result.ok) root.palette = result.colors || []
    })
  }

  function loadBattery() {
    root.battery = -1
    if (root.wired || !root.wireless) return
    root.enqueue(["battery"], "battery", function(result) {
      root.battery = result.ok ? Number(result.percent) : -1
    })
  }

  function requestPreview(text) {
    var hex = root.normalize(text)
    if (hex === "") {
      root.previewHex = ""
      return
    }
    root.enqueue(["preview", "--exact", hex], "preview", function(result) {
      root.previewHex = result.ok ? String(result.keyboard).toUpperCase() : ""
    })
  }

  // Colours are sent as shown: swatches already show what the keys get. While a colour
  // is pinned, a new one replaces the pin.
  function setColour(hex) {
    root.act(["apply", "--exact"].concat(root.pinned ? ["--pin"] : [], [hex]), "colour",
             "Applying " + hex + "…", "Applied " + hex)
  }

  function applyHex() {
    var hex = root.normalize(hexInput.text)
    if (hex === "") {
      root.failed = true
      root.message = "Enter a 6-digit hex colour"
      return
    }
    root.setColour(hex)
  }

  function resetToTheme() {
    root.previewHex = ""
    root.act(["reset"], "colour", "Returning to the theme colour…", "Back on the theme colour")
  }

  // Keep shows whether the colour is pinned: on pins the colour the keys have now, off
  // releases it so the next theme change sets the theme colour.
  function setKeep(on) {
    if (root.keyboardHex === "") return
    root.pinned = on
    root.act(["apply", "--exact"].concat(on ? ["--pin"] : [], [root.keyboardHex]), "colour",
             on ? "Pinning " + root.keyboardHex + "…" : "Unpinning…",
             on ? "Pinned " + root.keyboardHex : "Unpinned: the next theme change sets the theme colour")
  }

  function setBrightness(level) {
    level = Math.max(1, Math.min(5, level))
    root.brightness = level
    root.act(["brightness", String(level)], "brightness", "Brightness " + level + "…",
             "Brightness " + level)
  }

  function setEffect(name, speed) {
    root.effect = name
    root.speed = speed
    root.act(["effect", name, String(speed)], "effect", "Switching to " + name + "…",
             "Effect: " + name)
  }

  // Saved for the next colour change; nothing changes on the keys now.
  function setTransition(style) {
    root.transition = style
    root.act(["transition", style], "transition", "Transition: " + style + "…",
             style === "none" ? "Colours change at once" : "Colours change with a " + style)
  }

  function setMusic(on) {
    root.act(on ? ["music", "start", root.musicBackground] : ["music", "stop"], "music",
             on ? "Starting the music visualiser…" : "Stopping the music visualiser…",
             on ? "Music on: bars follow the sound" : "Music off, back on the theme colour")
  }

  onOpenedChanged: {
    if (!opened) return
    root.refresh()
    root.loadPalette()
    Qt.callLater(root.loadBattery)
    hexInput.text = ""
    root.previewHex = ""
    root.message = ""
    root.effectsOpen = false
  }

  Component.onCompleted: Qt.callLater(root.refresh)

  // The theme change moves the keyboard colour. The hook applies it a moment later,
  // so wait for that before reading state back.
  Connections {
    target: Commons.Color

    function onAccentChanged() {
      settleTimer.restart()
    }
  }

  Timer {
    id: settleTimer
    interval: 2500
    onTriggered: {
      root.refresh()
      if (root.opened) root.loadPalette()
    }
  }

  IpcHandler {
    target: root.moduleName

    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): void { root.refresh() }
    function reset(): void { root.resetToTheme() }
    function music(): void { root.setMusic(!root.musicOn) }
    function brightness(level: int): void { root.setBrightness(level) }
    function brighter(): void { root.setBrightness(root.brightness + 1) }
    function dimmer(): void { root.setBrightness(root.brightness - 1) }
  }

  // ---- bar icon -------------------------------------------------------------

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰧹"
    useActiveColor: false
    tooltipText: root.tooltipText
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.RightButton) root.resetToTheme()
      else root.toggle()
    }
  }

  // ---- panel ----------------------------------------------------------------

  // Swatch row: theme palette or bright presets.
  component SwatchRow: Flow {
    id: row
    property var colors: []           // hex strings
    width: parent ? parent.width : 0
    spacing: Style.space(8)

    Repeater {
      model: row.colors

      Rectangle {
        required property string modelData
        width: Style.space(26)
        height: width
        radius: width / 2
        color: modelData
        readonly property bool current: root.normalize(modelData) === root.keyboardHex
        border.width: current ? Style.space(2) : Math.max(1, Style.space(1))
        border.color: current ? root.fg : Qt.darker(root.fg, 2.0)

        MouseArea {
          anchors.fill: parent
          cursorShape: Qt.PointingHandCursor
          onClicked: root.setColour(root.normalize(modelData))
        }
      }
    }
  }

  // A labelled row: caption on the left, control on the right.
  component LabelledRow: Item {
    id: lrow
    property string label: ""
    default property alias content: slot.data
    width: parent ? parent.width : 0
    implicitHeight: Math.max(caption.implicitHeight, slot.childrenRect.height)

    Text {
      id: caption
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      text: lrow.label
      color: root.fg
      font.family: root.family
      font.pixelSize: Style.font.caption
    }

    Item {
      id: slot
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      width: childrenRect.width
      height: childrenRect.height
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(320))
    // no cap: the panel grows with its content, up to the screen's height
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()

      Column {
        id: panelColumn
        width: parent.width
        spacing: Style.space(10)

        // Title and connection.
        Item {
          width: parent.width
          implicitHeight: titleText.implicitHeight

          Text {
            id: titleText
            text: "AULA F75 Max"
            color: root.fg
            font.family: root.family
            font.pixelSize: Style.font.title
            font.bold: true
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            text: root.connection + (root.battery >= 0 ? " · " + root.battery + "%" : "")
            color: root.dim
            font.family: root.family
            font.pixelSize: Style.font.caption
            font.bold: true
            font.letterSpacing: 1.2
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
          }
        }

        // Keyboard and theme side by side, for reading only.
        Row {
          width: parent.width
          spacing: Style.space(8)

          Repeater {
            model: [
              { label: root.pinned ? "KEYBOARD · PINNED" : root.matches ? "KEYBOARD" : "KEYBOARD · CUSTOM",
                hex: root.keyboardHex },
              { label: "THEME", hex: root.themeHex }
            ]

            Rectangle {
              required property var modelData
              width: (panelColumn.width - Style.space(8)) / 2
              height: Style.space(42)
              radius: Style.space(6)
              color: modelData.hex !== "" ? modelData.hex : "transparent"
              border.width: Math.max(1, Style.space(1))
              border.color: Qt.darker(root.fg, 1.8)

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
            }
          }
        }

        PanelSeparator { foreground: root.fg }

        // ---- colour ----
        PanelSectionHeader {
          text: "COLOUR"
          foreground: root.fg
          fontFamily: root.family
        }

        SwatchRow {
          visible: root.palette.length > 0
          colors: root.palette.map(function(c) { return c.target })
        }

        SwatchRow {
          colors: root.brights
        }

        Row {
          width: parent.width
          spacing: Style.space(8)

          Rectangle {
            width: parent.width - applyButton.width - Style.space(8)
            height: Style.space(30)
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
              onTextEdited: root.requestPreview(text)
              Keys.onReturnPressed: root.applyHex()
              Keys.onEnterPressed: root.applyHex()
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
              width: Style.space(14)
              height: width
              radius: width / 2
              visible: root.previewHex !== ""
              color: root.previewHex !== "" ? root.previewHex : "transparent"
              border.width: Math.max(1, Style.space(1))
              border.color: Qt.darker(root.fg, 1.8)
            }
          }

          Button {
            id: applyButton
            text: "Apply"
            bordered: true
            foreground: root.fg
            fontFamily: root.family
            fontSize: Style.font.caption
            onClicked: root.applyHex()
          }
        }

        LabelledRow {
          label: "Keep this colour through theme changes"
          ToggleSwitch {
            checked: root.pinned
            foreground: root.fg
            onToggled: root.setKeep(!root.pinned)
          }
        }

        Button {
          width: parent.width
          text: "Reset to theme"
          bordered: true
          foreground: root.fg
          fontFamily: root.family
          fontSize: Style.font.caption
          onClicked: root.resetToTheme()
        }

        PanelSeparator { foreground: root.fg }

        // ---- light ----
        PanelSectionHeader {
          text: "LIGHT"
          foreground: root.fg
          fontFamily: root.family
        }

        LabelledRow {
          label: "Brightness"
          ButtonGroup {
            options: ["1", "2", "3", "4", "5"]
            value: String(root.brightness)
            foreground: root.fg
            fontFamily: root.family
            fontSize: Style.font.caption
            onChanged: function(value) { root.setBrightness(Number(value)) }
          }
        }

        // The effect list folds out inside the panel: a popup would be cut off at the
        // panel's edge.
        LabelledRow {
          label: "Effect"
          Button {
            text: root.effect + (root.effectsOpen ? "  ▴" : "  ▾")
            bordered: true
            foreground: root.fg
            fontFamily: root.family
            fontSize: Style.font.caption
            onClicked: root.effectsOpen = !root.effectsOpen
          }
        }

        Flow {
          visible: root.effectsOpen
          width: parent.width
          spacing: Style.space(6)

          Repeater {
            model: root.effects

            Button {
              required property string modelData
              text: modelData
              selected: modelData === root.effect
              bordered: true
              foreground: root.fg
              fontFamily: root.family
              fontSize: Style.font.caption
              onClicked: {
                root.effectsOpen = false
                if (modelData !== root.effect) root.setEffect(modelData, root.speed)
              }
            }
          }
        }

        Column {
          visible: root.effect !== "static"
          width: parent.width
          spacing: Style.space(4)

          Text {
            text: "Speed"
            color: root.fg
            font.family: root.family
            font.pixelSize: Style.font.caption
          }

          PanelSlider {
            width: parent.width
            bar: root.bar
            minimum: 0
            maximum: 5
            step: 1
            integer: true
            tickCount: 6
            value: root.speed
            onReleased: function(value) { root.setEffect(root.effect, Math.round(value)) }
          }
        }

        LabelledRow {
          label: "Transition"
          ButtonGroup {
            options: [{ value: "none", label: "None" }, { value: "fade", label: "Fade" },
                      { value: "wave", label: "Wave" }, { value: "explode", label: "Burst" }]
            value: root.transition
            foreground: root.fg
            fontFamily: root.family
            fontSize: Style.font.caption
            onChanged: function(value) { root.setTransition(value) }
          }
        }

        PanelSeparator { foreground: root.fg }

        // ---- music ----
        PanelSectionHeader {
          text: "MUSIC"
          foreground: root.fg
          fontFamily: root.family
        }

        LabelledRow {
          label: root.wired || root.musicOn ? "Music visualiser" : "Music visualiser · connect the USB cable"
          ToggleSwitch {
            checked: root.musicOn
            interactive: root.wired || root.musicOn
            foreground: root.fg
            onToggled: root.setMusic(!root.musicOn)
          }
        }

        LabelledRow {
          label: "Behind the bars"
          ButtonGroup {
            options: [{ value: "off", label: "Dark" }, { value: "theme", label: "Theme" }]
            value: root.musicBackground
            foreground: root.fg
            fontFamily: root.family
            fontSize: Style.font.caption
            onChanged: function(value) {
              root.musicBackground = value
              if (root.musicOn) root.setMusic(true)
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
