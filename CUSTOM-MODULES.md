# Custom modules in this fork

This fork of Poly Effects' Beebo / Hector UI (`digit_ui`) adds the modules below. Each one lives in its own folder with its source, a ready-to-install pedal build, an installer and a README. Each is also registered in the UI, in `module_info.py`, `qml/PatchBayEffect.qml` and its own screen in `qml/`.

| Module | Folder | Browser category | What it is |
| --- | --- | --- | --- |
| **BiPoSeq** / **BiPoSeq_ext** | [`biposeq/`](biposeq/) | cv generators | Bipolar 16-step CV sequencer, −5 V to +5 V, with internal clock or external triggers. Tap a step and press the three dots to type a voltage. |
| **Droplets** | [`droplets/`](droplets/) | time effects | Granular texture processor, delay and reverb, ported from the open-source Mutable Instruments Beads engine. |

## Installing on a pedal

Every module installs the same way. You need SSH access as the `debian` user; see [add-module.md](add-module.md).

```sh
scp -r <module folder> debian@PEDAL_IP:
ssh debian@PEDAL_IP
cd <module folder>
sh install/install_on_pedal.sh --check    # dry run
sh install/install_on_pedal.sh            # install
sudo reboot
```

Run the installer again after a Poly firmware update. Uninstall with `sh install/uninstall_on_pedal.sh`.

## Where each module touches the UI

| File | BiPoSeq | Droplets |
| --- | --- | --- |
| `module_info.py` | `BiPoSeq`, `BiPoSeq_ext` | `Droplets` |
| `qml/PatchBayEffect.qml` | opens `BiPoSeq.qml` | opens `Droplets.qml` |
| `qml/` screen | `BiPoSeq.qml` | `Droplets.qml` |
| `qml/More.qml` | adds the +/- key to the value keypad | (uses it) |

None of these modules has been run on a physical Beebo or Hector yet.
