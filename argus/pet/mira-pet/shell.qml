// Mira's body on laphvk: a small layer-shell overlay that plays her sprite sheets (~/.argus/sprites/mira, see its
// NOTICE.md and clips.json). Run with `quickshell -c mira-pet`; it is its own Quickshell config, apart from Caelestia,
// so starting or stopping her never restarts the shell (or its lock screen).
//
// She sits bottom-LEFT on purpose: laphvk's right edge (x = 1919) is Lan Mouse's capture strip back to winhvk, and any
// surface over it breaks the crossing (JarvisInfrastructure ops/lan-mouse/README.md).
//
// What she says shows in a bubble over her head. Anything can make her talk by writing
// ~/.argus/companion/say.json: {"text": "...", "id": "<unique per line>"} - the companion's check-ins will, and so can
// a shell: `printf '{"id":"%s","text":"%s"}' "$(date +%s%N)" "Hi" > ~/.argus/companion/say.json`.
// Only her sprite takes clicks (a click: a grin, or dismisses the bubble); the bubble lets them through.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
    id: root

    readonly property string home: Quickshell.env("HOME")
    readonly property string sprites: home + "/.argus/sprites/mira/"
    readonly property real scale: 0.5          // 240x384 cells at half size
    readonly property int cellWidth: 240
    readonly property int cellHeight: 384
    readonly property int spriteWidth: cellWidth * scale
    readonly property int spriteHeight: cellHeight * scale
    readonly property int bubbleWidth: 300
    property string clip: "idle"
    property string said: ""
    property string lastId: ""

    readonly property var clips: ({
        "idle": { frames: 16, fps: 8, loop: true },
        "blink": { frames: 4, fps: 8, loop: false },
        "grin": { frames: 16, fps: 8, loop: false },
        "glitch": { frames: 10, fps: 15, loop: false }
    })

    function play(name) {
        root.clip = name
        sprite.restart()
    }

    function say(text) {
        root.said = text
        root.play("glitch")
        // About 0.06 s a character, at least 5 s and at most 20 s.
        hold.interval = Math.max(5000, Math.min(20000, text.length * 60))
        hold.restart()
    }

    FileView {
        id: speech
        path: root.home + "/.argus/companion/say.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            let line
            try { line = JSON.parse(speech.text()) } catch (e) { return }
            const text = String(line.text || "").trim()
            const id = String(line.id || text)
            if (text && id !== root.lastId) {
                root.lastId = id
                root.say(text.slice(0, 400))
            }
        }
    }

    // The watch only follows the file that existed when it started: a writer that replaces the file atomically (or
    // creates it after she started) leaves it blind, so she also re-reads it every 1.5 s. A seen id is never repeated.
    Timer { interval: 1500; running: true; repeat: true; onTriggered: speech.reload() }

    Timer { id: hold; onTriggered: root.said = "" }

    // How long Hannah's been away from the keyboard and mouse, for the companion's check-in ticker:
    // ~/.argus/companion/state.json holds {"idle_since": <unix seconds> | null}. Wayland only says "idle for at
    // least `timeout` seconds", so the start is backdated by the timeout.
    IdleMonitor {
        id: idle
        timeout: 60
        respectInhibitors: true
        onIsIdleChanged: state.setText(JSON.stringify({
            idle_since: idle.isIdle ? Math.floor(Date.now() / 1000) - idle.timeout : null }))
    }

    FileView {
        id: state
        path: root.home + "/.argus/companion/state.json"
        Component.onCompleted: state.setText(JSON.stringify({ idle_since: null }))
    }

    PanelWindow {
        id: body
        anchors { bottom: true; left: true }
        margins { left: 76; bottom: 8 }   // clear of Caelestia's left bar
        implicitWidth: root.bubbleWidth
        implicitHeight: root.spriteHeight + bubble.height + 8
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        mask: Region { item: sprite }
        WlrLayershell.layer: WlrLayer.Top
        WlrLayershell.namespace: "mira-pet"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

        Rectangle {
            id: bubble
            visible: root.said !== ""
            anchors { left: parent.left; bottom: sprite.top; bottomMargin: 6 }
            width: Math.min(root.bubbleWidth, words.implicitWidth + 24)
            height: visible ? words.implicitHeight + 16 : 0
            radius: 10
            color: "#e6150a1f"
            border { color: "#c77dff"; width: 1 }

            Text {
                id: words
                anchors { fill: parent; margins: 8; leftMargin: 12; rightMargin: 12 }
                text: root.said
                color: "#f3e8ff"
                font.pixelSize: 14
                wrapMode: Text.Wrap
                width: root.bubbleWidth - 24
            }
        }

        AnimatedSprite {
            id: sprite
            anchors { left: parent.left; bottom: parent.bottom }
            width: root.spriteWidth
            height: root.spriteHeight
            source: "file://" + root.sprites + root.clip + ".png"
            frameCount: root.clips[root.clip].frames
            frameRate: root.clips[root.clip].fps
            frameWidth: root.cellWidth
            frameHeight: root.cellHeight
            loops: root.clips[root.clip].loop ? AnimatedSprite.Infinite : 1
            interpolate: false
            smooth: true
            onFinished: if (root.clip !== "idle") root.play("idle")

            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                onClicked: {
                    if (root.said !== "") { root.said = ""; hold.stop() }
                    else root.play("grin")
                }
            }
        }
    }

    // An occasional blink while she's idling: every 4 to 9 seconds.
    Timer {
        interval: 4000 + Math.random() * 5000
        running: true
        repeat: true
        onTriggered: {
            interval = 4000 + Math.random() * 5000
            if (root.clip === "idle") root.play("blink")
        }
    }
}
