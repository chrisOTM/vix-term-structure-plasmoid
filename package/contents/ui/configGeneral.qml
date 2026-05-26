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
}
