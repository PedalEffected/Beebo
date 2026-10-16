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
    // screen to fit it, keeping its shape.
    readonly property bool isDesktop: beeboPaths.isDesktop
    readonly property real fitScale: isDesktop ? Math.min(width / 1280, height / 720) : 1
    color: "black"
    Item {
        transform: [
            Rotation {
                angle: flip_screen ? 180 : 0
                origin.x: (!flip_screen ? 720 : 1280) / 2
                origin.y: (flip_screen ? 720 : 1280) / 2
            },
            Scale { xScale: fitScale; yScale: fitScale }
        ]
        x: isDesktop ? (parent.width - 1280 * fitScale) / 2 : 0
        y: isDesktop ? (parent.height - 720 * fitScale) / 2 : 0
        width: 1280//Screen.height
        height: 720//Screen.wid
        StackView {
            id: mainStack
            initialItem: mainView
        }
    }
}
