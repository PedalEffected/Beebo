// Desktop stand-in for the pedal's on-screen keyboard: a computer has a real
// keyboard, so the panel is never shown.
import QtQuick 2.0
Item {
    property bool active: false
    visible: false
    height: 0
}
