import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents3

RowLayout {
    id: statusBar

    property string status: "loading"
    property string lastSuccessfulUpdate: ""
    property string curveState: "Unknown"
    property int refreshIntervalMinutes: 15
    property string errorMessage: ""
    property real maxMarginUsage: -1

    spacing: Kirigami.Units.smallSpacing * 2

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
            ? i18n("Updated: %1", statusBar.lastSuccessfulUpdate)
            : i18n("No data yet")
        elide: Text.ElideRight
        Layout.fillWidth: true
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
            if (statusBar.maxMarginUsage < 0)   return Kirigami.Theme.disabledTextColor
            if (statusBar.maxMarginUsage >= 50) return Kirigami.Theme.negativeTextColor
            if (statusBar.maxMarginUsage >= 30) return Kirigami.Theme.neutralTextColor
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
            if (statusBar.maxMarginUsage < 0)   return Kirigami.Theme.disabledTextColor
            if (statusBar.maxMarginUsage >= 50) return Kirigami.Theme.negativeTextColor
            if (statusBar.maxMarginUsage >= 30) return Kirigami.Theme.neutralTextColor
            return Kirigami.Theme.positiveTextColor
        }
    }
}
