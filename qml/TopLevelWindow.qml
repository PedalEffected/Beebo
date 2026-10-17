import "controls" as PolyControls

import QtQuick 2.4
import QtQuick.Window 2.2
import QtQuick.Controls 2.3
import QtQuick.Controls.Material 2.3

import "polyconst.js" as Constants

ApplicationWindow {
    id: beeboWindow
    // Screens pushed onto mainStack (module browser, presets, ...) refer to
    // the patch bay and footer by name. Qt 5 found them through the screen
    // that opened them; Qt 6 only looks here, so publish them on the window.
    property var patch_single: null
    property var title_footer: null

    Material.theme: Material.Dark
    Material.primary: Constants.cv_color
    Material.accent: accent_color.name
    Material.background: "black"
    // Material.buttonColor: "grey"
    // contentOrientation: 
    
    property bool onDevice: false // Qt.platform.os == "linux" 
    readonly property int baseFontSize: 20 
    readonly property int tabHeight: 60 
    readonly property int fontSizeExtraSmall: baseFontSize * 0.8
    readonly property int fontSizeMedium: baseFontSize * 1.5
    readonly property int fontSizeLarge: baseFontSize * 2
    readonly property int fontSizeExtraLarge: baseFontSize * 5
    property int presetBrowserIndex: 0
    property bool flip_screen: Boolean(pedalState["screen_flipped"])
    property bool interconnect: false
    contentOrientation: flip_screen ? Qt.InvertedPortraitOrientation : Qt.PortraitOrientation
    width: 1280 
    height: 720
    title: isDesktop ? "Beebo" : "Digit 2"
    minimumWidth: isDesktop ? 640 : 0
    minimumHeight: isDesktop ? 360 : 0
    visible: true
    FontLoader { id: docFont; source: "fonts/BarlowSemiCondensed-Medium.ttf" }
    FontLoader { id: mainFont; source: "fonts/BarlowSemiCondensed-SemiBold.ttf" }
    font.family: mainFont.name
    font.weight: Font.DemiBold
    Component {
        id: mainView
        TitleFooter {
        }

    }
    // On a desktop the window can be resized: scale the 1280 x 720 pedal
    // screen to fit it, keeping its shape. A zoom slider (desktopUI.zoom,
    // 1.0 = fit) can enlarge or shrink it further; scroll bars appear when
    // it's larger than the window.
    readonly property bool isDesktop: beeboPaths.isDesktop
    readonly property bool hasZoom: isDesktop && typeof desktopUI !== "undefined" && desktopUI !== null
    readonly property int toolbarHeight: hasZoom ? 40 : 0
    readonly property real zoom: hasZoom ? desktopUI.zoom : 1
    readonly property real fitScale: isDesktop ? Math.min(width / 1280, (height - toolbarHeight) / 720) : 1
    readonly property real viewScale: fitScale * zoom
    property real lastViewScale: 1
    // keep the same spot in the middle of the view while zooming
    onViewScaleChanged: {
        if (hasZoom && lastViewScale > 0) {
            var cx = (zoomView.contentX + zoomView.width / 2) / lastViewScale;
            var cy = (zoomView.contentY + zoomView.height / 2) / lastViewScale;
            zoomView.contentX = Math.max(0, Math.min(cx * viewScale - zoomView.width / 2,
                                                     zoomView.contentWidth - zoomView.width));
            zoomView.contentY = Math.max(0, Math.min(cy * viewScale - zoomView.height / 2,
                                                     zoomView.contentHeight - zoomView.height));
        }
        lastViewScale = viewScale;
    }
    color: "black"

    Rectangle {
        id: zoomBar
        visible: hasZoom
        width: parent.width
        height: toolbarHeight
        color: "#111111"
        Row {
            anchors.centerIn: parent
            spacing: 10
            Rectangle {
                width: 30; height: 26; radius: 4; color: "#2a2a2a"
                anchors.verticalCenter: parent.verticalCenter
                Text { anchors.centerIn: parent; text: "\u2212"; color: "white"; font.pixelSize: 20 }
                MouseArea { anchors.fill: parent; onClicked: desktopUI.zoomOut() }
            }
            // a plain slider (the pedal's own slider style shows its raw value)
            Item {
                id: zoomSlider
                width: Math.min(360, beeboWindow.width * 0.4)
                height: 26
                anchors.verticalCenter: parent.verticalCenter
                readonly property real lo: hasZoom ? desktopUI.zoomMin : 0.5
                readonly property real hi: hasZoom ? desktopUI.zoomMax : 3
                readonly property real pos: (zoom - lo) / (hi - lo)
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width; height: 4; radius: 2
                    color: "#555555"
                    Rectangle { width: parent.width * zoomSlider.pos; height: parent.height; radius: 2; color: Constants.cv_color }
                }
                Rectangle {   // where "Fit" is
                    x: parent.width * (1 - zoomSlider.lo) / (zoomSlider.hi - zoomSlider.lo) - 1
                    anchors.verticalCenter: parent.verticalCenter
                    width: 2; height: 12; color: "#888888"
                }
                Rectangle {
                    x: parent.width * zoomSlider.pos - width / 2
                    anchors.verticalCenter: parent.verticalCenter
                    width: 18; height: 18; radius: 9
                    color: "white"
                }
                MouseArea {
                    anchors.fill: parent
                    function setFrom(mx) {
                        var f = Math.max(0, Math.min(1, mx / width));
                        desktopUI.zoom = Math.round((zoomSlider.lo + f * (zoomSlider.hi - zoomSlider.lo)) * 20) / 20;
                    }
                    onPressed: setFrom(mouse.x)
                    onPositionChanged: setFrom(mouse.x)
                }
            }
            Rectangle {
                width: 30; height: 26; radius: 4; color: "#2a2a2a"
                anchors.verticalCenter: parent.verticalCenter
                Text { anchors.centerIn: parent; text: "+"; color: "white"; font.pixelSize: 20 }
                MouseArea { anchors.fill: parent; onClicked: desktopUI.zoomIn() }
            }
            Text {
                width: 56
                anchors.verticalCenter: parent.verticalCenter
                text: Math.round(zoom * 100) + "%"
                color: "white"
                font.pixelSize: 16
                horizontalAlignment: Text.AlignHCenter
            }
            Rectangle {
                width: 46; height: 26; radius: 4; color: "#2a2a2a"
                anchors.verticalCenter: parent.verticalCenter
                Text { anchors.centerIn: parent; text: "Fit"; color: "white"; font.pixelSize: 16 }
                MouseArea { anchors.fill: parent; onClicked: desktopUI.zoomFit() }
            }
        }
    }

    Flickable {
        id: zoomView
        y: toolbarHeight
        width: parent.width
        height: parent.height - toolbarHeight
        contentWidth: Math.max(width, 1280 * viewScale)
        contentHeight: Math.max(height, 720 * viewScale)
        // dragging belongs to the patch bay (moving modules), so pan with
        // the scroll bars, the scroll wheel or a two-finger swipe
        interactive: false
        clip: hasZoom
        ScrollBar.horizontal: ScrollBar {
            policy: zoomView.contentWidth > zoomView.width + 1 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
        }
        ScrollBar.vertical: ScrollBar {
            policy: zoomView.contentHeight > zoomView.height + 1 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
        }

        Item {
            transform: [
                Rotation {
                    angle: flip_screen ? 180 : 0
                    origin.x: (!flip_screen ? 720 : 1280) / 2
                    origin.y: (flip_screen ? 720 : 1280) / 2
                },
                Scale { xScale: viewScale; yScale: viewScale }
            ]
            x: isDesktop ? Math.max(0, (zoomView.width - 1280 * viewScale) / 2) : 0
            y: isDesktop ? Math.max(0, (zoomView.height - 720 * viewScale) / 2) : 0
            width: 1280//Screen.height
            height: 720//Screen.wid
            StackView {
                id: mainStack
                initialItem: mainView
            }
        }
    }

    // scroll wheel / trackpad: pan when zoomed in; with Command held, zoom
    MouseArea {
        visible: hasZoom
        y: toolbarHeight
        width: parent.width
        height: parent.height - toolbarHeight
        acceptedButtons: Qt.NoButton
        onWheel: {
            if (wheel.modifiers & Qt.ControlModifier) {
                if (wheel.angleDelta.y > 0) desktopUI.zoomIn();
                else if (wheel.angleDelta.y < 0) desktopUI.zoomOut();
                return;
            }
            // not zoomed in: let lists underneath (module browser, ...) scroll
            if (zoomView.contentWidth <= zoomView.width + 1 && zoomView.contentHeight <= zoomView.height + 1) {
                wheel.accepted = false;
                return;
            }
            var dx = wheel.pixelDelta.x !== 0 ? wheel.pixelDelta.x : wheel.angleDelta.x / 4;
            var dy = wheel.pixelDelta.y !== 0 ? wheel.pixelDelta.y : wheel.angleDelta.y / 4;
            zoomView.contentX = Math.max(0, Math.min(zoomView.contentX - dx,
                                                     zoomView.contentWidth - zoomView.width));
            zoomView.contentY = Math.max(0, Math.min(zoomView.contentY - dy,
                                                     zoomView.contentHeight - zoomView.height));
        }
    }
}
