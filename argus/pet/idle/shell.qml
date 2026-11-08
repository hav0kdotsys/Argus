// MIRA's idle signal on laphvk (2026-11-08): how long Hannah's input has been idle, for her body and companion.
// Wayland gives a plain process no idle time, and her Linux body (mira-body's cross build) only knows GNOME's and X11's,
// so on Hyprland it read her as never idle: from the 3 Nov cutover her companion counted one sitting of 87 hours and
// its check-ins escalated. Her retired Quickshell body had this IdleMonitor; this keeps just that part.
//
// Writes ~/.argus/companion/idle.json: {"idle_since": <unix s> | null, "at": <unix s>} on every change and every 30 s
// (so a reader can tell it's alive). Input, not the screensaver: a paused video's idle inhibitor would keep her
// looking present all night, so inhibitors are ignored.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
    id: root
    property var since: null

    function write() {
        root.since = idle.isIdle ? (root.since || Math.floor(Date.now() / 1000) - idle.timeout) : null
        out.setText(JSON.stringify({ idle_since: root.since, at: Math.floor(Date.now() / 1000) }))
    }

    IdleMonitor {
        id: idle
        timeout: 60
        respectInhibitors: false
        onIsIdleChanged: root.write()
    }

    FileView {
        id: out
        path: Quickshell.env("HOME") + "/.argus/companion/idle.json"
    }

    Timer { interval: 30000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.write() }
}
