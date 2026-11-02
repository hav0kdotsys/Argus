// Her mini player on laphvk (Capri's, in her colours): what's playing over MPRIS, previous/play/next, a seek bar,
// a menu (open the player, hide for now, turn off) and an X, on a black neon plate. Its top edge is a ledge.
import QtQuick
import Quickshell.Services.Mpris

Item {
    id: mini
    width: 360
    height: 92

    property var player: null              // the MprisPlayer to show
    property real now: 0
    signal putAway()
    signal turnOff()
    property bool menuOpen: false

    readonly property real length: player && player.lengthSupported ? player.length : 0
    property real position: 0
    Timer {
        interval: 500; running: mini.visible && mini.player; repeat: true; triggeredOnStart: true
        onTriggered: if (mini.player && mini.player.positionSupported) mini.position = mini.player.position
    }

    function clock(s) {
        s = Math.max(0, Math.floor(s))
        const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), ss = s % 60
        return (h > 0 ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(ss).padStart(2, "0")
    }

    Canvas {
        id: plate
        anchors.fill: parent
        onPaint: {
            const g = getContext("2d"), w = width, h = height, cut = 12
            g.reset()
            g.beginPath()
            g.moveTo(cut, 1); g.lineTo(w - 2, 1); g.lineTo(w - 2, h - cut); g.lineTo(w - cut, h - 2)
            g.lineTo(1, h - 2); g.lineTo(1, cut); g.closePath()
            g.fillStyle = "#0e0c12"
            g.fill()
            const edge = g.createLinearGradient(0, 0, w, h)
            edge.addColorStop(0, "#ff2a6d"); edge.addColorStop(1, "#05d9e8")
            g.strokeStyle = edge
            g.lineWidth = 2
            g.stroke()
        }
    }

    // drag it by its body; it keeps the spot
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        property point from
        onPressed: mouse => { if (mouse.button === Qt.RightButton) mini.menuOpen = !mini.menuOpen; from = Qt.point(mouse.x, mouse.y) }
        onPositionChanged: mouse => { if (pressed && mouse.buttons & Qt.LeftButton) { mini.x += mouse.x - from.x; mini.y += mouse.y - from.y } }
    }

    Text {
        x: 16 + ((Math.floor(mini.now * 4) % 97 === 0) ? 2 : 0); y: 9; width: parent.width - 96
        text: mini.player ? (mini.player.trackTitle || mini.player.identity || "") : ""
        color: "white"; font.family: "monospace"; font.bold: true; font.pixelSize: 14; elide: Text.ElideRight
    }
    Text {
        x: 16; y: 30; width: parent.width - 96
        text: mini.player ? (mini.player.trackArtist || "") : ""
        color: "#05d9e8"; font.family: "monospace"; font.pixelSize: 11; elide: Text.ElideRight
    }

    component Glyph: Text {
        signal hit()
        color: "white"; font.pixelSize: 16; font.family: "monospace"
        MouseArea { anchors.fill: parent; anchors.margins: -4; onClicked: parent.hit() }
    }
    Glyph { x: parent.width - 58; y: 6; text: "⋯"; color: "#cccccc"; onHit: mini.menuOpen = !mini.menuOpen }
    Glyph { x: parent.width - 30; y: 6; text: "✕"; color: "#cccccc"; onHit: mini.putAway() }

    Rectangle {
        id: seek
        x: 16; y: 54; width: parent.width - 32; height: 6; color: "#32323c"
        Rectangle {
            height: parent.height
            width: mini.length > 0 ? Math.max(1, parent.width * Math.min(1, mini.position / mini.length)) : 0
            gradient: Gradient { orientation: Gradient.Horizontal; GradientStop { position: 0; color: "#ff2a6d" } GradientStop { position: 1; color: "#05d9e8" } }
        }
        MouseArea {
            anchors.fill: parent; anchors.margins: -6
            function to(x) {
                if (!mini.player || !mini.player.canSeek || mini.length <= 0) return
                mini.player.position = mini.length * Math.max(0, Math.min(1, (x - 6) / seek.width))
            }
            onPressed: mouse => to(mouse.x)
            onPositionChanged: mouse => { if (pressed) to(mouse.x) }
        }
    }
    Text {
        visible: mini.length > 0
        anchors.right: parent.right; anchors.rightMargin: 16; y: 66
        text: mini.clock(mini.position) + " / " + mini.clock(mini.length)
        color: "gray"; font.family: "monospace"; font.pixelSize: 11
    }
    Glyph { x: 16; y: 64; text: "⏮"; onHit: if (mini.player && mini.player.canGoPrevious) mini.player.previous() }
    Glyph { x: 46; y: 64; text: mini.player && mini.player.isPlaying ? "⏸" : "▶"; color: "#ff2a6d"
            onHit: if (mini.player && mini.player.canTogglePlaying) mini.player.togglePlaying() }
    Glyph { x: 76; y: 64; text: "⏭"; onHit: if (mini.player && mini.player.canGoNext) mini.player.next() }

    Rectangle {
        visible: mini.menuOpen
        x: parent.width - 190; y: -86; width: 180; height: 80; color: "#0e0c12"; border.color: "#ff2a6d"; border.width: 1
        Column {
            anchors.fill: parent; anchors.margins: 6; spacing: 2
            Repeater {
                model: [
                    { label: "Open " + (mini.player ? mini.player.identity : "the player"), act: () => { if (mini.player && mini.player.canRaise) mini.player.raise() } },
                    { label: "Hide for now", act: () => mini.putAway() },
                    { label: "Turn off mini player", act: () => mini.turnOff() },
                ]
                delegate: Text {
                    required property var modelData
                    text: modelData.label; color: "white"; font.family: "monospace"; font.pixelSize: 12
                    width: 168; height: 22; elide: Text.ElideRight
                    MouseArea { anchors.fill: parent; onClicked: { mini.menuOpen = false; parent.modelData.act() } }
                }
            }
        }
    }
}
