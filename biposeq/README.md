# BiPoSeq: bipolar step sequencer for Beebo / Hector

BiPoSeq is a 16-step CV sequencer whose steps run from **−5 V to +5 V**. It's built on Poly Effects' step sequencer and uses the same screen, the same patch bay and the same knob mapping as every other module.

| Module | Clock | Inputs |
| --- | --- | --- |
| **BiPoSeq** | Internal BPM, play / back buttons | Play, Back Gate, Reset, BPM |
| **BiPoSeq_ext** | External triggers | Step Trigger, Back Trigger, Reset |

Both are listed under **cv generators** in the module browser.

## Using it

- **Drag a bar** up or down from the centre line to set the step's voltage. The centre line is 0 V.
- **Tap a step** (its bar or its number) to select it. The top bar shows the selected step's voltage, such as `STEP 4: +2.50 V`, and the pedal's knob controls that step.
- **Press the three dots** to open the value screen for the selected step. Type a voltage, use **+/-** to make it negative, and press **SUBMIT**. That screen also has MIDI learn, reset to default (0 V), +/- nudge buttons, and *Expose in Spotlight*.
- Like other modules, you can also **hold the three dots and touch a step**.
- With nothing selected, the three dots show the module's help page. Glide can be selected and typed in the same way.

**Output scale:** a step value is in volts. The plugin outputs it as Beebo CV, where 1.0 = 5 V on a Hector jack (the same scale as Poly's quantizer). On the Beebo pedal, BiPoSeq's −1…+1 output drives whatever parameter you patch it into.

## Install on the pedal

You need SSH access as the `debian` user. Poly's [add-module.md](../add-module.md) covers networking. To find the pedal's IP, open Settings, then QA Test, then IP.

```sh
# on your computer: copy this folder to the pedal
scp -r biposeq debian@PEDAL_IP:

# on the pedal
ssh debian@PEDAL_IP
cd biposeq
sh install/install_on_pedal.sh --check    # dry run
sh install/install_on_pedal.sh            # install
sudo reboot
```

The installer follows Poly's documented method. It remounts the pedal's read-only system layer, copies in the plugin (`/usr/lib/lv2/biposeq.lv2`), and adds BiPoSeq to the UI (`/home/debian/UI`). Every UI file it changes is backed up as `*.orig-biposeq`. If any file isn't what it expects, it stops without changing anything.

**After a Poly firmware update,** run the installer again.

**To uninstall,** run `sh install/uninstall_on_pedal.sh`, then reboot.

## What's in this folder

```
lv2/              plugin source (C), LV2 metadata, Makefile
prebuilt-arm64/   ready-to-install plugin for the pedal (ARM64, glibc >= 2.17)
ui/BiPoSeq.qml    the step editor screen
install/          pedal installer, uninstaller, and biposeq_ui.py (the UI patcher)
test/             plugin test harness
```

This fork already has BiPoSeq applied to the UI, made with `install/biposeq_ui.py`. The changed files are `qml/BiPoSeq.qml`, `module_info.py`, `qml/PatchBayEffect.qml` and `qml/More.qml`.

## Build from source

```sh
cd lv2
make            # native build (Linux / macOS), for testing in a desktop LV2 host
make arm64      # cross-compile the pedal build into ../prebuilt-arm64 (needs gcc-aarch64-linux-gnu)
```

Run the tests:

```sh
gcc -o /tmp/test_biposeq test/test_biposeq.c -ldl -lm
/tmp/test_biposeq lv2/build/biposeq.lv2/biposeq.so
```

## Technical notes

- **Plugin IDs:** `https://github.com/PedalEffected/Beebo#BiPoSeq` and `…#BiPoSeq_ext`.
- **Ports:** port numbers and symbols match Poly's `step_sequencer_bpm` / `step_sequencer`. `val0`–`val15` range −5…+5, default 0.
- **Plugin logic:** each step is clamped to ±5 V, divided by 5, then passed through the original one-pole glide.
- **Value screen:** the +/- key is added to Poly's shared `More.qml`. It only appears for controls whose minimum is below zero, so it also works for other bipolar controls such as attenuverters.

## Tested

- **Plugin:** 25 checks, run on x86-64 and on the ARM64 build under emulation. They cover −5/0/+2.5/+5 V steps, typed values (−1.25 V), clamping (9 V, −12 V), forward and back triggers, wrap-around, reset, glide, and 120 BPM timing.
- **UI:**
    - The patcher runs on the current `digit_ui`, a second run changes nothing, and the dry run writes nothing.
    - `module_info.js` regenerates with both modules, and all changed QML passes `qmllint`.
    - A headless Qt run confirmed the dots, select and hold behaviour.
- **Installer:** install and uninstall run end to end against a simulated pedal filesystem, and uninstall restores every file exactly.
- **Not yet run on a physical Beebo or Hector.**

## License

GPL-3.0-or-later. Based on Poly Effects' step sequencer (Loki Davison) and the blop sequencer (David Robillard, Mike Rawes).
