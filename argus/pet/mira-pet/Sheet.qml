// One cell of one of Mira's gridded sprite sheets (build_sheets.py), drawn into this item's box.
// Two image layers swap: a new clip loads behind the one showing and takes over once it's ready, so changing between
// big sheets never flashes empty.
import QtQuick

Item {
    id: sheet

    property string folder: ""          // ".../grid/" with a trailing slash
    property var info: null             // grid.json entry: {frames, cols, rows, cw, ch}
    property string name: ""            // the clip (sheet) shown
    property int cell: 0
    property bool mirror: false
    readonly property bool ready: shown.status === Image.Ready && shown.clipName === name

    clip: true
    transform: Scale { origin.x: sheet.width / 2; xScale: sheet.mirror ? -1 : 1 }

    property Image shown: a
    property Image loading: b

    onNameChanged: load()
    Component.onCompleted: load()

    function load() {
        if (!name || !info) return
        if (shown.clipName === name && shown.status !== Image.Error) return
        loading.clipName = name
        loading.layout = info
        loading.source = folder + name + ".png"
        if (loading.status === Image.Ready) swap()
    }

    function swap() {
        const old = shown
        shown = loading
        loading = old
        shown.visible = true
        loading.visible = false
    }

    component Layer: Image {
        property string clipName: ""
        property var layout: null      // this layer's own grid entry: a swap never draws a cell with the other's layout
        readonly property int at: layout ? sheet.cell % layout.frames : 0
        readonly property int col: layout ? at % layout.cols : 0
        readonly property int row: layout ? Math.floor(at / layout.cols) : 0
        asynchronous: true
        cache: true
        smooth: true
        mipmap: true
        visible: false
        width: layout ? layout.cols * sheet.width : 0
        height: layout ? layout.rows * sheet.height : 0
        x: -col * sheet.width
        y: -row * sheet.height
        onStatusChanged: if (status === Image.Ready && this === sheet.loading && clipName === sheet.name) sheet.swap()
    }

    Layer { id: a }
    Layer { id: b }
}
