#!/usr/bin/env python3
"""
Add Droplets to a Beebo / Hector UI folder (polyeffects/digit_ui or a fork).

    python3 droplets_ui.py <digit_ui folder>            # apply
    python3 droplets_ui.py <digit_ui folder> --check    # dry run, change nothing

Changes (each changed file is backed up to <file>.orig-droplets first):

  qml/Droplets.qml        new: the Droplets screen (Main / Modulate / Setup)
  module_info.py          registers the Droplets module (as in add-module.md)
  qml/PatchBayEffect.qml  opens Droplets.qml when you expand the module

All-or-nothing: if any file is not as expected, nothing is written.
Safe to run twice. Afterwards run `python3 effect_proto_to_js.py` in the
UI folder to rebuild qml/module_info.js.
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCREEN_SRC = os.path.join(HERE, "..", "ui", "Droplets.qml")
URI = "https://github.com/PedalEffected/Beebo#Droplets"


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
        fail(f"could not find the {what}. This UI version may differ from the one Droplets was written for.")
    return new


PROTO = """ 'Droplets': {'category': 3,
              'controls': {'time': ['Time', 0.5, 0.0, 1.0],
                           'size': ['Size', 0.5, 0.0, 1.0],
                           'shape': ['Shape', 0.5, 0.0, 1.0],
                           'density': ['Density', 0.5, 0.0, 1.0],
                           'pitch': ['Pitch', 0.0, -24.0, 24.0],
                           'feedback': ['Feedback', 0.5, 0.0, 1.0],
                           'dry_wet': ['Dry/Wet', 0.5, 0.0, 1.0],
                           'reverb': ['Reverb', 0.3, 0.0, 1.0],
                           'time_amt': ['Time amount', 0.0, -1.0, 1.0],
                           'size_amt': ['Size amount', 0.0, -1.0, 1.0],
                           'shape_amt': ['Shape amount', 0.0, -1.0, 1.0],
                           'pitch_amt': ['Pitch amount', 0.0, -1.0, 1.0],
                           'freeze': ['Freeze', 0, 0, 1, 'bool'],
                           'seed_button': ['Seed', 0, 0, 1, 'hide'],
                           'seed_lock': ['Seed lock', 1, 0, 1, 'bool'],
                           'quality': ['Quality', 3, 0, 3, 'int'],
                           'mono': ['Mono input', 0, 0, 1, 'bool'],
                           'input_gain': ['Input gain (0 = auto)', 0.0, 0.0, 1.0],
                           'synth': ['Synth mode', 0, 0, 1, 'bool'],
                           'gate_out': ['Right out = gate', 0, 0, 1, 'bool']},
              'description': 'Droplets: granular texture processor, delay and reverb. Ported from the open-source Mutable Instruments Beads engine.',
              'inputs': {'in_l': ['In L', 'AudioPort'],
                         'in_r': ['In R', 'AudioPort'],
                         'seed_gate': ['Seed / clock', 'CVPort'],
                         'freeze_gate': ['Freeze gate', 'CVPort'],
                         'time_cv': ['Time', 'CVPort'],
                         'size_cv': ['Size', 'CVPort'],
                         'shape_cv': ['Shape', 'CVPort'],
                         'pitch_cv': ['Pitch (1V/oct)', 'CVPort'],
                         'density_cv': ['Density', 'CVPort'],
                         'feedback_cv': ['Feedback', 'CVPort'],
                         'dry_wet_cv': ['Dry/Wet', 'CVPort'],
                         'reverb_cv': ['Reverb', 'CVPort']},
              'long_description': 'SIZE fully clockwise turns Droplets into a delay; patch a clock into Seed to sync it. Hold the three dots and touch a slider to type a value.',
              'outputs': {'out_l': ['L Out', 'AudioPort'], 'out_r': ['R Out', 'AudioPort']},
              'tags': {'ported', 'time effects'}},
"""


def patch_module_info(ui):
    path = os.path.join(ui, "module_info.py")
    text = read(path)
    if "'Droplets'" in text:
        print(f"  {path}: already has Droplets, skipping")
        return None
    text = sub_once(r"^([ \t]*)'granular': 'http://polyeffects\.com/lv2/polyclouds#granular',",
                    lambda m: f"{m.group(1)}'Droplets': '{URI}',\n" + m.group(0),
                    text, "granular entry in effect_type_maps", flags=re.M)
    text = sub_once(r"^ 'granular': \{'category'",
                    lambda m: PROTO + m.group(0),
                    text, "granular entry in effect_prototypes_models_all", flags=re.M)
    return path, text


def patch_patchbay(ui):
    path = os.path.join(ui, "qml", "PatchBayEffect.qml")
    text = read(path)
    if "Droplets" in text:
        print(f"  {path}: already has Droplets, skipping")
        return None

    def add_branch(m):
        ind, inner = m.group(1), m.group(1) + "    "
        return (f'{ind}else if (effect_type == "Droplets"){{\n'
                f'{inner}patchStack.push("Droplets.qml", {{"effect_id": effect_id, "effect_type": effect_type}});\n'
                f'{inner}patch_bay.current_help_text = "SIZE fully clockwise = delay. Clock into Seed to sync."\n'
                f'{ind}}}\n' + m.group(0))

    text = sub_once(r"^([ \t]*)else if \(\['granular'\]\.indexOf\(effect_type\) >= 0\)\{",
                    add_branch, text, "granular branch in expand_clicked()", flags=re.M)
    return path, text


def copy_screen(ui):
    dst = os.path.join(ui, "qml", "Droplets.qml")
    src = read(SCREEN_SRC)
    if os.path.exists(dst) and read(dst) == src:
        print(f"  {dst}: up to date, skipping")
        return None
    return dst, src


def write(path, text, check):
    if check:
        print(f"  would write {path}")
        return
    if os.path.exists(path) and not os.path.exists(path + ".orig-droplets"):
        shutil.copy2(path, path + ".orig-droplets")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  wrote {path}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    if len(args) != 1:
        sys.exit(__doc__)
    ui = args[0]
    print("Droplets UI install" + (" (dry run)" if check else "") + f" -> {ui}")
    results = [copy_screen(ui), patch_module_info(ui), patch_patchbay(ui)]
    for r in results:
        if r:
            write(*r, check)
    if any(results) and not check:
        print("\nDone. Now rebuild the module list:  cd " + ui + " && python3 effect_proto_to_js.py")


if __name__ == "__main__":
    main()
