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
    property string mode: "hidden"                // hidden, resting, walking, falling, dragging, hanging
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
    // her mini player: shown while music plays (and a minute after), X puts it away until nothing's played for 10 s
    property var mpris: null
    property real lastPlaying: -1000
    property bool miniPutAway: false
    property bool miniOff: false
    readonly property bool miniShown: !miniOff && !miniPutAway && mode !== "hidden" && loaded && mpris !== null
                                      && (mpris.trackTitle || "") !== "" && now - lastPlaying < 60
    onMiniShownChanged: {
        if (miniShown && mode === "resting" && !(ledge && ledge.free) && !sleeping && !talking) {
            const seat = miniLedge()
            vanish(() => { settle(seat, seat.x1 + (seat.x2 - seat.x1) * 0.3, true); play("perch_arrive") })
        }
    }
    function miniLedge() {
        return { x1: mini.x + 12, x2: mini.x + mini.width - 12, y: mini.y + 1, win: "mini-player", floor: false,
                 floating: true, focus: -1 }
    }
    FileView {
        id: petPrefs
        path: root.companion + "pet-laphvk.json"
        onLoaded: {
            try {
                const p = JSON.parse(text())
                root.miniOff = p.mini_player_off === true
                if (root.sizes[p.size]) root.size = root.sizes[p.size]
            } catch (e) { }
        }
    }
    // her sizes, as on winhvk (`argus companion body size small|medium|large|huge|giant`), kept in pet-laphvk.json
    readonly property var sizes: ({ small: 150, medium: 190, large: 240, huge: 300, giant: 380 })
    function savePrefs() {
        let name = "medium"
        for (const k in sizes) if (sizes[k] === size) name = k
        petPrefs.setText(JSON.stringify({ mini_player_off: miniOff, size: name }))
    }
    function setMiniOff(off) { miniOff = off; savePrefs() }
    function setSize(name) {
        if (!sizes[name] || sizes[name] === size) return
        size = sizes[name]
        savePrefs()
        if (mode === "resting" && ledge) settle(ledge, hip().x, floorSit || !ledge.floor)
    }
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
    readonly property bool grooving: (music || peerMusic || danceUntil > now) && !talking
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
        if (mode === "dragging" || mode === "falling" || mode === "hanging") return "dangle"
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

    // Her start: forked neon veins crackle out from behind her as she glitches in, different every time.
    property real introAt: -100
    property bool introDone: false
    property var veins: []
    function startVeins() {
        const out = []
        const n = 8 + Math.floor(Math.random() * 5)
        const colours = ["#ff2a6d", "#05d9e8", "#c77dff", "#ff2a6d"]
        function grow(x, y, ang, len, depth) {
            const pts = [{ x: x, y: y }]
            const steps = 5 + Math.floor(Math.random() * 4)
            for (let i = 1; i <= steps; i++) {
                ang += (Math.random() - 0.5) * 0.9
                x += Math.cos(ang) * len / steps; y += Math.sin(ang) * len / steps
                pts.push({ x: x, y: y })
                if (depth < 2 && Math.random() < 0.28) grow(x, y, ang + (Math.random() < 0.5 ? -0.8 : 0.8), len * 0.45, depth + 1)
            }
            out.push({ pts: pts, colour: colours[Math.floor(Math.random() * colours.length)], width: depth ? 1.5 : 2.6,
                       delay: depth * 0.12 + Math.random() * 0.1 })
        }
        for (let i = 0; i < n; i++) {
            const ang = Math.PI * 2 * i / n + (Math.random() - 0.5) * 0.6
            grow(0, 0, ang, size * (0.6 + Math.random() * 0.9), 0)
        }
        veins = out
        introAt = now
    }
    readonly property bool introOn: now - introAt < 1.6

    function appear() {
        if (!loaded || spots.length === 0) return
        if (!introDone) { introDone = true; startVeins() }
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

    // Glitch over to the pointer (Hyprland's cursor) and drop onto whatever is under it.
    function comeHere() {
        if (mode === "dragging") return
        riding = false
        cursor.then = p => vanish(() => { settle({ x1: p.x - 4, x2: p.x + 4, y: p.y, win: "", floor: false, free: true }, p.x, false); play("glitch", fall) })
        cursor.running = true
    }
    // "Go somewhere else": always somewhere - another window, or well along the floor - from wherever she is.
    function elsewhere() {
        if (mode === "dragging" || mode === "falling") return
        const wide = spots.filter(l => l.x2 - l.x1 > size * 0.6)
        if (!wide.length) return
        const h = hip()
        for (let tries = 0; tries < 24; tries++) {
            const l = wide[Math.floor(Math.random() * wide.length)]
            const x = Pet.clampX(l, l.x1 + (l.x2 - l.x1) * Math.random(), size, screenW)
            if (Math.abs(x - h.x) < size * 2 && Math.abs(l.y - h.y) < size && mode !== "hidden") continue
            riding = false; sleeping = false; forcedSleep = false; hiddenUntil = now + 5
            const sit = l.floor && Math.random() < 0.4
            vanish(() => { settle(l, x, sit); play(l.floor && !sit ? "arrive" : "perch_arrive") })
            return
        }
    }
    function teleport(l, sit) {
        riding = false
        vanish(() => { settle(l, l.x1 + (l.x2 - l.x1) * 0.4, sit); play(l.floor && !sit ? "arrive" : "perch_arrive") })
    }
    // "Sit on my Discord window": the ledge of the first window whose class or title has the words in it.
    function perchOn(what) {
        what = String(what || "").toLowerCase()
        if (!what) return
        if (what === "taskbar" || what === "floor") { teleport(spots.find(l => l.floor), false); return }
        if (what === "player" || what === "mini player") { if (miniShown) teleport(miniLedge(), true); return }
        const names = {}
        for (const c of clients) names[c.address] = ((c.class || "") + " " + (c.title || "")).toLowerCase()
        const l = spots.find(x => !x.floor && names[x.win] && names[x.win].indexOf(what) >= 0)
        if (l) teleport(l, true)
    }
    // Riding her cursor: while on, her seat is just under the pointer (polled from Hyprland only while riding).
    property bool riding: false
    Process {
        id: cursor
        property var then: null
        command: ["hyprctl", "cursorpos", "-j"]
        stdout: StdioCollector {
            onStreamFinished: {
                let p
                try { p = JSON.parse(text) } catch (e) { return }
                if (cursor.then) { const f = cursor.then; cursor.then = null; f(p); return }
                if (root.riding && root.mode === "resting") {
                    root.ledge = { x1: p.x - 4, x2: p.x + 4, y: p.y + 18, win: "", floor: false, free: true }
                    root.placeOn(root.ledge, p.x + 6, true)
                }
            }
        }
    }
    Timer { interval: 40; repeat: true; running: root.riding; onTriggered: if (!cursor.running) cursor.running = true }

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
        if (!ledge.floor && !ledge.free) {
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
        if (!quiet || sleeping || ledge.free) return
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
        noteTick()
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

    // Like Capri: dropped with Shift she sits right there (a seat of her own until moved); with Ctrl she hangs.
    function sitHere() {
        const h = hip()
        const seat = { x1: h.x - 4, x2: h.x + 4, y: h.y, win: "", floor: false, free: true }
        ledge = seat
        mode = "resting"
        floorSit = false
        placeOn(seat, h.x, true)
        play("perch_glitch")
    }

    function react() {
        if (mode === "hanging") { play("glitch", fall); return }
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
        let arg = ""
        const space = String(what).indexOf(" ")
        if (space > 0) { arg = what.slice(space + 1).trim(); what = what.slice(0, space) }
        switch (what) {
        case "come_here": comeHere(); break
        case "hop_in": hiddenUntil = now + 5; comeHere(); break    // she came over from her other body (no appearing elsewhere first)
        case "perch": perchOn(arg); break
        case "floor": teleport(spots.find(l => l.floor), false); break
        case "ride": if (mode === "resting" || mode === "hanging") { riding = true; lying = false; sleeping = false; mode = "resting"; play("perch_glitch") } break
        case "hop_off": if (riding) { riding = false; play("perch_glitch", fall) } break
        case "type": if (mode === "hidden") { hiddenUntil = 0; appear() } typing = true; break
        case "stop_typing": typing = false; break
        case "show": if (mode === "hidden") { hiddenUntil = 0; appear() } break
        case "hide": if (mode !== "hidden") vanish(() => { hiddenUntil = now + 900 }); break
        case "hop": if (mode === "resting") hop(); break
        case "elsewhere": elsewhere(); break
        case "size": setSize(arg.toLowerCase()); break
        case "next_screen": case "this_screen": teleport(spots.find(l => l.floor), false); break   // one screen here
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
        case "mini_player_on": setMiniOff(false); break
        case "mini_player_off": setMiniOff(true); break
        case "grin": if (mode === "resting" && !seated) play("grin"); else if (seated) blinkWith = lying ? "laydown_blink" : "perch_blink"; break
        }
    }
    property bool forcedSleep: false
    property bool typing: false                   // the typing box is open (it has the keyboard)
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
    FileView { id: askFile; path: root.companion + "ask.json" }

    function send(text) {
        typing = false
        text = String(text || "").trim()
        if (text) askFile.setText(JSON.stringify({ id: String(Date.now()), text: text, at: new Date().toISOString() }))
    }

    Process {
        id: hypr
        command: ["sh", "-c", "hyprctl -j activeworkspace; echo '@@MIRA@@'; hyprctl -j clients"]
        stdout: StdioCollector {
            onStreamFinished: {
                const parts = text.split("@@MIRA@@")
                try {
                    root.workspace = JSON.parse(parts[0]).id
                    root.clients = JSON.parse(parts[1])
                    const spots = Pet.ledges(root.clients, root.workspace, root.floor, root.size)
                    if (root.miniShown) spots.push(root.miniLedge())
                    root.spots = spots
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
                hold.interval = Math.max(8000, Math.min(25000, text.length * 80))
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
            const players = Mpris.players.values
            const playing = players.find(p => p.isPlaying)
            root.music = !!playing
            if (playing) { root.mpris = playing; root.lastPlaying = root.now }
            else if (root.mpris && players.indexOf(root.mpris) < 0) root.mpris = null
            if (root.miniPutAway && root.now - root.lastPlaying > 10) root.miniPutAway = false
            const req = new XMLHttpRequest()
            req.onreadystatechange = () => {
                if (req.readyState !== XMLHttpRequest.DONE) return
                try { root.panelBusy = req.status === 200 && JSON.parse(req.responseText).busy === true } catch (e) { root.panelBusy = false }
            }
            req.open("GET", "http://127.0.0.1:8769/status")
            req.send()
        }
    }

    // ---- the engine's move as an arrow over the coached board (arrow.json from her chess coach)
    property var arrow: null
    FileView {
        id: arrowFile
        path: root.companion + "arrow.json"
        printErrors: false
        onLoaded: {
            let a = null
            try { a = JSON.parse(text()) } catch (e) { }
            const ok = a && a.at && Date.now() / 1000 - a.at < 600 && a.box && a.from && a.to
            if (!ok) { if (root.arrow !== null) root.arrow = null; return }
            if (!root.arrow || root.arrow.id !== a.id) root.arrow = a
        }
    }
    Timer { interval: 400; running: true; repeat: true; onTriggered: arrowFile.reload() }

    // ---- one Mira, two bodies: music on winhvk makes her dance here too (link.json, from the companion's link),
    // and she nods on the beat her ears hear (beat.json here, or the one winhvk's ears send over the link).
    property bool peerMusic: false
    property real beatBpm: 0
    property real beatAt: 0
    property var peerBeat: null
    property var localBeat: null
    FileView {
        id: linkFile
        printErrors: false             // absent until the link / her ears first write it
        path: root.companion + "link.json"
        onLoaded: {
            try {
                const l = JSON.parse(text())
                const fresh = Date.now() / 1000 - (l.at || 0) < 15
                root.peerMusic = fresh && !!(l.music && l.music.playing)
                root.peerBeat = root.peerMusic && l.music.bpm ? { bpm: l.music.bpm, at: l.music.beat_at } : null
            } catch (e) { root.peerMusic = false; root.peerBeat = null }
            root.pickBeat()
        }
    }
    FileView {
        id: beatFile
        printErrors: false             // absent until the link / her ears first write it
        path: root.companion + "beat.json"
        onLoaded: {
            try {
                const b = JSON.parse(text())
                root.localBeat = b.bpm && Date.now() / 1000 - (b.at || 0) < 15 ? { bpm: b.bpm, at: b.beat_at } : null
            } catch (e) { root.localBeat = null }
            root.pickBeat()
        }
    }
    function pickBeat() {
        const b = music && localBeat ? localBeat : (peerMusic ? peerBeat : null)
        beatBpm = b ? b.bpm : 0
        beatAt = b ? b.at : 0
    }
    Timer { interval: 1000; running: true; repeat: true; onTriggered: { linkFile.reload(); beatFile.reload() } }
    // where in the beat she is (0 on it, rising to 1 just before the next), -1 with no beat lock
    readonly property real beatPhase: beatBpm > 0 ? ((((now - beatAt) * beatBpm / 60) % 1) + 1) % 1 : -1
    readonly property bool dancing: (current === "dance" || current === "perch_music") && mode === "resting"
    readonly property real nod: dancing && beatPhase >= 0 ? size * 0.028 * Math.exp(-beatPhase * 6) : 0
    // music notes off her head: every other beat with a lock, about a beat's worth of time without
    property var notes: []
    property real lastNote: 0
    property int lastBeat: -1
    function noteTick() {
        let due = false
        if (dancing && body.visible) {
            if (beatBpm > 0) {
                const n = Math.floor((now - beatAt) * beatBpm / 60)
                if (n !== lastBeat) { due = n % 2 === 0; lastBeat = n }
            } else due = now - lastNote > 0.9
        }
        const kept = notes.filter(n => now - n.born < 1.8)
        if (due) {
            lastNote = now
            kept.push({ born: now, glyph: ["♪", "♫", "♬", "♩"][Math.floor(Math.random() * 4)],
                        color: Math.random() < 0.5 ? "#ff2a6d" : "#05d9e8", wob: Math.random() * 6,
                        x: bx.x + bx.w * (0.25 + Math.random() * 0.5), y: bx.y + bx.h * 0.12 })
        }
        if (due || kept.length !== notes.length) notes = kept
    }

    // For the companion's ticker: {"idle_since": <unix seconds> | null} (Wayland only says "idle at least N s").
    // Presence is about input, not the screensaver: a paused video in a browser holds an idle inhibitor for hours,
    // and respecting it made Hannah look present all night (2026-11-02: "late" check-ins at 3 am).
    IdleMonitor {
        id: idleMonitor
        timeout: 60
        respectInhibitors: false
        onIsIdleChanged: root.writeIdle(idleMonitor.isIdle)
    }
    // Wayland only tells a new client about idleness from when it started, so a restart would make Hannah look
    // freshly present: keep the stored idle_since across restarts, and clear it only once she's seen active.
    property var storedIdleSince: null
    function writeIdle(idle) {
        const since = idle ? (storedIdleSince || Math.floor(Date.now() / 1000) - idleMonitor.timeout) : null
        storedIdleSince = since
        stateFile.setText(JSON.stringify({ idle_since: since }))
    }
    FileView {
        id: stateFile
        path: root.companion + "state.json"
        onLoaded: { try { root.storedIdleSince = JSON.parse(text()).idle_since || null } catch (e) { } }
    }
    // Not idle a while after starting means she was active: clear what an earlier run left behind.
    Timer { interval: 65000; running: true; onTriggered: if (!idleMonitor.isIdle) root.writeIdle(false) }
    IdleMonitor { id: awayMonitor; timeout: 300; respectInhibitors: false }
    Timer { id: awake; interval: 120000 }   // a click-woken nap doesn't fall straight back asleep

    // As fast as she needs: 30 fps for her 30 fps clips and while she moves, 15 otherwise, 4 while hidden.
    Timer {
        interval: root.mode === "hidden" ? 250
                  : (root.mode !== "resting" || (root.baseInfo && root.baseInfo.fps >= 24) || root.glitching) ? 33 : 66
        running: true; repeat: true
        onTriggered: root.tick()
    }

    // ---- her

    PanelWindow {
        id: win
        anchors { top: true; bottom: true; left: true; right: true }
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Top
        WlrLayershell.namespace: "mira-pet"
        // The keyboard only while the typing box is open; never otherwise.
        WlrLayershell.keyboardFocus: root.typing ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
        mask: Region { item: hit; Region { item: typeBox } Region { item: miniArea } }

        Canvas {
            id: veinCanvas
            anchors.fill: parent
            visible: root.introOn
            property real age: root.now - root.introAt
            onAgeChanged: if (visible) requestPaint()
            onPaint: {
                const g = getContext("2d")
                g.reset()
                if (!root.introOn) return
                const cx = root.bx.x + root.bx.w / 2, cy = root.bx.y + root.bx.h * 0.55
                const fade = age < 1.0 ? 1 : Math.max(0, 1 - (age - 1.0) / 0.6)
                g.lineCap = "round"; g.lineJoin = "round"
                for (const v of root.veins) {
                    const t = Math.max(0, Math.min(1, (age - v.delay) / 0.45))
                    if (t <= 0) continue
                    const upto = Math.max(1, Math.floor((v.pts.length - 1) * t))
                    const jx = (Math.random() - 0.5) * 4, jy = (Math.random() - 0.5) * 3      // the glitch shake
                    for (const pass of [{ w: v.width * 4, a: 0.22 }, { w: v.width, a: 0.95 }]) {
                        g.globalAlpha = pass.a * fade * (0.75 + 0.25 * Math.random())
                        g.strokeStyle = v.colour; g.lineWidth = pass.w
                        g.beginPath()
                        g.moveTo(cx + v.pts[0].x + jx, cy + v.pts[0].y + jy)
                        for (let i = 1; i <= upto; i++) g.lineTo(cx + v.pts[i].x + jx, cy + v.pts[i].y + jy)
                        g.stroke()
                    }
                }
            }
        }

        Canvas {
            id: arrowCanvas
            anchors.fill: parent
            visible: root.arrow !== null
            opacity: 0.78 + 0.12 * Math.sin(root.now * 3)
            property var shown: root.arrow
            onShownChanged: requestPaint()
            function centre(a, sq) {
                const f = sq.charCodeAt(0) - 97, r = sq.charCodeAt(1) - 49
                const col = a.white_bottom ? f : 7 - f, row = a.white_bottom ? 7 - r : r
                const w = (a.box[2] - a.box[0]) / 8, h = (a.box[3] - a.box[1]) / 8
                return { x: a.box[0] + (col + 0.5) * w, y: a.box[1] + (row + 0.5) * h, s: Math.min(w, h) }
            }
            onPaint: {
                const g = getContext("2d")
                g.reset()
                const a = shown
                if (!a) return
                const p = centre(a, a.from), q = centre(a, a.to)
                const ang = Math.atan2(q.y - p.y, q.x - p.x), head = p.s * 0.42, wide = p.s * 0.17
                const ex = q.x - Math.cos(ang) * head * 0.8, ey = q.y - Math.sin(ang) * head * 0.8
                g.lineCap = "round"
                for (const pass of [{ c: "#55ff2a6d", w: wide * 2.2 }, { c: "#ff2a6d", w: wide }]) {
                    g.strokeStyle = pass.c; g.lineWidth = pass.w
                    g.beginPath(); g.moveTo(p.x, p.y); g.lineTo(ex, ey); g.stroke()
                }
                g.fillStyle = "#ff2a6d"
                g.beginPath()
                g.moveTo(q.x, q.y)
                g.lineTo(q.x - Math.cos(ang - 0.5) * head, q.y - Math.sin(ang - 0.5) * head)
                g.lineTo(q.x - Math.cos(ang + 0.5) * head, q.y - Math.sin(ang + 0.5) * head)
                g.closePath(); g.fill()
                g.strokeStyle = "#05d9e8"; g.lineWidth = Math.max(2, wide * 0.18)
                g.beginPath(); g.arc(p.x, p.y, p.s * 0.2, 0, Math.PI * 2); g.stroke()
            }
        }

        MiniPlayer {
            id: mini
            visible: root.miniShown
            x: root.floor.x1 + 16
            y: root.floor.y - height - 40
            player: root.mpris
            now: root.now
            onPutAway: { root.miniPutAway = true; menuOpen = false }
            onTurnOff: { root.setMiniOff(true); menuOpen = false }
        }
        // what of the player takes clicks: the plate, and its menu above it while open
        Item {
            id: miniArea
            readonly property int menu: mini.menuOpen ? 90 : 0
            x: root.miniShown ? mini.x : 0
            y: root.miniShown ? mini.y - menu : 0
            width: root.miniShown ? mini.width : 0
            height: root.miniShown ? mini.height + menu : 0
        }

        // Only her body takes the pointer (and only near it): the rest of the screen is clicked straight through.
        Item {
            id: hit
            readonly property bool on: root.mode !== "hidden" && root.loaded && !root.riding   // riding: clicks pass through her
            x: on ? root.bx.x + root.bx.w * 0.15 : 0
            y: on ? root.bx.y + root.bx.h * 0.05 : 0
            width: on ? root.bx.w * 0.7 : 0
            height: on ? root.bx.h * 0.9 : 0
        }

        Item {
            id: body
            visible: root.mode !== "hidden" && root.loaded
            x: root.bx.x
            y: root.bx.y + root.nod + (root.settled ? Math.sin(root.now * 1.75) * 2.2 * root.size / 240 : 0)
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

        Repeater {
            model: root.notes
            delegate: Text {
                required property var modelData
                readonly property real age: root.now - modelData.born
                text: modelData.glyph
                color: modelData.color
                font.pixelSize: Math.round(root.size * 0.12)
                font.bold: true
                style: Text.Outline; styleColor: "#80000000"
                x: modelData.x + Math.sin(age * 3 + modelData.wob) * root.size * 0.05
                y: modelData.y - age * root.size * 0.24
                opacity: Math.max(0, 1 - age / 1.8)
                scale: 0.7 + Math.min(0.5, age * 0.6)
                visible: body.visible
            }
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

        // Typing to her: Enter sends (the companion answers in her bubble), Esc closes.
        Rectangle {
            id: typeBox
            visible: root.typing && body.visible
            width: visible ? 360 : 0
            height: visible ? 40 : 0
            x: Math.max(80, Math.min(root.screenW - 384, root.bx.x + root.bx.w / 2 - 180))
            y: root.bx.y - 54 < 8 ? root.bx.y + root.bx.h + 8 : root.bx.y - 54
            radius: 10
            color: "#f0150a1f"
            border { color: "#c77dff"; width: 1 }
            onVisibleChanged: if (visible) { input.text = ""; input.forceActiveFocus() }

            TextInput {
                id: input
                anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                verticalAlignment: TextInput.AlignVCenter
                color: "#f3e8ff"
                selectionColor: "#c77dff"
                font.pixelSize: 15
                clip: true
                onAccepted: root.send(text)
                Keys.onEscapePressed: root.typing = false
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Say something to Mira…"
                    color: "#8a7a99"
                    font.pixelSize: 15
                    visible: !input.text
                }
            }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onPressed: mouse => {
                if (mouse.button === Qt.MiddleButton) { root.typing = true; return }
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
                    root.mode = "dragging"; root.ledge = null; root.lying = false; root.sleeping = false; root.riding = false
                    root.oneShot = false; root.current = "dangle"; root.clipStart = root.now
                }
                root.ax = Math.min(root.screenW - root.size - 16, mouse.x - root.grabX)
                root.ay = mouse.y - root.grabY
            }
            onReleased: mouse => {
                if (mouse.button !== Qt.LeftButton || !root.pressed) return
                root.pressed = false
                if (root.mode === "dragging") {
                    if (mouse.modifiers & Qt.ShiftModifier) root.sitHere()
                    else if (mouse.modifiers & Qt.ControlModifier) { root.mode = "hanging"; root.current = "dangle"; root.clipStart = root.now }
                    else root.fall()
                }
                else root.react()
            }
            onDoubleClicked: mouse => {
                if (mouse.button === Qt.LeftButton) root.command(root.riding ? "hop_off" : "ride")
            }
        }
    }
}
