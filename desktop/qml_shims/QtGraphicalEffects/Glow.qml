// Qt 6 stand-in for Qt 5's QtGraphicalEffects Glow (desktop build only),
// using MultiEffect so the Mac app doesn't need the Qt5Compat add-on.
import QtQuick
import QtQuick.Effects
MultiEffect {
    property color color: "white"
    property int samples: 20
    property real spread: 0.3
    property real radius: 8
    shadowEnabled: true
    shadowColor: color
    shadowBlur: Math.min(1.0, samples / 32)
    shadowHorizontalOffset: 0
    shadowVerticalOffset: 0
    shadowScale: 1.0 + spread * 0.1
}
