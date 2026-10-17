#!/usr/bin/env python3
"""Beebo for desktop: start the audio engine and the Beebo screen.

What the pedal does at boot, done on a computer:

  1. JACK, the audio server, on the audio interface you pick
  2. Ingen, the patching engine, loading every module
  3. the Beebo screen (digit_ui), connected to Ingen

and the pedal's inputs and outputs (in_1 ... out_8) connected to your
interface's channels. Quitting the screen stops everything again.

    python3 desktop/beebo_launcher.py            start
    python3 desktop/beebo_launcher.py --setup    choose the audio interface first
    python3 desktop/beebo_launcher.py --list     list audio devices and exit

Settings are kept in <data folder>/pedal_state/desktop_audio.json
(~/Beebo on a Mac). Logs go to <data folder>/logs.
"""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
sys.path.insert(0, UI)
os.environ.setdefault("BEEBO_DESKTOP", "1")
import beebo_paths  # noqa: E402

DARWIN = sys.platform == "darwin"

# Inside Beebo.app, everything sits next to the UI folder in Resources/:
#   Resources/ui  Resources/lv2  Resources/ingen  Resources/jack  Resources/factory
RES = os.environ.get("BEEBO_RESOURCES", os.path.dirname(UI))
BUNDLED = os.path.isdir(os.path.join(RES, "ingen"))

SETTINGS_PATH = beebo_paths.P("/mnt/pedal_state/desktop_audio.json")
LOG_DIR = os.path.join(beebo_paths.DATA_DIR, "logs")
AUDIO_SETUP_REQUEST = os.path.join(beebo_paths.DATA_DIR, "pedal_state", ".audio_setup_requested")

DEFAULTS = {
    "driver": "coreaudio" if DARWIN else "alsa",
    "device": "",               # duplex device (internal name); "" = system default
    "capture_device": "",       # optional separate input device
    "playback_device": "",      # optional separate output device
    "sample_rate": 48000,       # the pedal runs at 48 kHz
    "buffer": 256,
    "inputs": [1, 2, 3, 4, 5, 6],          # in_1..in_6 <- device input channels
    "outputs": [1, 2, 3, 4, 5, 6, 7, 8],   # out_1..out_8 -> device output channels
    "midi": True,
    "threads": 2,
    "ask_at_start": True,       # show the audio setup window at every start
}


def log(*a):
    print("[beebo]", *a, flush=True)


# ------------------------------------------------------------------ programs

def find_program(name):
    """Bundled copy first, then $BEEBO_<NAME>, then PATH."""
    env = os.environ.get("BEEBO_" + name.upper().replace("-", "_"))
    if env:
        return env
    for sub in ("ingen/bin", "jack/bin"):
        p = os.path.join(RES, sub, name)
        if os.path.exists(p):
            return p
    return shutil.which(name)


def program_env():
    env = dict(os.environ)
    lv2 = [os.path.join(RES, "lv2"), os.path.join(beebo_paths.DATA_DIR, "lv2")]
    if DARWIN:
        lv2 += [os.path.expanduser("~/Library/Audio/Plug-Ins/LV2"), "/Library/Audio/Plug-Ins/LV2"]
    else:
        lv2 += [os.path.expanduser("~/.lv2"), "/usr/local/lib/lv2", "/usr/lib/lv2"]
    if env.get("LV2_PATH"):
        lv2.insert(0, env["LV2_PATH"])
    env["LV2_PATH"] = os.pathsep.join(p for p in lv2 if os.path.isdir(p))
    if BUNDLED:
        env["INGEN_MODULE_PATH"] = os.path.join(RES, "ingen", "lib")
        env["JACK_DRIVER_DIR"] = os.path.join(RES, "jack", "lib", "jack")
    return env


# ------------------------------------------------------------------ settings

def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH) as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(s, f, indent=1)


def coreaudio_channel_counts():
    """{device name: (inputs, outputs)} from macOS's own audio report."""
    counts = {}
    try:
        out = subprocess.run(["system_profiler", "SPAudioDataType", "-json"],
                             capture_output=True, text=True, timeout=20).stdout
        for top in json.loads(out).get("SPAudioDataType", []):
            for d in top.get("_items", []):
                counts[d.get("_name", "")] = (int(d.get("coreaudio_device_input", 0) or 0),
                                              int(d.get("coreaudio_device_output", 0) or 0))
    except Exception:
        pass
    return counts


def list_devices(driver):
    """[(display name, internal name, inputs, outputs)] for the JACK driver."""
    jackd = find_program("jackd")
    devices = []
    if not jackd:
        return devices
    if driver == "coreaudio":
        try:
            p = subprocess.run([jackd, "-d", "coreaudio", "-l"], env=program_env(),
                               capture_output=True, text=True, timeout=20)
            out = p.stdout + p.stderr
        except (OSError, subprocess.TimeoutExpired):
            return devices
        channels = coreaudio_channel_counts()
        seen = set()
        for m in re.finditer(r"name = '([^']*)', internal name = '([^']*)'", out):
            name, internal = m.group(1), m.group(2)
            if internal in seen:
                continue
            seen.add(internal)
            ins, outs = channels.get(name, (0, 0))
            devices.append((name, internal, ins, outs))
    elif driver == "alsa":
        try:
            out = subprocess.run(["aplay", "-l"], capture_output=True, text=True).stdout
        except OSError:
            out = ""
        for m in re.finditer(r"card (\d+): (\w+) \[([^\]]*)\]", out):
            devices.append((m.group(3), "hw:%s" % m.group(2), 0, 0))
    return devices


def setup_dialog(settings):
    """Small window to pick the audio interface. Returns updated settings,
    or None if cancelled."""
    sys.path.insert(0, HERE)
    import qt_compat
    qt_compat.install()
    from PySide2.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                                   QFormLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
                                   QVBoxLayout)
    app = QApplication.instance() or QApplication(sys.argv)
    devices = list_devices(settings["driver"])
    dlg = QDialog()
    dlg.setWindowTitle("Beebo audio setup")
    lay = QVBoxLayout(dlg)
    intro = QLabel(
        "Pick the audio interface Beebo plays through. To use two USB devices at once, "
        "combine them into an Aggregate Device in Audio MIDI Setup first, then pick it "
        "here, or choose separate devices for inputs and outputs below." if DARWIN else
        "Pick the audio interface Beebo plays through.")
    intro.setWordWrap(True)
    lay.addWidget(intro)
    form = QFormLayout()
    lay.addLayout(form)

    def fill(c, current, first):
        c.clear()
        c.addItem(first, "")
        for name, internal, ins, outs in devices:
            label = name + ("  (%d in / %d out)" % (ins, outs) if ins or outs else "")
            c.addItem(label, internal)
        i = c.findData(current)
        c.setCurrentIndex(max(i, 0))

    dev, cap, play = QComboBox(), QComboBox(), QComboBox()
    fill(dev, settings["device"], "System default")
    fill(cap, settings["capture_device"], "Same as above")
    fill(play, settings["playback_device"], "Same as above")

    def refresh():
        nonlocal devices
        keep = (dev.currentData(), cap.currentData(), play.currentData())
        devices = list_devices(settings["driver"])
        fill(dev, keep[0], "System default")
        fill(cap, keep[1], "Same as above")
        fill(play, keep[2], "Same as above")

    rescan = QPushButton("Refresh list")
    rescan.setToolTip("Look again for audio interfaces, for example one you just plugged in")
    rescan.clicked.connect(refresh)
    form.addRow("Audio device", dev)
    form.addRow("", rescan)
    form.addRow("Inputs from (optional)", cap)
    form.addRow("Outputs to (optional)", play)
    rate = QComboBox()
    for r in (44100, 48000, 88200, 96000):
        rate.addItem("%d Hz" % r, r)
    rate.setCurrentIndex(max(rate.findData(settings["sample_rate"]), 0))
    form.addRow("Sample rate", rate)
    buf = QComboBox()
    for b in (64, 128, 256, 512, 1024):
        buf.addItem("%d samples" % b, b)
    buf.setCurrentIndex(max(buf.findData(settings["buffer"]), 0))
    form.addRow("Buffer size", buf)
    ins = QLineEdit(", ".join(str(x) for x in settings["inputs"]))
    outs = QLineEdit(", ".join(str(x) for x in settings["outputs"]))
    form.addRow("Beebo IN 1, 2, ... from device inputs", ins)
    form.addRow("Beebo OUT 1, 2, ... to device outputs", outs)
    threads = QSpinBox()
    threads.setRange(1, max(1, os.cpu_count() or 1))
    threads.setValue(settings["threads"])
    form.addRow("Processing threads", threads)
    ask = QCheckBox("Show this window every time Beebo starts")
    ask.setChecked(settings.get("ask_at_start", True))
    lay.addWidget(ask)
    later = QLabel("You can also change the audio device while Beebo runs: "
                   "Audio menu > Change Audio Device." if DARWIN else "")
    later.setWordWrap(True)
    lay.addWidget(later)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("Start Beebo")
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    if not (dlg.exec() if hasattr(dlg, "exec") else dlg.exec_()):
        return None

    def nums(text):
        return [int(x) for x in re.findall(r"\d+", text)]

    settings = dict(settings)
    settings.update(device=dev.currentData(), capture_device=cap.currentData(),
                    playback_device=play.currentData(), sample_rate=rate.currentData(),
                    buffer=buf.currentData(), inputs=nums(ins.text()) or DEFAULTS["inputs"],
                    outputs=nums(outs.text()) or DEFAULTS["outputs"], threads=threads.value(),
                    ask_at_start=ask.isChecked())
    save_settings(settings)
    return settings


# ------------------------------------------------------------------ processes

class Engine:
    def __init__(self, settings):
        self.s = settings
        self.procs = []
        self.env = program_env()
        os.makedirs(LOG_DIR, exist_ok=True)

    def spawn(self, name, args):
        logf = open(os.path.join(LOG_DIR, name + ".log"), "w")
        log("starting", name, ":", " ".join(args))
        p = subprocess.Popen(args, env=self.env, stdout=logf, stderr=subprocess.STDOUT,
                             start_new_session=True)
        self.procs.append((name, p))
        return p

    def jack_running(self):
        lsp = find_program("jack_lsp")
        if not lsp:
            return False
        return subprocess.run([lsp], env=self.env, capture_output=True).returncode == 0

    def start_jack(self):
        if self.jack_running():
            log("using the JACK server that is already running")
            return
        jackd = find_program("jackd")
        if not jackd:
            raise SystemExit("JACK (jackd) not found")
        s = self.s
        args = [jackd, "--silent", "-t", "2000", "-d", s["driver"], "-r", str(s["sample_rate"]), "-p", str(s["buffer"])]
        if s["driver"] in ("coreaudio", "alsa"):
            if s["capture_device"] or s["playback_device"]:
                args += ["-C", s["capture_device"] or s["device"], "-P", s["playback_device"] or s["device"]]
            elif s["device"]:
                args += ["-d", s["device"]]
        if s["driver"] == "alsa" and s.get("midi"):
            args += ["-X", "seq"]
        self.spawn("jackd", args)
        for _ in range(100):
            if self.jack_running():
                return
            time.sleep(0.1)
        raise SystemExit("JACK didn't start; see %s" % os.path.join(LOG_DIR, "jackd.log"))

    def start_ingen(self):
        ingen = find_program("ingen")
        if not ingen:
            raise SystemExit("Ingen not found")
        sock = beebo_paths.INGEN_SOCKET
        for f in (sock,):
            if os.path.lexists(f):
                os.unlink(f)
        graph = startup_graph()
        self.spawn("ingen", [ingen, "-e", "-p", str(self.s["threads"]), "-S", sock, graph])
        for _ in range(300):
            if os.path.exists(sock):
                try:
                    c = socket.socket(socket.AF_UNIX)
                    c.connect(sock)
                    c.close()
                    return
                except OSError:
                    pass
            time.sleep(0.1)
        raise SystemExit("Ingen didn't start; see %s" % os.path.join(LOG_DIR, "ingen.log"))

    def connect_ports(self):
        """Wire ingen:in_N / out_N to the device's channels."""
        connect = find_program("jack_connect")
        lsp = find_program("jack_lsp")
        if not (connect and lsp):
            log("jack_connect not found: connect Beebo's ports yourself")
            return
        for _ in range(50):
            ports = subprocess.run([lsp], env=self.env, capture_output=True, text=True).stdout.split()
            if "ingen:in_1" in ports:
                break
            time.sleep(0.2)
        capture = sorted([p for p in ports if p.startswith("system:capture_")], key=_num)
        playback = sorted([p for p in ports if p.startswith("system:playback_")], key=_num)
        pairs = []
        for i, ch in enumerate(self.s["inputs"], 1):
            if "ingen:in_%d" % i in ports and 0 < ch <= len(capture):
                pairs.append((capture[ch - 1], "ingen:in_%d" % i))
        for i, ch in enumerate(self.s["outputs"], 1):
            if "ingen:out_%d" % i in ports and 0 < ch <= len(playback):
                pairs.append(("ingen:out_%d" % i, playback[ch - 1]))
        if self.s.get("midi"):
            midi_in = [p for p in ports if re.search(r"(midi.*capture|capture.*midi|a2j.*capture)", p, re.I)]
            midi_out = [p for p in ports if re.search(r"(midi.*playback|playback.*midi|a2j.*playback)", p, re.I)]
            if "ingen:midi_in" in ports:
                pairs += [(p, "ingen:midi_in") for p in midi_in]
            if "ingen:midi_out" in ports:
                pairs += [("ingen:midi_out", p) for p in midi_out]
        for a, b in pairs:
            subprocess.run([connect, a, b], env=self.env, capture_output=True)
        log("connected %d ports" % len(pairs))

    def stop(self):
        for name, p in reversed(self.procs):
            if p.poll() is None:
                log("stopping", name)
                p.terminate()
                try:
                    p.wait(5)
                except subprocess.TimeoutExpired:
                    p.kill()
        self.procs = []


def _num(port):
    m = re.search(r"(\d+)$", port)
    return int(m.group(1)) if m else 0


def startup_graph():
    for p in (os.path.join(RES, "factory", "start_up.ingen"),
              os.path.join(HERE, "factory", "start_up.ingen")):
        if os.path.isdir(p):
            return p
    raise SystemExit("start_up.ingen not found")


def install_factory_presets():
    """Copy the bundled presets into the data folder (never overwriting)."""
    for root in (os.path.join(RES, "factory", "presets"), os.path.join(HERE, "factory", "presets")):
        if not os.path.isdir(root):
            continue
        for model in os.listdir(root):
            for preset in os.listdir(os.path.join(root, model)):
                dst = os.path.join(beebo_paths.P("/mnt/presets"), model, preset)
                if not os.path.exists(dst):
                    shutil.copytree(os.path.join(root, model, preset), dst)
        return


def option_key_held():
    """True if the Option (Alt) key is down: on a Mac, holding it while
    Beebo starts opens the audio setup."""
    if not DARWIN:
        return False
    try:
        import ctypes
        q = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        q.CGEventSourceFlagsState.restype = ctypes.c_uint64
        return bool(q.CGEventSourceFlagsState(1) & 0x80000)  # HID state, alternate mask
    except Exception:
        return False


def main():
    if "--list" in sys.argv:
        for d in list_devices(load_settings()["driver"]):
            print("%-40s %-40s %d in / %d out" % d)
        return 0
    beebo_paths.ensure_dirs()
    install_factory_presets()
    settings = load_settings()
    first_run = not os.path.exists(SETTINGS_PATH)
    ask = ("--setup" in sys.argv or option_key_held() or
           ((first_run or settings.get("ask_at_start", True)) and "--no-setup" not in sys.argv))
    if ask:
        settings = setup_dialog(settings)
        if settings is None:
            return 0
    for arg in sys.argv[1:]:
        if arg.startswith("--driver="):
            settings["driver"] = arg.split("=", 1)[1]
    state = {"engine": None}

    def bye(*_):
        if state["engine"]:
            state["engine"].stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, bye)
    signal.signal(signal.SIGINT, bye)
    while True:
        # the screen asks for the audio setup (Audio menu) by leaving this file
        if os.path.exists(AUDIO_SETUP_REQUEST):
            os.unlink(AUDIO_SETUP_REQUEST)
        engine = state["engine"] = Engine(settings)
        try:
            engine.start_jack()
            engine.start_ingen()
            engine.connect_ports()
            log("starting the Beebo screen")
            ui_log = open(os.path.join(LOG_DIR, "ui.log"), "w")
            env = dict(engine.env)
            env["PYTHONUNBUFFERED"] = "1"
            env["BEEBO_AUDIO_SETUP_REQUEST"] = AUDIO_SETUP_REQUEST
            ui = subprocess.Popen([sys.executable, os.path.join(UI, "beebo_desktop_ui.py")],
                                  env=env, stdout=ui_log, stderr=subprocess.STDOUT)
            ui.wait()
        finally:
            engine.stop()
            state["engine"] = None
        if not os.path.exists(AUDIO_SETUP_REQUEST):
            return 0
        log("audio setup requested from the Beebo screen")
        new = setup_dialog(settings)
        if new is not None:
            settings = new
        # cancelled: start again with the same settings


if __name__ == "__main__":
    sys.exit(main())
