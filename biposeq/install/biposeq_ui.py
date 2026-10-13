#!/usr/bin/env python3
"""
Add BiPoSeq to a Beebo / Hector UI folder (polyeffects/digit_ui or a fork).

    python3 biposeq_ui.py <digit_ui folder>            # apply
    python3 biposeq_ui.py <digit_ui folder> --check    # dry run, change nothing

Changes (each changed file is backed up to <file>.orig-biposeq first):

  qml/BiPoSeq.qml         new: the BiPoSeq step editor screen
  module_info.py          registers BiPoSeq and BiPoSeq_ext (as in add-module.md)
  qml/PatchBayEffect.qml  opens BiPoSeq.qml when you expand the module
  qml/More.qml            adds a +/- sign key to the value keypad, shown only for
                          controls that can go negative

All-or-nothing: if any file is not as expected, nothing is written.
Safe to run twice. Afterwards run `python3 effect_proto_to_js.py` in the
UI folder to rebuild qml/module_info.js.
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCREEN_SRC = os.path.join(HERE, "..", "ui", "BiPoSeq.qml")
URI = "https://github.com/PedalEffected/Beebo"


def fail(msg):
    sys.exit(f"ERROR: {msg}\nNothing was changed.")


def read(path):
    if not os.path.exists(path):
        fail(f"{path} not found - pass the digit_ui (UI) folder as the first argument.")
    with open(path, encoding="utf-8") as f:
        return f.read()


def sub_once(pattern, repl, text, what, flags=0):
    new, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        fail(f"could not find the {what}. This UI version may differ from the one BiPoSeq was written for.")
    return new


# ------------------------------------------------------------- module_info.py
def _vals(indent):
    return "".join(f"{indent}'val{i}': ['Value {i}', 0.0, -5.0, 5.0],\n" for i in range(16))


PROTO = (
    " 'BiPoSeq': {'broadcast_ports': {'bpm': ['tempo', 120, 1, 320],\n"
    "                                 'current_step_out': ['current step out', 0, 0, 16]},\n"
    "             'category': 2,\n"
    "             'controls': {'back_gate': ['back', 0.0, 0.0, 1.0],\n"
    "                          'bpm': ['BPM', 120, 20, 320],\n"
    "                          'glide': ['Glide', 0.5, 0.0, 1.0],\n"
    "                          'note_length': ['Note Length', 0.125, 0.03125, 1],\n"
    "                          'play': ['play', 0.0, 0.0, 1.0],\n"
    "                          'steps': ['Loop Steps', 16, 1, 16],\n"
    + _vals("                          ").rstrip(",\n") + "},\n"
    "             'description': 'BiPoSeq: bipolar 16 step sequencer with internal clock, -5V to +5V',\n"
    "             'inputs': {'back_gate': ['Back Gate', 'CVPort'],\n"
    "                        'bpm': ['BPM', 'ControlPort'],\n"
    "                        'play': ['Play', 'CVPort'],\n"
    "                        'reset': ['Reset Trigger', 'CVPort']},\n"
    "             'long_description': 'Each step is set in volts, -5V to +5V. Tap a step, then press the three dots to type a value.',\n"
    "             'outputs': {'out': ['Value Out', 'CVPort']},\n"
    "             'tags': {'cv generators'}},\n"
    " 'BiPoSeq_ext': {'broadcast_ports': {'current_step_out': ['current step out', 0, 0, 16]},\n"
    "                 'category': 2,\n"
    "                 'controls': {'glide': ['Glide', 0.5, 0.0, 1.0],\n"
    "                              'steps': ['Loop Steps', 16, 1, 16],\n"
    + _vals("                              ").rstrip(",\n") + "},\n"
    "                 'description': 'BiPoSeq: bipolar 16 step sequencer stepped by triggers, -5V to +5V',\n"
    "                 'inputs': {'back_trigger': ['Back Trigger', 'CVPort'],\n"
    "                            'reset': ['Reset Trigger', 'CVPort'],\n"
    "                            'trigger': ['Step Trigger', 'CVPort']},\n"
    "                 'long_description': 'Each step is set in volts, -5V to +5V. Tap a step, then press the three dots to type a value.',\n"
    "                 'outputs': {'out': ['Value Out', 'CVPort']},\n"
    "                 'tags': {'cv generators'}},\n"
)


def patch_module_info(ui):
    path = os.path.join(ui, "module_info.py")
    text = read(path)
    if "'BiPoSeq'" in text:
        print(f"  {path}: already has BiPoSeq, skipping")
        return None
    text = sub_once(r"^([ \t]*)'step_sequencer': 'http://polyeffects\.com/lv2/step_sequencer_bpm',",
                    lambda m: (f"{m.group(1)}'BiPoSeq': '{URI}#BiPoSeq',\n"
                               f"{m.group(1)}'BiPoSeq_ext': '{URI}#BiPoSeq_ext',\n" + m.group(0)),
                    text, "step_sequencer entry in effect_type_maps", flags=re.M)
    text = sub_once(r"^ 'step_sequencer': \{'broadcast_ports'",
                    lambda m: PROTO + m.group(0),
                    text, "step_sequencer entry in effect_prototypes_models_all", flags=re.M)
    return path, text


# ------------------------------------------------------- PatchBayEffect.qml
def patch_patchbay(ui):
    path = os.path.join(ui, "qml", "PatchBayEffect.qml")
    text = read(path)
    if "BiPoSeq" in text:
        print(f"  {path}: already has BiPoSeq, skipping")
        return None

    def add_branch(m):
        ind, inner = m.group(1), m.group(1) + "    "
        return (f'{ind}else if (effect_type == "BiPoSeq" || effect_type == "BiPoSeq_ext"){{\n'
                f'{inner}patchStack.push("BiPoSeq.qml", {{"effect": effect_id, "effect_type": effect_type}});\n'
                f'{inner}patch_bay.current_help_text = "Tap a step, then press the three dots to type a value."\n'
                f'{ind}}}\n' + m.group(0))

    text = sub_once(r'^([ \t]*)else if \(effect_type == "step_sequencer_ext"\)\s*\{',
                    add_branch, text, "step_sequencer_ext branch in expand_clicked()", flags=re.M)
    return path, text


# ------------------------------------------------------------------ More.qml
SIGN_KEY = '''
{i}PolyButton {{ // BiPoSeq: +/- sign key, only for controls that can go negative
{i}    visible: currentEffects[current_effect]["controls"][row_param].rmin < 0
{i}    height: 70
{i}    width: 150
{i}    text: "+/-"
{i}    onClicked: {{
{i}        control.current_value = control.current_value.charAt(0) == "-" ? control.current_value.slice(1) : "-" + control.current_value;
{i}    }}
{i}    Material.foreground: Constants.poly_pink
{i}    border_color: Constants.poly_pink
{i}    Material.background: Constants.background_color
{i}    font_size: 36
{i}}}'''


def patch_more(ui):
    path = os.path.join(ui, "qml", "More.qml")
    text = read(path)
    if "BiPoSeq" in text:
        print(f"  {path}: already has the sign key, skipping")
        return None
    text = sub_once(r'(Column\s*\{\s*\n([ \t]*)width: 150\s*\n\s*spacing\s*:\s*20\s*\n\s*height: parent\.height)',
                    lambda m: m.group(1) + SIGN_KEY.format(i=m.group(2)),
                    text, "value column (+ / value / -) in More.qml")
    return path, text


# --------------------------------------------------------------- BiPoSeq.qml
def copy_screen(ui):
    dst = os.path.join(ui, "qml", "BiPoSeq.qml")
    src = read(SCREEN_SRC)
    if os.path.exists(dst) and read(dst) == src:
        print(f"  {dst}: up to date, skipping")
        return None
    return dst, src


def write(path, text, check):
    if check:
        print(f"  would write {path}")
        return
    if os.path.exists(path) and not os.path.exists(path + ".orig-biposeq"):
        shutil.copy2(path, path + ".orig-biposeq")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  wrote {path}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    if len(args) != 1:
        sys.exit(__doc__)
    ui = args[0]
    print("BiPoSeq UI install" + (" (dry run)" if check else "") + f" -> {ui}")
    results = [copy_screen(ui), patch_module_info(ui), patch_patchbay(ui), patch_more(ui)]
    for r in results:
        if r:
            write(*r, check)
    if any(results) and not check:
        print("\nDone. Now rebuild the module list:  cd " + ui + " && python3 effect_proto_to_js.py")


if __name__ == "__main__":
    main()
