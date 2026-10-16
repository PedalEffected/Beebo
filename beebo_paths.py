"""Where Beebo keeps its files, on the pedal and on a desktop computer.

On the pedal everything lives at fixed paths (/mnt/presets, /audio, ...).
On a desktop the same folders live in the user's data folder:

    macOS   ~/Beebo   (visible, so you can drop IRs, NAM models and presets in)
    Linux   ~/.local/share/beebo   (or $XDG_DATA_HOME/beebo)

or wherever BEEBO_DATA_DIR points. P("/mnt/presets/beebo/x.ingen") turns a
pedal path into the matching desktop path, and returns it unchanged on the
pedal, so the rest of the code can keep using pedal-style paths.

Desktop mode is on when BEEBO_DESKTOP=1, or automatically on macOS and
Windows, or on Linux when this isn't a Poly pedal (no /pedal_state folder).
"""
import os
import sys
import tempfile


def _detect_desktop():
    env = os.environ.get("BEEBO_DESKTOP")
    if env is not None:
        return env not in ("", "0", "false", "no")
    if sys.platform != "linux":
        return True
    return not os.path.isdir("/pedal_state")


IS_DESKTOP = _detect_desktop()


def _default_data_dir():
    if sys.platform == "darwin":
        # Not "Application Support": the pedal's shell commands can't cope
        # with spaces in paths.
        return os.path.expanduser("~/Beebo")
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Beebo")
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(base, "beebo")


DATA_DIR = os.environ.get("BEEBO_DATA_DIR", _default_data_dir()) if IS_DESKTOP else "/"

# Pedal folder -> folder inside DATA_DIR. Longest prefixes first.
_MAP = [
    ("/mnt/pedal_state", "pedal_state"),
    ("/pedal_state", "pedal_state"),
    ("/mnt/presets", "presets"),
    ("/mnt/audio", "audio"),
    ("/audio", "audio"),
    ("/usb_flash", "usb"),
    ("/nor_flash", "nor_flash"),
    ("/to_nor_flash", "nor_flash"),
]

if IS_DESKTOP:
    # Unix socket paths are limited to ~104 bytes on macOS, so keep it short.
    INGEN_SOCKET = os.environ.get(
        "BEEBO_INGEN_SOCKET",
        os.path.join(tempfile.gettempdir(), "beebo-%d-ingen.sock" % os.getuid()))
    TMP_DIR = tempfile.gettempdir()
else:
    INGEN_SOCKET = "/tmp/ingen.sock"
    TMP_DIR = "/tmp"


def P(path):
    """Map a pedal path (or file:// URL) to where it lives on this machine."""
    if not IS_DESKTOP or not isinstance(path, str):
        return path
    if path.startswith("file://"):
        return "file://" + P(path[len("file://"):])
    if path == "/tmp/ingen.sock":
        return INGEN_SOCKET
    if path.startswith("/tmp/"):
        return os.path.join(TMP_DIR, path[len("/tmp/"):])
    for pedal, local in _MAP:
        if path == pedal or path.startswith(pedal + "/"):
            return os.path.join(DATA_DIR, local) + path[len(pedal):]
    return path


def unP(path):
    """Inverse of P(): turn a desktop path back into the pedal-style path."""
    if not IS_DESKTOP or not isinstance(path, str):
        return path
    if path.startswith("file://"):
        return "file://" + unP(path[len("file://"):])
    for pedal, local in _MAP:
        root = os.path.join(DATA_DIR, local)
        if path == root or path.startswith(root + "/"):
            return pedal + path[len(root):]
    return path


def url(path):
    """file:// URL for a pedal path, for QML."""
    return "file://" + P(path)


def ensure_dirs():
    """Create the desktop data folders on first run."""
    if not IS_DESKTOP:
        return
    for sub in ("presets/beebo", "pedal_state", "audio/reverbs", "audio/cabs",
                "audio/amp_nam", "audio/amp_json", "usb"):
        os.makedirs(os.path.join(DATA_DIR, sub), exist_ok=True)
    if _SHELL_ROOT != DATA_DIR:
        try:
            if os.path.islink(_SHELL_ROOT) and os.readlink(_SHELL_ROOT) != DATA_DIR:
                os.unlink(_SHELL_ROOT)
            if not os.path.lexists(_SHELL_ROOT):
                os.symlink(DATA_DIR, _SHELL_ROOT)
        except OSError:
            pass


# Shell commands can't cope with spaces, so if the data folder has one they
# use a space-free link to it (~/.beebo-data).
_SHELL_ROOT = DATA_DIR if " " not in DATA_DIR else os.path.expanduser("~/.beebo-data")


# ---------------------------------------------------------------- shell hooks
# The pedal UI runs a few shell commands (USB import/export, mixer levels,
# shutdown). On a desktop, pedal paths inside those commands are rewritten to
# the data folder, sudo/mount steps are dropped, and pedal-only programs are
# skipped instead of failing.

import re as _re
import shlex as _shlex
import subprocess as _subprocess

_PEDAL_ONLY = ("amixer", "shutdown", "reboot", "polyoverlayroot", "overlayroot",
               "dpkg", "fbtextdemo", "hostname -I", "/usr/bin/jack_connect",
               "jack_connect", "jack_disconnect", "systemctl", "fw_setenv",
               "mount -o remount")


def shell(cmd):
    """Rewrite a pedal shell command for this machine (desktop only)."""
    if not IS_DESKTOP or not isinstance(cmd, str):
        return cmd
    cmd = _re.sub(r"sudo\s+(u?mount)\b[^;\n]*;?", "", cmd)
    cmd = _re.sub(r"\bmount\s+/dev/\S+\s+/usb_flash;?", "", cmd)
    cmd = _re.sub(r"\bsudo\s+", "", cmd)
    for pedal, local in _MAP:
        root = os.path.join(_SHELL_ROOT, local)
        if " " in root:
            root = _shlex.quote(root)
        cmd = _re.sub(r"(?<![\w/.-])" + _re.escape(pedal) + r"(?=[/\s;'\"*)]|$)",
                      lambda m: root, cmd)
    return cmd


def _is_pedal_only(cmd):
    text = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
    return any(text.lstrip().startswith(p) or (" " + p) in text for p in _PEDAL_ONLY[:4]) \
        or any(text.lstrip().startswith(p) for p in _PEDAL_ONLY)


class _Done:
    returncode = 0
    stdout = b""
    stderr = b""


def install_desktop_shell_hooks(log=print):
    """Wrap subprocess so pedal shell commands are safe on a desktop."""
    if not IS_DESKTOP or getattr(_subprocess, "_beebo_hooked", False):
        return
    real_call, real_run, real_popen = _subprocess.call, _subprocess.run, _subprocess.Popen
    real_check_output = _subprocess.check_output

    def fix(args, kwargs):
        cmd = args[0] if args else kwargs.get("args")
        if _is_pedal_only(cmd):
            log("desktop: skipping pedal-only command: %s" % (cmd if isinstance(cmd, str) else " ".join(cmd))[:120])
            return None
        if isinstance(cmd, str):
            cmd = shell(cmd)
        elif isinstance(cmd, (list, tuple)):
            cmd = [P(c) if isinstance(c, str) else c for c in cmd]
        if args:
            args = (cmd,) + tuple(args[1:])
        else:
            kwargs["args"] = cmd
        return args, kwargs

    def call(*args, **kwargs):
        r = fix(args, kwargs)
        return 0 if r is None else real_call(*r[0], **r[1])

    def run(*args, **kwargs):
        r = fix(args, kwargs)
        if r is None:
            d = _Done()
            if kwargs.get("universal_newlines") or kwargs.get("text"):
                d.stdout = d.stderr = ""
            return d
        return real_run(*r[0], **r[1])

    def check_output(*args, **kwargs):
        r = fix(args, kwargs)
        if r is None:
            return b"0 0\n"
        return real_check_output(*r[0], **r[1])

    class Popen(real_popen):
        def __init__(self, *args, **kwargs):
            r = fix(args, kwargs)
            if r is None:
                r = ((["true"],), {})
            super().__init__(*r[0], **r[1])

    _subprocess.call, _subprocess.run = call, run
    _subprocess.check_output, _subprocess.Popen = check_output, Popen
    _subprocess._beebo_hooked = True
