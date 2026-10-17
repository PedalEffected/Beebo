# Droplets: granular texture processor for Beebo / Hector

Droplets is the sound engine of the Mutable Instruments **Beads** module, running as a module on Poly Effects Beebo and Hector. Émilie Gillet released the Beads source in October 2026 under the MIT license. Droplets uses that engine **unmodified** and replaces only the hardware layer: panel, CV inputs, gates and audio codec.

It does everything Beads does: granular textures, freeze, pitch-shifting grains, tape and digital quality modes, the built-in reverb, a clock-syncable delay, and the wavetable synth mode.

## The screen

Droplets has three pages, in the style of Poly's Rings screen:

| Page | Controls |
| --- | --- |
| **Main** | Time, Size, Shape, Density, Pitch (±24 semitones), Feedback, Dry/Wet, Reverb |
| **Modulate** | Time / Size / Shape / Pitch amount, Freeze, Seed lock, and a momentary **SEED** button |
| **Setup** | Quality (Dirty tape, Clean tape, Vintage digital, Digital), Mono input, Input gain (0 = automatic), Synth mode, Right out = gate |

As in every Poly module, **hold the three dots and touch a slider** to type an exact value.

## How it maps to Beads

- **Grains:** SEED LOCK is on by default, as on Beads at power-up, so grains flow continuously. DENSITY at 12 o'clock means no grains. Turn it left for regular grains and right for random ones.
- **Delay mode:** turn SIZE fully clockwise. With a clock patched into **Seed / clock**, or tempo tapped on the SEED button with lock off, the delay syncs. DENSITY then picks the clock ratio and TIME picks the number of repeats.
- **Amount controls:** these are the Beads attenuverters. With a CV patched into the matching input, they scale it. With nothing patched, they add random wander. Beads detects patched cables with jack switches. Droplets treats an input as patched if it has carried any signal in the last second.
- **CV scale:** Hector scale, 1.0 = 5 V, matching Beads' ±5 V inputs. Pitch CV is 1 V/oct. Feedback, Dry/Wet and Reverb each get their own CV input, in place of Beads' single assignable one.
- **Gates:** Seed and Freeze gates count as high above about 2 V (0.4).
- **Quality modes:** these run at the same internal rates as the module (24, 32 or 48 kHz), resampled to the pedal's rate. Input gain and soft clipping follow the module's per-mode behaviour.
- **Synth mode:** a switch. Beads enters it automatically when nothing is patched into its audio inputs for 10 seconds.

## Install on the pedal

You need SSH access as the `debian` user (see [add-module.md](../add-module.md)).

```sh
scp -r droplets debian@PEDAL_IP:
ssh debian@PEDAL_IP
cd droplets
sh install/install_on_pedal.sh --check    # dry run
sh install/install_on_pedal.sh            # install
sudo reboot
```

Droplets appears under **time effects**. The installer uses Poly's documented method and backs up each changed UI file as `*.orig-droplets`. To remove it, run `sh install/uninstall_on_pedal.sh` and reboot. **After a Poly firmware update, run the installer again.**

## Build from source

The exact engine files Droplets needs are in `third_party/` (unmodified, with their MIT licenses).

```sh
cd lv2
make                                   # desktop build, for testing in any LV2 host
make arm64 LV2_INCLUDE=/usr/include    # pedal build -> ../prebuilt-arm64 (needs: pip install ziglang)
```

The pedal build uses Zig as the cross-compiler. It targets glibc 2.17, so it loads on older Debian images. It has no C++ standard library dependency and exports only `lv2_descriptor`.

## Tested

- **Engine match:** Droplets' output matches Beads' engine called directly to within rounding (relative error about 10⁻⁸).
- **Functional tests:** 19 checks, all passing on x86-64 and on the ARM64 pedal build under emulation. They cover grains, freeze, the clocked delay (the echo lands exactly one clock period later), all four quality modes at 48 kHz and 44.1 kHz with no dropouts, synth mode, and CV inputs.
- **CPU:** under 2% of one 2.8 GHz x86 core at the heaviest settings. The pedal's Cortex-A53 is estimated at about 15–25% of one of its four cores, which still needs confirming on hardware.
- **UI:** the installer is all-or-nothing and safe to rerun, and every LV2 port matches `module_info.py`. The QML passes `qmllint`, and all three pages render. Install and uninstall were tested on a simulated pedal filesystem.
- **Not yet run on a physical Beebo or Hector.**

## License and credits

- Droplets wrapper, screen and installer: MIT, © 2026 Gary Kane.
- Beads engine and stmlib: MIT, © Émilie Gillet. See `third_party/`.
- "Mutable Instruments" and "Beads" are Émilie Gillet's names. Droplets is an independent port and is not affiliated with Mutable Instruments.
