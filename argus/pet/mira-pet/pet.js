// Mira's body rules: clip geometry, ledges and landing. Pure functions; shell.qml holds the state.
//
// Geometry follows the art (Capri Desktop's sheets, recoloured): every clip is drawn in a box centred on her S x S
// square, `h` times S tall, shifted by (sx, sy) x S. Her hip - the point that sits on a ledge - is at SIT of the
// square when seated and STAND when on her feet. Facing left draws the `_flipped` sheet (the art drawn for that side:
// her limbs are asymmetric) mirrored; clips without one are just mirrored.
.pragma library

var SIT = { x: 0.30, y: 0.79 }
var STAND = { x: 0.50, y: 0.99 }
var PERCH_TOP = 0.17          // how much headroom a seat needs above the ledge, as a share of S above SIT.y

var LIE_SCALE = 0.85
var LIE_H = 250 / 384 * LIE_SCALE
var LIE_SY = (SIT.y - 0.5) * (1 - LIE_SCALE) + 94 / 384 * LIE_SCALE
var LIE_REACH = 0.78 * LIE_SCALE   // how far her hair reaches back along the ledge from her hip

function family(clip) {
    if (clip.indexOf("laydown") === 0) return { h: LIE_H, sx: 0, sy: LIE_SY, seated: true }
    if (clip.indexOf("perch") === 0) return { h: 1, sx: -26 / 384, sy: 36 / 384, seated: true }
    return { h: 1.11, sx: 0, sy: 0, seated: false }
}

// The sheet to draw for a clip facing a way: facing left uses the `_flipped` art when there is one.
function sheetFor(clip, facing, grid) {
    if (facing < 0 && grid[clip + "_flipped"]) return clip + "_flipped"
    return clip
}

// The box a clip is drawn in, from her square's top-left (ax, ay).
function box(clip, info, S, ax, ay, facing) {
    var f = family(clip)
    var tall = S * f.h
    var wide = info ? tall * info.cw / info.ch : tall * 0.6
    var sx = (facing < 0 ? -f.sx : f.sx) * S
    return { x: ax + S / 2 - wide / 2 + sx, y: ay + S / 2 - tall / 2 + f.sy * S, w: wide, h: tall }
}

// Her hip in the square: seated or standing, mirrored when she faces left.
function hipShare(seated, facing) {
    var p = seated ? SIT : STAND
    return { x: facing < 0 ? 1 - p.x : p.x, y: p.y }
}

function anchorFor(hipX, hipY, S, seated, facing) {
    var h = hipShare(seated, facing)
    return { x: hipX - h.x * S, y: hipY - h.y * S }
}

// Ledges on the visible workspace: window tops (floor: false) and the screen's floor.
// clients: `hyprctl -j clients`; ws: the active workspace id; floor: {x1, x2, y}.
function ledges(clients, ws, floor, S) {
    var found = [{ x1: floor.x1, x2: floor.x2, y: floor.y, win: "", floor: true }]
    for (var i = 0; i < clients.length; i++) {
        var c = clients[i]
        if (!c.mapped || c.hidden || c.fullscreen || !c.workspace || c.workspace.id !== ws) continue
        var x1 = c.at[0], x2 = c.at[0] + c.size[0], y = c.at[1]
        if (x2 - x1 < S * 0.6 || y - S * (SIT.y - PERCH_TOP) < 0) continue
        found.push({ x1: x1, x2: Math.min(x2, floor.x2), y: y, h: c.size[1], win: c.address, floor: false,
                     floating: !!c.floating, focus: c.focusHistoryID })
    }
    return found
}

// Is (x, ledge.y) hidden under another window that sits above this one?
function covered(ledge, x, all) {
    for (var i = 0; i < all.length; i++) {
        var o = all[i]
        if (o.floor || o.win === ledge.win) continue
        var above = (o.floating && !ledge.floating) || (o.floating === ledge.floating && o.focus < ledge.focus)
        if (!above) continue
        // other window's rectangle: from its top (o.y) down; its height isn't kept, so treat it as reaching the floor
        if (x >= o.x1 && x <= o.x2 && ledge.y > o.y && ledge.y < o.y + (o.h || 1e9)) return true
    }
    return false
}

// The ledge she lands on falling from (hx, hy): the nearest one below whose span holds her (with a margin) and
// that isn't covered there. The floor always catches her.
function below(all, hx, hy, S) {
    var best = null
    for (var i = 0; i < all.length; i++) {
        var l = all[i]
        if (l.y < hy - 2) continue
        if (hx < l.x1 + S * 0.15 || hx > l.x2 - S * 0.45) continue
        if (!l.floor && covered(l, hx, all)) continue
        if (!best || l.y < best.y) best = l
    }
    return best || all[0]
}

// A spot to stand or sit on a ledge, kept inside it (and off the screen's right edge, Lan Mouse's strip).
function clampX(l, x, S, screenRight) {
    if (l.free) return x
    var lo = l.x1 + S * 0.15
    var hi = Math.min(l.x2, screenRight - 12) - S * 0.45
    return hi < lo ? (l.x1 + l.x2) / 2 : Math.max(lo, Math.min(hi, x))
}

// Room to lie down from hip x facing a way: lying (head left) needs ledge behind her to the left.
function lieFacing(l, hx, S) {
    var reach = LIE_REACH * S
    if (hx - l.x1 >= reach) return 1
    if (l.x2 - hx >= reach) return -1
    return 0
}
