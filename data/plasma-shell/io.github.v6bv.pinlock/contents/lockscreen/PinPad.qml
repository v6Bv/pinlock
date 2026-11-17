// SPDX-License-Identifier: MIT
// The pinlock passkey panel: which controller button types which digit.
// Shared by the login screen overlay and the lock screen add-on, so it only
// uses plain Qt Quick.
import QtQuick

Rectangle {
    id: pad

    // Digits typed so far; -1 hides the dots (the lock screen's own password
    // box already shows them).
    property int dots: -1
    property int maxDots: 12

    readonly property var keys: [
        { digit: "1", button: "A",  tint: "#6cc04a" },
        { digit: "2", button: "B",  tint: "#e3443c" },
        { digit: "3", button: "X",  tint: "#3b8eea" },
        { digit: "4", button: "Y",  tint: "#f2c037" },
        { digit: "5", button: "LB", tint: "" },
        { digit: "6", button: "RB", tint: "" },
        { digit: "7", button: "↑",  tint: "" },
        { digit: "8", button: "→",  tint: "" },
        { digit: "9", button: "↓",  tint: "" },
        { digit: "",  button: "",   tint: "" },
        { digit: "0", button: "←",  tint: "" },
        { digit: "",  button: "",   tint: "" }
    ]

    implicitWidth: content.implicitWidth + 56
    implicitHeight: content.implicitHeight + 48
    radius: 18
    color: Qt.rgba(0.09, 0.10, 0.13, 0.92)
    border.color: Qt.rgba(1, 1, 1, 0.08)

    Column {
        id: content
        anchors.centerIn: parent
        spacing: 18

        Column {
            spacing: 4
            Text {
                text: "Enter your PIN"
                color: "#ffffff"
                font.pixelSize: 26
            }
            Text {
                text: "Using your controller"
                color: "#9aa4b2"
                font.pixelSize: 15
            }
        }

        Row {
            visible: pad.dots >= 0
            spacing: 12
            Repeater {
                model: Math.max(4, Math.min(pad.maxDots, pad.dots + 1))
                Rectangle {
                    width: 16; height: 16; radius: 8
                    color: index < pad.dots ? "#66c0f4" : "transparent"
                    border.color: "#66c0f4"
                    border.width: 2
                }
            }
        }

        Grid {
            columns: 3
            columnSpacing: 26
            rowSpacing: 10
            Repeater {
                model: pad.keys
                Item {
                    width: 72; height: 52
                    Text {
                        id: digit
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.digit
                        color: "#ffffff"
                        font.pixelSize: 40
                        font.weight: Font.Light
                    }
                    Rectangle {
                        visible: modelData.button !== ""
                        anchors.left: digit.right
                        anchors.leftMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.max(24, badge.implicitWidth + 10); height: 24
                        radius: 12
                        color: "transparent"
                        border.color: modelData.tint || "#9aa4b2"
                        border.width: 1.5
                        Text {
                            id: badge
                            anchors.centerIn: parent
                            text: modelData.button
                            color: modelData.tint || "#d0d7de"
                            font.pixelSize: 12
                            font.bold: true
                        }
                    }
                }
            }
        }

        Text {
            text: "<b>Start</b>&nbsp;&nbsp;unlock&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<b>View</b>&nbsp;&nbsp;delete"
            textFormat: Text.StyledText
            color: "#9aa4b2"
            font.pixelSize: 14
        }
    }
}
