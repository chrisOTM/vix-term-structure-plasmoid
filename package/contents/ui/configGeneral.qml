import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.FormLayout {
    id: page

    property alias cfg_refreshIntervalMinutes: refreshInterval.value
    property alias cfg_showValuesOnChart: showValues.checked
    property alias cfg_showTable: showTable.checked
    property alias cfg_showPercentiles: showPercentiles.checked
    property alias cfg_marginWarnThreshold: marginWarn.value
    property alias cfg_marginCriticalThreshold: marginCritical.value

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
