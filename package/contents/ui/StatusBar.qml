import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents3

RowLayout {
    id: statusBar

    property string status: "loading"
    property string lastSuccessfulUpdate: ""
    // Data source incl. the vendor's data date, e.g. "STOXX (delayed) · 2026-08-14"
    property string dataSource: ""
    property string curveState: "Unknown"
    property int refreshIntervalMinutes: 15
    property string errorMessage: ""
    property real maxMarginUsage: -1
    property int marginWarnThreshold: 30
    property int marginCriticalThreshold: 50

    spacing: Kirigami.Units.smallSpacing * 2

    // Format the backend ISO timestamp (e.g. "2026-06-11T15:30:45+02:00")
    // for display: localized weekday + day + short month + 24h time,
    // e.g. "Do 11 Jun, 15:30". Falls back to the raw string if unparseable.
    function formatTimestamp(iso) {
        var d = new Date(iso)
        if (isNaN(d.getTime()))
            return iso
        return d.toLocaleString(Qt.locale(), "ddd dd MMM, HH:mm")
    }

    PlasmaComponents3.Label {
        id: statusLabel
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        color: {
            switch (statusBar.status) {
                case "ok":        return Kirigami.Theme.positiveTextColor
                case "partial":   return Kirigami.Theme.neutralTextColor
                case "error":     return Kirigami.Theme.negativeTextColor
                case "loading":   return Kirigami.Theme.disabledTextColor
                case "refreshing": return Kirigami.Theme.disabledTextColor
                default:          return Kirigami.Theme.disabledTextColor
            }
        }
        text: {
            switch (statusBar.status) {
                case "ok":        return i18n("OK")
                case "partial":   return i18n("Partial")
                case "error":     return i18n("Error")
                case "loading":   return i18n("Loading…")
                case "refreshing": return i18n("Refreshing…")
                default:          return i18n("Unknown")
            }
        }
    }

    PlasmaComponents3.Label {
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        color: Kirigami.Theme.disabledTextColor
        text: "|"
    }

    PlasmaComponents3.Label {
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        color: Kirigami.Theme.disabledTextColor
        text: statusBar.lastSuccessfulUpdate.length > 0
            ? i18n("Updated: %1", statusBar.formatTimestamp(statusBar.lastSuccessfulUpdate))
            : i18n("No data yet")
        elide: Text.ElideRight
        Layout.fillWidth: true

        // The fetch time is not the data time: VSTOXX is a delayed feed, so
        // the source line carries the vendor's own data date.
        QQC2.ToolTip.visible: sourceHover.hovered && statusBar.dataSource.length > 0
        QQC2.ToolTip.text: i18n("Source: %1", statusBar.dataSource)

        HoverHandler { id: sourceHover }
    }

    PlasmaComponents3.Label {
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        color: Kirigami.Theme.disabledTextColor
        text: "|"
    }

    PlasmaComponents3.Label {
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        color: Kirigami.Theme.disabledTextColor
        text: i18n("%1 min", statusBar.refreshIntervalMinutes)
    }

    PlasmaComponents3.Label {
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        color: Kirigami.Theme.disabledTextColor
        text: "|"
    }

    PlasmaComponents3.Label {
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        text: statusBar.maxMarginUsage >= 0
            ? i18n("Margin: %1%", statusBar.maxMarginUsage.toFixed(1))
            : i18n("Margin: —")
        color: {
            if (statusBar.maxMarginUsage < 0)                              return Kirigami.Theme.disabledTextColor
            if (statusBar.maxMarginUsage >= statusBar.marginCriticalThreshold) return Kirigami.Theme.negativeTextColor
            if (statusBar.maxMarginUsage >= statusBar.marginWarnThreshold)     return Kirigami.Theme.neutralTextColor
            return Kirigami.Theme.textColor
        }
    }

    PlasmaComponents3.Label {
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        color: Kirigami.Theme.disabledTextColor
        text: "|"
    }

    // Cushion = ungenutzter Puffer = 100% − Margin-Auslastung
    PlasmaComponents3.Label {
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        text: statusBar.maxMarginUsage >= 0
            ? i18n("Cushion: %1%", (100 - statusBar.maxMarginUsage).toFixed(1))
            : i18n("Cushion: —")
        color: {
            if (statusBar.maxMarginUsage < 0)                              return Kirigami.Theme.disabledTextColor
            if (statusBar.maxMarginUsage >= statusBar.marginCriticalThreshold) return Kirigami.Theme.negativeTextColor
            if (statusBar.maxMarginUsage >= statusBar.marginWarnThreshold)     return Kirigami.Theme.neutralTextColor
            return Kirigami.Theme.positiveTextColor
        }
    }
}
