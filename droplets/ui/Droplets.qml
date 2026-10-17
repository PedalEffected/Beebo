// Droplets - granular texture processor / delay (Beads engine) for Beebo / Hector.
// Three pages, in the style of Poly's Rings screen:
//   Main      the eight front-panel controls
//   Modulate  attenuverters (CV amount, or random wander when no CV is patched),
//             freeze, seed button and seed lock
//   Setup     quality (tape / digital), mono input, input gain, synth mode,
//             gate on the right output
// Sliders are Poly's DelayRow, so "hold the three dots and touch a slider"
// opens the type-a-value screen as in every other module.
import "controls" as PolyControls
import QtQuick 2.4
import QtQuick.Controls 2.3
import QtQuick.Controls.Material 2.3
import "../qml/polyconst.js" as Constants
import "module_info.js" as ModuleInfo

Item {
    id: droplets
    property string effect_id: "none"
    property string effect_type: "Droplets"
    property int tab_index: 0
    z: 3
    height: 540
    width: 1280

    Component.onCompleted: knobs.set_broadcast(effect_id, true)
    Component.onDestruction: knobs.set_broadcast(effect_id, false)

    function v_type(p) {
        var c = ModuleInfo.effectPrototypes[effect_type]["controls"][p];
        return c.length > 4 ? c[4] : "float";
    }

    // --------------------------------------------------------- page buttons
    Column {
        x: 25
        y: 30
        width: 223
        spacing: 15
        Repeater {
            model: ["Main", "Modulate", "Setup"]
            PolyControls.Button {
                height: 141
                width: 150
                checked: droplets.tab_index == index
                onClicked: droplets.tab_index = index
                contentItem: Text {
                    text: modelData
                    color: parent.checked ? Constants.background_color : "white"
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.WordWrap
                    font { pixelSize: 24; capitalization: Font.AllUppercase }
                }
                background: Rectangle {
                    color: parent.checked ? Constants.poly_blue : Constants.poly_dark_grey
                    radius: 20
                }
            }
        }
    }

    // ---------------------------------------------------------------- Main
    Grid {
        visible: droplets.tab_index == 0
        x: 200
        y: 40
        columns: 2
        spacing: 24
        Repeater {
            model: ["time", "size", "shape", "density", "pitch", "feedback", "dry_wet", "reverb"]
            DelayRow {
                row_param: modelData
                current_effect: droplets.effect_id
                v_type: droplets.v_type(modelData)
                Material.foreground: Constants.rainbow[index]
            }
        }
    }

    // ------------------------------------------------------------ Modulate
    Item {
        visible: droplets.tab_index == 1
        x: 200
        y: 40
        width: 1050
        height: 480

        Grid {
            columns: 2
            spacing: 24
            Repeater {
                model: ["time_amt", "size_amt", "shape_amt", "pitch_amt", "freeze", "seed_lock"]
                DelayRow {
                    row_param: modelData
                    current_effect: droplets.effect_id
                    v_type: droplets.v_type(modelData)
                    Material.foreground: Constants.rainbow[index + 8]
                }
            }
        }

        // SEED button: momentary, like the module's button
        PolyControls.Button {
            id: seedButton
            y: 280
            width: 472
            height: 110
            onPressedChanged: knobs.ui_knob_change(droplets.effect_id, "seed_button", pressed ? 1.0 : 0.0)
            contentItem: Text {
                text: "SEED"
                color: seedButton.pressed ? Constants.background_color : "white"
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                font { pixelSize: 32; capitalization: Font.AllUppercase }
            }
            background: Rectangle {
                color: seedButton.pressed ? Constants.poly_pink : Constants.poly_dark_grey
                radius: 20
            }
        }
        Text {
            x: 496
            y: 280
            width: 520
            wrapMode: Text.WordWrap
            color: "white"
            font.pixelSize: 20
            text: "Tap SEED for a grain or to tap a delay tempo. SEED LOCK on = grains flow continuously. " +
                  "Amount knobs scale their CV input; with no CV patched they add random wander."
        }
    }

    // --------------------------------------------------------------- Setup
    Item {
        visible: droplets.tab_index == 2
        x: 200
        y: 40
        width: 1050
        height: 480

        Text {
            text: "QUALITY"
            color: "white"
            font { pixelSize: 24; capitalization: Font.AllUppercase }
        }
        Row {
            y: 40
            spacing: 16
            Repeater {
                model: ["Dirty tape", "Clean tape", "Vintage digital", "Digital"]
                PolyControls.Button {
                    width: 230
                    height: 90
                    checked: Math.round(currentEffects[droplets.effect_id]["controls"]["quality"].value) == index
                    onClicked: knobs.ui_knob_change(droplets.effect_id, "quality", index)
                    contentItem: Text {
                        text: modelData
                        color: parent.checked ? Constants.background_color : "white"
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.WordWrap
                        font { pixelSize: 22; capitalization: Font.AllUppercase }
                    }
                    background: Rectangle {
                        color: parent.checked ? Constants.poly_blue : Constants.poly_dark_grey
                        radius: 20
                    }
                }
            }
        }

        Grid {
            y: 170
            columns: 2
            spacing: 24
            Repeater {
                model: ["input_gain", "mono", "synth", "gate_out"]
                DelayRow {
                    row_param: modelData
                    current_effect: droplets.effect_id
                    v_type: droplets.v_type(modelData)
                    Material.foreground: Constants.rainbow[index + 2]
                }
            }
        }
    }

    MoreButton {
        l_effect_type: droplets.effect_type
    }
}
