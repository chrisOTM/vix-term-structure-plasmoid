import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as Plasma5Support

PlasmoidItem {
    id: root

    Plasmoid.title: i18n("VIX Term Structure")
    Plasmoid.icon: "office-chart-line"
    toolTipMainText: Plasmoid.title
    toolTipSubText: i18n("VIX cash term structure via Yahoo Finance")

    // State
    property var    points:               []
    property var    lastSuccessfulPoints: []
    property string status:               "loading"
    property string errorMessage:         ""
    property string lastUpdate:           ""
    property string lastSuccessfulUpdate: ""
    property string curveState:           "Unknown"
    property bool   isRefreshing:         false
    property int    refreshIntervalMinutes: Math.max(1, plasmoid.configuration.refreshIntervalMinutes)

    readonly property string compactLabel: {
        var vix = lastSuccessfulPoints.find(function(p) { return p.label === "30D" })
        return vix ? vix.value.toFixed(1) : "—"
    }

    // ── Compact representation (panel) ──────────────────────────────────────
    compactRepresentation: Item {
        implicitWidth:  Math.round(Kirigami.Units.gridUnit * 2)
        implicitHeight: Math.round(Kirigami.Units.gridUnit * 2)

        MouseArea {
            anchors.fill: parent
            onClicked: plasmoid.expanded = !plasmoid.expanded
        }

        ColumnLayout {
            anchors.centerIn: parent
            spacing: 0

            PlasmaComponents3.Label {
                Layout.alignment: Qt.AlignHCenter
                text: root.compactLabel
                font.pointSize: Kirigami.Units.gridUnit * 0.9
                color: {
                    switch (root.status) {
                        case "error":   return Kirigami.Theme.negativeTextColor
                        case "partial": return Kirigami.Theme.neutralTextColor
                        default:        return Kirigami.Theme.textColor
                    }
                }
            }

            PlasmaComponents3.Label {
                Layout.alignment: Qt.AlignHCenter
                text: "VIX"
                font.pointSize: Kirigami.Units.gridUnit * 0.55
                color: Kirigami.Theme.disabledTextColor
            }
        }
    }

    // ── Full representation ──────────────────────────────────────────────────
    fullRepresentation: Item {
        Layout.minimumWidth:   Kirigami.Units.gridUnit * 16
        Layout.minimumHeight:  Kirigami.Units.gridUnit * 12
        Layout.preferredWidth:  Kirigami.Units.gridUnit * 22
        Layout.preferredHeight: Kirigami.Units.gridUnit * 18

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.smallSpacing * 2
            spacing: Kirigami.Units.smallSpacing

            // Header
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.Label {
                    text: i18n("VIX Term Structure")
                    font.bold: true
                    Layout.fillWidth: true
                }

                PlasmaComponents3.Label {
                    text: {
                        switch (root.curveState) {
                            case "Contango":      return i18n("Contango")
                            case "Backwardation": return i18n("Backwardation")
                            case "Flat":          return i18n("Flat")
                            default:              return i18n("Unknown")
                        }
                    }
                    color: {
                        switch (root.curveState) {
                            case "Backwardation": return Kirigami.Theme.negativeTextColor
                            case "Unknown":       return Kirigami.Theme.disabledTextColor
                            default:              return Kirigami.Theme.textColor
                        }
                    }
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                }

                PlasmaComponents3.ToolButton {
                    icon.name: "view-refresh"
                    enabled: !root.isRefreshing
                    onClicked: root.fetchData()
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.text: i18n("Refresh data")
                }
            }

            // Error message
            PlasmaComponents3.Label {
                Layout.fillWidth: true
                visible: root.status === "error" && root.errorMessage.length > 0
                text: root.errorMessage
                color: Kirigami.Theme.negativeTextColor
                wrapMode: Text.WordWrap
                font.pointSize: Kirigami.Theme.smallFont.pointSize
            }

            // Chart
            ChartView {
                id: chartView
                Layout.fillWidth: true
                Layout.fillHeight: true
                points: root.lastSuccessfulPoints.length > 0 ? root.lastSuccessfulPoints : root.points
                showValues: plasmoid.configuration.showValuesOnChart
            }

            // Table (optional) — horizontal row
            ColumnLayout {
                id: tableSection
                Layout.fillWidth: true
                visible: plasmoid.configuration.showTable && root.lastSuccessfulPoints.length > 0
                spacing: Kirigami.Units.smallSpacing / 2

                // Header
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    PlasmaComponents3.Label {
                        text: i18n("Label")
                        font.bold: true
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        color: Kirigami.Theme.disabledTextColor
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 2
                    }
                    PlasmaComponents3.Label {
                        text: i18n("Value")
                        font.bold: true
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        color: Kirigami.Theme.disabledTextColor
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 3
                    }
                    PlasmaComponents3.Label {
                        text: i18n("Pctl")
                        font.bold: true
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        color: Kirigami.Theme.disabledTextColor
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 2
                        visible: plasmoid.configuration.showPercentiles
                    }
                }

                // Data rows
                Repeater {
                    model: root.lastSuccessfulPoints

                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        PlasmaComponents3.Label {
                            text: modelData.label + ":"
                            color: Kirigami.Theme.disabledTextColor
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 2
                        }
                        PlasmaComponents3.Label {
                            text: modelData.value.toFixed(2)
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 3
                        }
                        PlasmaComponents3.Label {
                            text: {
                                if (modelData.percentile === undefined || modelData.percentile === null)
                                    return "—"
                                return Math.round(modelData.percentile) + "%"
                            }
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 2
                            visible: plasmoid.configuration.showPercentiles
                            color: {
                                if (modelData.percentile === undefined || modelData.percentile === null)
                                    return Kirigami.Theme.disabledTextColor
                                var pctl = modelData.percentile
                                if (pctl <= 10 || pctl >= 90)
                                    return Kirigami.Theme.negativeTextColor
                                if (pctl <= 25 || pctl >= 75)
                                    return Kirigami.Theme.neutralTextColor
                                return Kirigami.Theme.textColor
                            }
                        }
                    }
                }
            }

            // Status bar
            StatusBar {
                Layout.fillWidth: true
                status: root.status
                lastSuccessfulUpdate: root.lastSuccessfulUpdate
                curveState: root.curveState
                refreshIntervalMinutes: root.refreshIntervalMinutes
                errorMessage: root.errorMessage
            }
        }
    }

    // ── Data source ──────────────────────────────────────────────────────────
    Plasma5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []

        onNewData: function(sourceName, data) {
            executable.disconnectSource(sourceName)
            var stdout   = data["stdout"]   || ""
            var stderr   = data["stderr"]   || ""
            var exitCode = data["exit code"] !== undefined ? data["exit code"] : -1
            handleFetcherOutput(stdout, stderr, exitCode)
        }
    }

    // ── Timer ────────────────────────────────────────────────────────────────
    Timer {
        id: refreshTimer
        interval: root.refreshIntervalMinutes * 60 * 1000
        repeat: true
        running: root.visible
        onTriggered: fetchData()
    }

    // ── Fetch timeout (fängt stumme Fehler, wenn der Subprozess nie antwortet) ─
    Timer {
        id: fetchTimeout
        interval: 30000
        repeat: false
        onTriggered: {
            root.isRefreshing = false
            root.status = "error"
            root.errorMessage = i18n("Fetcher did not respond within 30s. Check that python3 and yfinance are installed.")
        }
    }

    // ── Config change reactivity ─────────────────────────────────────────────
    Connections {
        target: plasmoid.configuration
        function onRefreshIntervalMinutesChanged() {
            root.refreshIntervalMinutes = Math.max(1, plasmoid.configuration.refreshIntervalMinutes)
            refreshTimer.interval = root.refreshIntervalMinutes * 60 * 1000
            refreshTimer.restart()
        }
    }

    // ── Lifecycle ────────────────────────────────────────────────────────────
    Component.onCompleted: {
        root.refreshIntervalMinutes = Math.max(1, plasmoid.configuration.refreshIntervalMinutes)
        fetchData()
        refreshTimer.start()
    }

    onExpandedChanged: {
        if (plasmoid.expanded) {
            fetchData()
        }
    }

    // ── Functions ────────────────────────────────────────────────────────────
    function quoteShell(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'"
    }

    function fetchData() {
        if (root.isRefreshing) {
            return
        }
        root.isRefreshing = true
        root.status = root.lastSuccessfulPoints.length > 0 ? "refreshing" : "loading"
        fetchTimeout.stop()

        var scriptUrl = Qt.resolvedUrl("../code/fetch_vix.py")
        var script    = scriptUrl.toString().replace(/^file:\/\//, "")
        var command   = quoteShell(script) + " --timeout 10"
        executable.connectSource(command)
        fetchTimeout.start()
    }

    function formatErrors(errors) {
        if (!errors || errors.length === 0) return ""
        return errors.map(function(e) {
            return e.ticker ? (e.ticker + ": " + e.message) : e.message
        }).join(", ")
    }

    function handleFetcherOutput(stdout, stderr, exitCode) {
        root.isRefreshing = false
        fetchTimeout.stop()

        if (!stdout || stdout.trim().length === 0) {
            root.status       = "error"
            root.errorMessage = stderr && stderr.length > 0
                ? stderr
                : i18n("Fetcher returned no JSON output")
            return
        }

        try {
            var result = JSON.parse(stdout)

            if (result.status === "ok" || result.status === "partial") {
                root.points     = result.points       || []
                root.curveState = result.curve_state  || "Unknown"
                root.lastUpdate = result.timestamp    || ""

                if (root.points.length > 0) {
                    root.lastSuccessfulPoints = root.points
                    root.lastSuccessfulUpdate = root.lastUpdate
                }

                root.status       = result.status
                root.errorMessage = formatErrors(result.errors || [])
                return
            }

            root.status       = "error"
            root.errorMessage = formatErrors(result.errors || [])
                || i18n("Could not fetch data")
        } catch (e) {
            root.status       = "error"
            root.errorMessage = i18n("Could not parse fetcher JSON: %1", e)
        }
    }
}
