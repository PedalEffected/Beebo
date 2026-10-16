# Beebo / Hector on a desktop computer

This folder turns the Beebo / Hector software into an app for a Mac (and
Linux). It runs the same three parts as the pedal:

| Part | On the pedal | On a desktop |
| --- | --- | --- |
| The screen | `show_widget.py` + QML, Qt 5 | the same code, on Qt 6 (PySide6) on a Mac |
| The engine | Ingen (Poly Effects fork) | the same Ingen, with `ingen/JsonWriter.*` |
| Audio | JACK on the pedal's codec | JACK on your audio interface |

The desktop app starts as a **Hector: 6 inputs and 8 outputs**. You can
switch it to Beebo in Settings.

## Mac app

`desktop/mac/build_app.sh` builds `Beebo.app`. GitHub builds it on its Mac
machines on every push to the `desktop` branch (see
`.github/workflows/mac-app.yml`). Each run attaches `Beebo-macOS`, which
contains:

- `Beebo-macOS-arm64.zip`: the app
- `report/plugins-report.md`: which modules were built
- `report/modules-loaded.txt`: which modules Ingen could load
- `report/screen.png`: a picture of the screen from the build check

### First start

1. Unzip and move **Beebo.app** to Applications.
2. The app isn't signed by Apple, so the first time macOS will refuse to
   open it. Open **System Settings > Privacy & Security**, scroll down and
   click **Open Anyway**. Alternatively, run this once in Terminal:
   `xattr -dr com.apple.quarantine /Applications/Beebo.app`
3. Pick your audio interface in the window that appears. Allow microphone
   access when macOS asks: that's how macOS describes any audio input.

To use **two USB devices at once**, for example a guitar interface and an
ES-8 for CV, open **Audio MIDI Setup**, click **+**, choose **Create
Aggregate Device**, tick both devices, then pick the aggregate device in
Beebo. Use the "Beebo IN / OUT ... channels" boxes to choose which channels
of the combined device the Hector's 6 inputs and 8 outputs use.

To change the audio setup later, quit Beebo and start it with the Option key
held, or run `Beebo.app/Contents/MacOS/Beebo --setup` from Terminal.

### Your files

Everything you make lives in **~/Beebo**:

| Folder | What |
| --- | --- |
| `presets/beebo` | presets (copy `/mnt/presets/beebo/*.ingen` from your pedal here) |
| `audio/reverbs`, `audio/cabs` | impulse responses (.wav, 48 kHz) |
| `audio/amp_nam` | NAM amp models |
| `pedal_state` | settings, favourites, the audio setup |
| `logs` | logs from JACK, Ingen and the screen |

## Modules

`build_plugins.py` builds every open-source module the screen offers, from
each project's source at a fixed version, and writes a report. Missing from
the desktop build:

- **Modules Poly Effects hasn't published the source for:** delay, wet/dry
  (and stereo), foot switches, tonestack, bitcrusher, MIDI note to CV (mono
  and poly), MIDI program change, MIDI clock in, onset and pitch detect, the
  "ext" phasers and the looper ports. They exist on the pedal only as ARM
  Linux binaries, so they can't run on a Mac. They can be rewritten from
  the port lists in `module_info.py`.
- **vinyl** (Calf): not built yet.

Presets that use a missing module still load, without that module.

## Linux

The same launcher runs on Linux with JACK, Ingen and PySide2 or PySide6
installed:

```sh
python3 desktop/prepare_ui.py .            # generated QML, icons, module list
python3 desktop/build_plugins.py --out ~/.lv2
python3 desktop/beebo_launcher.py --setup
```

## What changed in the shared code

The pedal code paths are unchanged. Desktop mode is detected in
`beebo_paths.py` (`BEEBO_DESKTOP=1`, any Mac, or a Linux machine without
`/pedal_state`):

- `beebo_paths.P()` maps pedal folders (`/mnt/presets`, `/audio`,
  `/usb_flash`, ...) to `~/Beebo`, and pedal-only shell commands (mounting,
  ALSA mixer, shutdown) are skipped
- the window scales to any size, and closing it quits
- `desktop/qt_compat.py` lets the PySide2 code run on PySide6, and
  `prepare_ui.py --qt6` adjusts a copy of the QML for Qt 6
- `make_placeholder_icons.py` draws simple icons for artwork that's only
  on the pedal (about 45 images, such as the menu buttons). Copy
  `/home/debian/UI/icons` from your pedal over them for the real ones.
