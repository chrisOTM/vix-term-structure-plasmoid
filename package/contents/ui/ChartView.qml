import QtQuick
import org.kde.kirigami as Kirigami

Canvas {
    id: chart

    property var points: []
    property bool showValues: true

    onPointsChanged: requestPaint()
    onShowValuesChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)

        if (!points || points.length === 0) {
            _drawEmpty(ctx)
            return
        }

        var pad = Kirigami.Units.gridUnit
        var padLeft = pad * 2.5
        var padRight = pad
        var padTop = pad
        var padBottom = pad * 1.8

        var values = points.map(function(p) { return p.value })
        var minVal = Math.min.apply(null, values)
        var maxVal = Math.max.apply(null, values)
        var range = maxVal - minVal
        if (range < 0.5) {
            var mid = (minVal + maxVal) / 2
            minVal = mid - 0.5
            maxVal = mid + 0.5
            range = 1.0
        }
        minVal -= range * 0.1
        maxVal += range * 0.1
        range = maxVal - minVal

        var chartW = width - padLeft - padRight
        var chartH = height - padTop - padBottom

        function xAt(i) {
            return padLeft + (i / (points.length - 1)) * chartW
        }
        function yAt(v) {
            return padTop + chartH - ((v - minVal) / range) * chartH
        }

        // Y-axis grid lines and labels
        var ySteps = 4
        ctx.strokeStyle = Kirigami.Theme.textColor
        ctx.globalAlpha = 0.12
        ctx.lineWidth = 1
        for (var s = 0; s <= ySteps; s++) {
            var yVal = minVal + (range / ySteps) * s
            var yPx = yAt(yVal)
            ctx.beginPath()
            ctx.moveTo(padLeft, yPx)
            ctx.lineTo(width - padRight, yPx)
            ctx.stroke()
        }
        ctx.globalAlpha = 1.0

        ctx.fillStyle = Kirigami.Theme.disabledTextColor
        ctx.font = Math.max(Kirigami.Units.gridUnit * 0.75, 9) + "px sans-serif"
        ctx.textAlign = "right"
        ctx.textBaseline = "middle"
        for (var s2 = 0; s2 <= ySteps; s2++) {
            var yVal2 = minVal + (range / ySteps) * s2
            var yPx2 = yAt(yVal2)
            ctx.fillText(yVal2.toFixed(1), padLeft - Kirigami.Units.smallSpacing, yPx2)
        }

        // Line
        ctx.beginPath()
        ctx.moveTo(xAt(0), yAt(points[0].value))
        for (var i = 1; i < points.length; i++) {
            ctx.lineTo(xAt(i), yAt(points[i].value))
        }
        ctx.strokeStyle = Kirigami.Theme.highlightColor
        ctx.lineWidth = 2
        ctx.globalAlpha = 1.0
        ctx.stroke()

        // Points, labels, values
        var dotR = Kirigami.Units.smallSpacing * 1.5
        var fontSize = Math.max(Kirigami.Units.gridUnit * 0.75, 9)
        ctx.font = fontSize + "px sans-serif"

        for (var j = 0; j < points.length; j++) {
            var px = xAt(j)
            var py = yAt(points[j].value)

            ctx.beginPath()
            ctx.arc(px, py, dotR, 0, Math.PI * 2)
            ctx.fillStyle = Kirigami.Theme.highlightColor
            ctx.fill()
            ctx.strokeStyle = Kirigami.Theme.backgroundColor
            ctx.lineWidth = 1.5
            ctx.stroke()

            // X-axis label
            ctx.fillStyle = Kirigami.Theme.disabledTextColor
            ctx.textAlign = "center"
            ctx.textBaseline = "top"
            ctx.fillText(points[j].label, px, height - padBottom + Kirigami.Units.smallSpacing)

            // Value near point
            if (showValues) {
                ctx.fillStyle = Kirigami.Theme.textColor
                ctx.textBaseline = "bottom"
                ctx.fillText(points[j].value.toFixed(1), px, py - dotR - Kirigami.Units.smallSpacing)
            }
        }
    }

    function _drawEmpty(ctx) {
        ctx.fillStyle = Kirigami.Theme.disabledTextColor
        ctx.font = Kirigami.Units.gridUnit + "px sans-serif"
        ctx.textAlign = "center"
        ctx.textBaseline = "middle"
        ctx.fillText(i18n("No data"), width / 2, height / 2)
    }
}
