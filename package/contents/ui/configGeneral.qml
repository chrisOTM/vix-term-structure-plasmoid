import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.FormLayout {
    id: page

    property string cfg_market: "vix"
    property alias cfg_refreshIntervalMinutes: refreshInterval.value
    property alias cfg_showValuesOnChart: showValues.checked
    property alias cfg_showTable: showTable.checked
    property alias cfg_showPercentiles: showPercentiles.checked
    property alias cfg_showTrendArrows: showTrendArrows.checked
    property alias cfg_marginWarnThreshold: marginWarn.value
    property alias cfg_marginCriticalThreshold: marginCritical.value

    QQC2.ComboBox {
        id: marketCombo
        Kirigami.FormData.label: i18n("Market:")
        textRole: "text"
        valueRole: "value"
        model: [
            { value: "vix",    text: i18n("VIX — S&P 500 (Yahoo Finance)") },
            { value: "vstoxx", text: i18n("VSTOXX — EURO STOXX 50 (STOXX, delayed)") }
        ]

        Component.onCompleted: currentIndex = Math.max(0, indexOfValue(page.cfg_market))
        onActivated: page.cfg_market = currentValue

        // The config loader may assign cfg_market after this page is built.
        Connections {
            target: page
            function onCfg_marketChanged() {
                marketCombo.currentIndex = Math.max(0, marketCombo.indexOfValue(page.cfg_market))
            }
        }
    }

    QQC2.SpinBox {
        id: refreshInterval
        Kirigami.FormData.label: i18n("Refresh interval in minutes:")
        from: 1
        to: 1440
        value: 15
    }

    QQC2.CheckBox {
        id: showValues
        text: i18n("Show values on chart")
    }

    QQC2.CheckBox {
        id: showTable
        text: i18n("Show table")
    }

    QQC2.CheckBox {
        id: showPercentiles
        text: i18n("Show percentile ranks")
        checked: true
    }

    QQC2.CheckBox {
        id: showTrendArrows
        text: i18n("Show trend arrows (vs. previous close)")
        checked: true
    }

    Item {
        Kirigami.FormData.isSection: true
    }

    QQC2.SpinBox {
        id: marginWarn
        Kirigami.FormData.label: i18n("Margin warning threshold (%):")
        from: 0
        // darf critical nicht überschreiten
        to: marginCritical.value
        value: 30
    }

    QQC2.SpinBox {
        id: marginCritical
        Kirigami.FormData.label: i18n("Margin critical threshold (%):")
        // darf warning nicht unterschreiten
        from: marginWarn.value
        to: 100
        value: 50
    }
}
