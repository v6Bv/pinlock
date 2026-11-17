// SPDX-License-Identifier: MIT
// pinlock lock screen: Plasma's own lock screen, unchanged, with the pinlock
// passkey panel in the bottom-left corner.
//
// `pinlock lockscreen enable` points KWin (and only KWin) at this shell package
// via PLASMA_DEFAULT_SHELL, which the lock screen reads. Everything else is taken
// straight from the installed Plasma shell, so Plasma updates keep working.
import QtQuick
import "file:///usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen"

Item {
    id: root

    // The same properties and signals kscreenlocker expects on Plasma's own
    // root item; Plasma's LockScreenUi reaches them through `root`.
    property bool debug: false
    property string notification
    signal clearPassword()
    signal notificationRepeated()
    property bool viewVisible: false

    LayoutMirroring.enabled: Application.layoutDirection === Qt.RightToLeft
    LayoutMirroring.childrenInherit: true

    implicitWidth: 800
    implicitHeight: 600

    LockScreenUi {
        id: ui
        anchors.fill: parent
    }

    // Follow the lock screen's own show/hide of its UI, if we can find it.
    property QtObject uiState: null
    readonly property bool uiShown: uiState ? uiState.uiVisible : true

    function findUiState(item, depth) {
        if (!item || depth < 0)
            return null
        if (item.uiVisible !== undefined)
            return item
        for (let i = 0; i < item.children.length; i++) {
            const found = findUiState(item.children[i], depth - 1)
            if (found)
                return found
        }
        return null
    }

    Component.onCompleted: uiState = findUiState(ui, 4)

    PinPad {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 48
        opacity: root.uiShown ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 250 } }
    }
}
