// Mira's body on laphvk: her sprite life as a full-screen, click-through overlay (only her body takes the pointer).
//
// Sheets: ~/.argus/sprites/mira/grid (build_sheets.py; recoloured Capri Desktop art, see ../NOTICE.md).
// Rules (geometry, ledges, landing): pet.js. Run: `quickshell -c mira-pet` (its own config, never Caelestia's).
//
// What she does: arrives glitching in; sits on window tops (perch) or stands on the floor; blinks, glitches now and
// then, breathes; walks along her ledge or hops to another window (glitch out, glitch in); lies down along a window
// for a while; sleeps when Hannah's away and wakes when she's back; dances (or sways on her perch) while music plays;
// dangles when picked up and falls onto whatever is below; follows her window when it moves and falls when it goes;
// talks (mouth, or her perch/lying talk) while MIRA speaks or her bubble shows. Pats (rub the cursor back and forth
// over her), a click (a glitch, or waking her), a double click (dance), right click (hide; she comes back to talk).
// Pats, tosses, pokes and waking her go to the companion (~/.argus/companion/event.json) as moments Mira may answer.
//
// She keeps off laphvk's right edge (x = 1919): Lan Mouse's capture strip back to winhvk.
import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Services.Mpris
import "pet.js" as Pet

ShellRoot {
    id: root

    readonly property string home: Quickshell.env("HOME")
    readonly property string gridDir: "file://" + home + "/.argus/sprites/mira/grid/"
    readonly property string companion: home + "/.argus/companion/"
    property var grid: ({})
    readonly property bool loaded: grid.idle !== undefined
    property real size: 190                          // her square, in pixels

    // ---- state
    property string mode: "hidden"                // hidden, resting, walking, falling, dragging
    property string current: "idle"               // the clip playing
    property bool oneShot: false                  // a transition plays once, then `after` runs
    property var after: null
    property real clipStart: 0
    property int facing: 1
    property real ax: 300                         // her square's top-left
    property real ay: 700
    property var ledge: null
    property var spots: []                        // ledges on the visible workspace
    property var clients: []
    property int workspace: 1
    property bool lying: false
    property bool sleeping: false
    property bool music: false
    property real danceUntil: 0
    property bool panelBusy: false
    property string said: ""
    property string lastId: ""
    property real now: Date.now() / 1000
    property real lastTick: now
    property real nextCheck: 0
    property real nextWander: 0
    property real nextLie: 0
    property real lyingUntil: 0
    property real nextGlitch: 0
    property real hiddenUntil: 0
    property real vy: 0
    property var fallTo: null
    property real fallFrom: 0
    property real walkTo: 0
    property int lastCycle: -1
    property string blinkWith: ""
    property var events: ({})

    // ---- derived
    readonly property real screenW: win.width
    readonly property real screenH: win.height
    readonly property var floor: ({ x1: 76, x2: screenW - 12, y: screenH - 2 })
    readonly property bool talking: said !== "" || panelBusy
    readonly property bool grooving: (music || danceUntil > now) && !talking
    property bool floorSit: false                 // on the floor: sitting on the bottom edge rather than standing
    property real nextPosture: 0
    readonly property bool seated: ledge !== null && mode === "resting" && (!ledge.floor || floorSit)
    readonly property bool quiet: mode === "resting" && !oneShot && !talking
    readonly property string baseName: Pet.sheetFor(current, facing, grid)
    readonly property var baseInfo: grid[baseName] || null
    readonly property var bx: Pet.box(current, baseInfo, size, ax, ay, facing)
    readonly property int frameIndex: baseInfo ? Math.floor((now - clipStart) * baseInfo.fps) : 0
    readonly property int baseCell: baseInfo ? (oneShot ? Math.min(frameIndex, baseInfo.frames - 1) : frameIndex % baseInfo.frames) : 0
    readonly property bool settled: ["idle", "perch", "laydown", "perch_music", "dance", "perch_talk", "laydown_talk"].indexOf(current) >= 0
    readonly property bool glitching: /glitch|arrive|leave/.test(current) || /glitch/.test(blinkShown)
    readonly property var blinkRule: ({ idle: { from: 9, n: 4 }, perch: { from: 28, n: 8 }, laydown: { from: 28, n: 8 } })[current] || null
    readonly property string blinkShown: blinkRule && blinkWith && baseCell >= blinkRule.from && baseCell < blinkRule.from + blinkRule.n
                                         ? Pet.sheetFor(blinkWith, facing, grid) : ""
    readonly property int blinkCell: blinkRule ? baseCell - blinkRule.from : 0
    readonly property bool mouthOn: talking && current === "idle" && !blinkShown

    // ---- clips

    function play(name, then) {
        current = name
        clipStart = now
        oneShot = true
        after = then || null
        lastCycle = -1
    }

    function loopClip() {
        if (mode === "dragging" || mode === "falling") return "dangle"
        if (mode === "walking") return "walk"
        if (seated && lying) return sleeping ? "laydown_sleep" : (talking ? "laydown_talk" : "laydown")
        if (seated) return talking ? "perch_talk" : (grooving ? "perch_music" : "perch")
        if (sleeping) return "sleep"
        if (grooving) return "dance"
        return "idle"
    }

    function glitchClip() { return seated ? (lying ? "laydown_glitch" : "perch_glitch") : "glitch" }

    function animate() {
        if (!baseInfo) return
        if (oneShot) {
            const runs = current === "grin" ? 2 : 1
            if (frameIndex >= baseInfo.frames * runs) {
                const then = after
                oneShot = false
                after = null
                current = loopClip()
                clipStart = now
                if (then) then()
            }
            return
        }
        const want = loopClip()
        if (want !== current) { current = want; clipStart = now; lastCycle = -1; return }
        const cycle = Math.floor(frameIndex / baseInfo.frames)
        if (cycle !== lastCycle) {
            lastCycle = cycle
            const roll = Math.random()
            const blink = { idle: "blink", perch: "perch_blink", laydown: "laydown_blink" }[current]
            blinkWith = blink && !sleeping ? (roll < 0.1 ? blink + "_glitch" : roll < 0.55 ? blink : "") : ""
            if (now >= nextGlitch && quiet && !sleeping && ["idle", "perch", "laydown"].indexOf(current) >= 0) {
                nextGlitch = now + 30 + Math.random() * 30
                if (cycle > 0) play(glitchClip())
            }
        }
    }

    // ---- where she is

    function hip() {
        const h = Pet.hipShare(Pet.family(current).seated || (seated && mode === "resting"), facing)
        return { x: ax + h.x * size, y: ay + h.y * size }
    }

    function placeOn(l, x, sit) {
        // Lying along the screen's bottom edge, her hanging limbs would leave her mostly off screen: lift her a little.
        const y = l.floor && lying ? l.y - size * 0.2 : l.y
        const a = Pet.anchorFor(x, y, size, sit, facing)
        ax = a.x
        ay = a.y
    }

    function lieDown(f, stay) {
        const x = hip().x
        facing = f
        lying = true
        placeOn(ledge, x, true)
        if (stay) lyingUntil = now + stay
    }

    function getUp() {
        const x = hip().x
        lying = false
        placeOn(ledge, x, true)
        play("perch_glitch")
    }

    function settle(l, x, sit) {
        ledge = l
        mode = "resting"
        floorSit = l.floor && !!sit
        x = Pet.clampX(l, x, size, screenW)
        facing = x > screenW / 2 ? -1 : 1
        placeOn(l, x, !l.floor || floorSit)
    }

    // On the floor she sometimes sits on the bottom edge, legs over it, and stands back up.
    function posture(sit) {
        if (!ledge || !ledge.floor || floorSit === sit) return
        const x = hip().x
        floorSit = sit
        lying = false
        placeOn(ledge, x, sit)
        play(sit ? "perch_glitch" : "glitch")
    }

    function appear() {
        if (!loaded || spots.length === 0) return
        const windows = spots.filter(l => !l.floor)
        const l = windows.length && Math.random() < 0.6 ? windows[Math.floor(Math.random() * windows.length)] : spots[0]
        const sit = l.floor && Math.random() < 0.4
        settle(l, l.floor ? floor.x1 + 140 + Math.random() * 300 : l.x1 + (l.x2 - l.x1) * Math.random(), sit)
        lying = false
        play(l.floor && !sit ? "arrive" : "perch_arrive")
        nextPosture = now + 90 + Math.random() * 150
        nextWander = now + 40 + Math.random() * 60
        nextLie = now + 90 + Math.random() * 240
        nextGlitch = now + 20 + Math.random() * 30
    }

    function vanish(then) {
        lying = false
        play(seated ? "perch_leave" : "leave", () => { mode = "hidden"; if (then) then() })
    }

    function hop() {
        const others = spots.filter(l => !ledge || l.win !== ledge.win || l.floor !== ledge.floor)
        if (!others.length) return
        const l = others[Math.floor(Math.random() * others.length)]
        const sit = l.floor && Math.random() < 0.4
        vanish(() => { settle(l, l.x1 + (l.x2 - l.x1) * Math.random(), sit); play(l.floor && !sit ? "arrive" : "perch_arrive") })
    }

    function walk() {
        if (!ledge) return
        const h = hip()
        const target = Pet.clampX(ledge, ledge.x1 + (ledge.x2 - ledge.x1) * Math.random(), size, screenW)
        if (Math.abs(target - h.x) < size * 0.5) return
        facing = target > h.x ? 1 : -1
        lying = false
        floorSit = false
        mode = "walking"
        walkTo = target
        placeOn(ledge, h.x, false)
    }

    function endWalk() {
        const x = hip().x
        mode = "resting"
        placeOn(ledge, x, !ledge.floor)
        if (!ledge.floor) play("perch_glitch")
    }

    function fall() {
        lying = false
        sleeping = false
        const h = hip()
        mode = "falling"
        ledge = null
        vy = 0
        fallFrom = h.y
        fallTo = Pet.below(spots, h.x, h.y, size)
    }

    function land(l) {
        const h = hip()
        const drop = l.y - fallFrom
        settle(l, h.x)
        play(l.floor ? "glitch" : "perch_glitch")
        if (drop > size * 2.2) tell("tossed")
    }

    // ---- the world

    function physics(dt) {
        if (mode === "falling") {
            vy += size * 11 * dt
            ay += vy * dt
            const target = fallTo || spots[0]
            if (target && hip().y >= target.y) land(target)
        } else if (mode === "walking") {
            const step = size * 0.42 * dt
            const x = hip().x
            if (Math.abs(walkTo - x) <= step) { ax += walkTo - x; endWalk() }
            else ax += facing * step
        }
    }

    function behave() {
        if (mode === "hidden") {
            if (loaded && (said !== "" || now >= hiddenUntil) && spots.length) appear()
            return
        }
        if (mode !== "resting" || !ledge) return
        if (!ledge.floor) {
            const c = spots.find(l => l.win === ledge.win)
            if (!c) { play(glitchClip(), fall); return }
            if (c.y !== ledge.y || c.x1 !== ledge.x1 || c.x2 !== ledge.x2) {
                const x = hip().x + (c.x2 - c.x1 === ledge.x2 - ledge.x1 ? c.x1 - ledge.x1 : 0)
                ledge = c
                placeOn(c, Pet.clampX(c, x, size, screenW), true)
            }
            if (Pet.covered(c, hip().x, spots)) { play(glitchClip(), fall); return }
        }
        // sleep and wake
        const sleepy = (awayMonitor.isIdle || forcedSleep) && !talking
        if (sleepy && !sleeping && !oneShot) {
            sleeping = true
            if (ledge.floor && !floorSit && Math.random() < 0.5) { floorSit = true; placeOn(ledge, hip().x, true) }
            if (seated && !lying) { const f = Pet.lieFacing(ledge, hip().x, size); if (f) lieDown(f, 0) }
        } else if (!sleepy && sleeping) {
            sleeping = false
            if (seated && lying) lyingUntil = now + 20 + Math.random() * 20
            else play("wake")
        }
        if (!quiet || sleeping) return
        if (ledge.floor && !lying && now >= nextPosture) {
            nextPosture = now + 90 + Math.random() * 150
            posture(!floorSit)
            return
        }
        // lying down for a while on a window (or along the floor's edge)
        if (seated && !lying && now >= nextLie) {
            const f = Pet.lieFacing(ledge, hip().x, size)
            nextLie = now + 480 + Math.random() * 240
            if (f) lieDown(f, 120 + Math.random() * 120)
        } else if (lying && now >= lyingUntil) {
            getUp()
        } else if (!lying && now >= nextWander) {
            nextWander = now + 60 + Math.random() * 120
            if (Math.random() < 0.5) walk()
            else hop()
        }
    }

    function tick() {
        now = Date.now() / 1000
        const dt = Math.min(0.05, now - lastTick)
        lastTick = now
        if (!loaded) return
        physics(dt)
        if (now >= nextCheck) { nextCheck = now + 0.25; behave() }
        animate()
    }

    // ---- touch

    property bool pressed: false
    property real downX: 0
    property real downY: 0
    property real grabX: 0
    property real grabY: 0
    property var clicks: []
    property var turns: []
    property real petX: 0
    property int petWay: 0
    property real petAt: -60

    function react() {
        clicks = clicks.filter(t => now - t < 4).concat([now])
        if (clicks.length >= 3) { clicks = []; tell("poked") }
        if (said !== "") { said = ""; hold.stop(); return }
        if (sleeping) { sleeping = false; forcedSleep = false; awake.restart(); tell("woke"); if (!lying) play("wake"); else lyingUntil = now + 30; return }
        play(glitchClip())
    }

    function petted() {
        petAt = now
        if (seated) { blinkWith = lying ? "laydown_blink" : "perch_blink"; lastCycle = Math.floor(frameIndex / (baseInfo ? baseInfo.frames : 1)) }
        else if (mode === "resting") play("grin")
        tell("pat")
    }

    function stroke(x) {
        if (pressed || mode !== "resting") { turns = []; petWay = 0; return }
        const dx = x - petX
        if (Math.abs(dx) < 6) return
        const way = dx > 0 ? 1 : -1
        petX = x
        if (petWay !== 0 && way !== petWay) turns = turns.filter(t => now - t < 1.5).concat([now])
        petWay = way
        if (turns.length >= 4 && now - petAt > 20) { turns = []; petted() }
    }

    function tell(kind) {
        if (events[kind] && now - events[kind] < 60) return
        events[kind] = now
        eventFile.setText(JSON.stringify({ id: String(Date.now()), kind: kind, at: new Date().toISOString() }))
    }

    // ---- her body on command: ~/.argus/companion/body.json {"id", "do"} (`argus companion body <action>`, and Mira's
    // own actions later). Each id runs once.
    property string lastCommand: ""
    function command(what) {
        console.info("mira-pet: body " + what + " (mode " + mode + ", " + current + (ledge ? (ledge.floor ? ", floor" : ", window") : "") + (floorSit ? ", sitting" : "") + ")")
        switch (what) {
        case "show": if (mode === "hidden") { hiddenUntil = 0; appear() } break
        case "hide": if (mode !== "hidden") vanish(() => { hiddenUntil = now + 900 }); break
        case "hop": if (mode === "resting") hop(); break
        case "walk": if (mode === "resting") walk(); break
        case "drop": if (mode === "resting") { ay -= size * 1.5; fall() } break
        case "lie": if (seated && !lying) { const f = Pet.lieFacing(ledge, hip().x, size); if (f) lieDown(f, 180) } break
        case "sit": if (lying) getUp(); else posture(true); break
        case "stand": if (lying) getUp(); posture(false); break
        case "sleep": if (mode === "resting") { sleeping = true; forcedSleep = true } break
        case "wake": if (sleeping) { sleeping = false; forcedSleep = false; if (!lying) play("wake") } break
        case "dance": danceUntil = now + 45; break
        case "stop_dancing": danceUntil = 0; break
        case "glitch": if (mode === "resting") play(glitchClip()); break
        case "grin": if (mode === "resting" && !seated) play("grin"); else if (seated) blinkWith = lying ? "laydown_blink" : "perch_blink"; break
        }
    }
    property bool forcedSleep: false
    FileView {
        id: bodyFile
        path: root.companion + "body.json"
        onLoaded: {
            let c
            try { c = JSON.parse(bodyFile.text()) } catch (e) { return }
            const id = String(c.id || "")
            if (id && id !== root.lastCommand) {
                const first = root.lastCommand === ""
                root.lastCommand = id
                if (!first || Date.now() - Number(id) < 10000) root.command(String(c.do || ""))
            }
        }
    }
    Timer { interval: 500; running: true; repeat: true; onTriggered: bodyFile.reload() }

    // ---- inputs: the sheets, the windows, speech, music, MIRA's voice, away

    FileView {
        path: root.home + "/.argus/sprites/mira/grid/grid.json"
        onLoaded: root.grid = JSON.parse(text()).clips
    }

    FileView { id: eventFile; path: root.companion + "event.json" }

    Process {
        id: hypr
        command: ["sh", "-c", "hyprctl -j activeworkspace; echo '@@MIRA@@'; hyprctl -j clients"]
        stdout: StdioCollector {
            onStreamFinished: {
                const parts = text.split("@@MIRA@@")
                try {
                    root.workspace = JSON.parse(parts[0]).id
                    root.clients = JSON.parse(parts[1])
                    root.spots = Pet.ledges(root.clients, root.workspace, root.floor, root.size)
                } catch (e) { }
            }
        }
    }
    Timer { interval: 700; running: true; repeat: true; triggeredOnStart: true; onTriggered: if (!hypr.running) hypr.running = true }

    FileView {
        id: speech
        path: root.companion + "say.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            let line
            try { line = JSON.parse(speech.text()) } catch (e) { return }
            const text = String(line.text || "").trim()
            const id = String(line.id || text)
            if (text && id !== root.lastId) {
                root.lastId = id
                root.said = text.slice(0, 400)
                hold.interval = Math.max(5000, Math.min(20000, text.length * 65))
                hold.restart()
                if (root.mode === "resting" && !root.oneShot) root.play(root.glitchClip())
            }
        }
    }
    // The watch only follows the file that existed when it started; re-read it too. A seen id is never repeated.
    Timer { interval: 1500; running: true; repeat: true; onTriggered: speech.reload() }
    Timer { id: hold; onTriggered: root.said = "" }

    Timer {
        interval: 1000; running: true; repeat: true
        onTriggered: {
            root.music = Mpris.players.values.some(p => p.isPlaying)
            const req = new XMLHttpRequest()
            req.onreadystatechange = () => {
                if (req.readyState !== XMLHttpRequest.DONE) return
                try { root.panelBusy = req.status === 200 && JSON.parse(req.responseText).busy === true } catch (e) { root.panelBusy = false }
            }
            req.open("GET", "http://127.0.0.1:8769/status")
            req.send()
        }
    }

    // For the companion's ticker: {"idle_since": <unix seconds> | null} (Wayland only says "idle at least N s").
    IdleMonitor {
        id: idleMonitor
        timeout: 60
        respectInhibitors: true
        onIsIdleChanged: stateFile.setText(JSON.stringify({ idle_since: idleMonitor.isIdle ? Math.floor(Date.now() / 1000) - idleMonitor.timeout : null }))
    }
    FileView { id: stateFile; path: root.companion + "state.json"; Component.onCompleted: stateFile.setText(JSON.stringify({ idle_since: null })) }
    IdleMonitor { id: awayMonitor; timeout: 300; respectInhibitors: true }
    Timer { id: awake; interval: 120000 }   // a click-woken nap doesn't fall straight back asleep

    Timer { interval: 33; running: true; repeat: true; onTriggered: root.tick() }

    // ---- her

    PanelWindow {
        id: win
        anchors { top: true; bottom: true; left: true; right: true }
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Top
        WlrLayershell.namespace: "mira-pet"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        mask: Region { item: hit }

        // Only her body takes the pointer (and only near it): the rest of the screen is clicked straight through.
        Item {
            id: hit
            readonly property bool on: root.mode !== "hidden" && root.loaded
            x: on ? root.bx.x + root.bx.w * 0.15 : 0
            y: on ? root.bx.y + root.bx.h * 0.05 : 0
            width: on ? root.bx.w * 0.7 : 0
            height: on ? root.bx.h * 0.9 : 0
        }

        Item {
            id: body
            visible: root.mode !== "hidden" && root.loaded
            x: root.bx.x
            y: root.bx.y + (root.settled ? Math.sin(root.now * 1.75) * 2.2 * root.size / 240 : 0)
            width: root.bx.w
            height: root.bx.h
            rotation: root.settled ? Math.sin(root.now * 0.95) * 0.65 : 0

            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: root.talking ? "#d0c77dff" : "#80000000"
                shadowBlur: root.talking ? 0.9 + 0.1 * Math.sin(root.now * 4) : 0.5
                shadowVerticalOffset: root.talking ? 0 : 3
                shadowHorizontalOffset: 0
                blurMax: 32
            }

            Sheet {
                anchors.fill: parent
                folder: root.gridDir
                name: root.baseName
                info: root.baseInfo
                cell: root.baseCell
                mirror: root.facing < 0
                opacity: blink.visible ? 0 : 1
            }
            Sheet {
                id: blink
                anchors.fill: parent
                folder: root.gridDir
                name: root.blinkShown || (root.blinkWith ? Pet.sheetFor(root.blinkWith, root.facing, root.grid) : "")
                info: root.grid[name] || null
                cell: Math.max(0, root.blinkCell)
                mirror: root.facing < 0
                visible: root.blinkShown !== "" && ready
            }
            Sheet {
                anchors.fill: parent
                folder: root.gridDir
                name: "mouth"
                info: root.grid.mouth || null
                cell: Math.floor(root.now * 12) % 5
                mirror: root.facing < 0
                visible: root.mouthOn
            }
        }

        // Her glitches split into red and cyan for a moment.
        ShaderEffectSource { id: snap; sourceItem: body; live: true; hideSource: false; visible: false }
        MultiEffect {
            source: snap; x: body.x - 5 * Math.random(); y: body.y; width: body.width; height: body.height
            colorization: 1; colorizationColor: "#ff2a6d"; brightness: 0.2
            opacity: root.glitching && body.visible ? 0.45 : 0; visible: opacity > 0
        }
        MultiEffect {
            source: snap; x: body.x + 5 * Math.random(); y: body.y; width: body.width; height: body.height
            colorization: 1; colorizationColor: "#05d9e8"; brightness: 0.2
            opacity: root.glitching && body.visible ? 0.45 : 0; visible: opacity > 0
        }

        // What she says, over her head (kept on screen, clear of the left bar and the right edge).
        Rectangle {
            id: bubble
            visible: root.said !== "" && body.visible
            width: Math.min(340, words.implicitWidth + 64)
            height: Math.max(face.height + 16, words.implicitHeight + 18)
            x: Math.max(80, Math.min(root.screenW - width - 24, root.bx.x + root.bx.w / 2 - width / 2))
            y: root.bx.y - height - 10 < 8 ? root.bx.y + root.bx.h + 8 : root.bx.y - height - 10
            radius: 12
            color: "#ee150a1f"
            border { color: "#c77dff"; width: 1 }

            Image {
                id: face
                source: "file://" + root.home + "/.argus/sprites/mira/face.png"
                width: 36; height: 36
                x: 8; anchors.verticalCenter: parent.verticalCenter
                fillMode: Image.PreserveAspectCrop
                smooth: true
            }
            Text {
                id: words
                x: 52; anchors.verticalCenter: parent.verticalCenter
                width: Math.min(276, implicitWidth)
                text: root.said
                color: "#f3e8ff"
                font.pixelSize: 14
                wrapMode: Text.Wrap
            }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onPressed: mouse => {
                if (mouse.button === Qt.RightButton) { root.vanish(() => { root.hiddenUntil = root.now + 900 }); return }
                root.pressed = true
                root.downX = mouse.x
                root.downY = mouse.y
                root.grabX = mouse.x - root.ax
                root.grabY = mouse.y - root.ay
            }
            onPositionChanged: mouse => {
                if (!root.pressed) { root.stroke(mouse.x); return }
                const dx = mouse.x - root.downX, dy = mouse.y - root.downY
                if (root.mode !== "dragging" && dx * dx + dy * dy < 36) return
                if (root.mode !== "dragging") {
                    root.mode = "dragging"; root.ledge = null; root.lying = false; root.sleeping = false
                    root.oneShot = false; root.current = "dangle"; root.clipStart = root.now
                }
                root.ax = Math.min(root.screenW - root.size - 16, mouse.x - root.grabX)
                root.ay = mouse.y - root.grabY
            }
            onReleased: mouse => {
                if (mouse.button !== Qt.LeftButton || !root.pressed) return
                root.pressed = false
                if (root.mode === "dragging") root.fall()
                else root.react()
            }
            onDoubleClicked: mouse => {
                if (mouse.button === Qt.LeftButton) root.danceUntil = root.danceUntil > root.now ? 0 : root.now + 45
            }
        }
    }
}
