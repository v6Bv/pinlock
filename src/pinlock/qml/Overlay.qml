// SPDX-License-Identifier: MIT
// Login screen overlay: the passkey panel pinned to the bottom-left corner as
// a layer-shell surface. It never takes keyboard focus or mouse input, so the
// greeter's password box keeps receiving what pinlockd types.
import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell

Window {
    id: win

    readonly property int margin: 48

    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowTransparentForInput
    width: (pad.item ? pad.item.implicitWidth : 360) + margin
    height: (pad.item ? pad.item.implicitHeight : 480) + margin
    visible: controller.shown

    LayerShell.Window.anchors: LayerShell.Window.AnchorBottom | LayerShell.Window.AnchorLeft
    LayerShell.Window.layer: LayerShell.Window.LayerOverlay
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.activateOnShow: false
    LayerShell.Window.scope: "pinlock"

    Loader {
        id: pad
        x: win.margin
        y: 0
        source: pinpadUrl
        opacity: controller.shown ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }

    Binding {
        target: pad.item
        property: "dots"
        value: controller.dots
        when: pad.item !== null
    }
}
