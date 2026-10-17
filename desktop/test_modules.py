#!/usr/bin/env python3
"""Load every Beebo module into Ingen and report which ones fail.

    python3 desktop/test_modules.py [socket path]
    python3 desktop/test_modules.py SOCKET --start INGEN GRAPH [--log FILE]

Without --start, Ingen must already be running (the desktop launcher starts
it). With --start, this script runs Ingen itself and starts it again if a
module crashes it, so one bad module doesn't hide the rest.

Each module is added to a scratch graph and removed again; a module that
Ingen can't instantiate shows up as an error response.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
sys.path.insert(0, UI)
import module_info  # noqa: E402
from beebo_paths import INGEN_SOCKET  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("socket", nargs="?", default=INGEN_SOCKET)
ap.add_argument("--start", nargs=2, metavar=("INGEN", "GRAPH"))
ap.add_argument("--log", default=os.devnull)
args = ap.parse_args()
path = args.socket
ingen = None
s = None
buf = b""
SCRATCH = "/main/beebo_test"


class Crashed(Exception):
    pass


def start_ingen():
    global ingen
    if os.path.lexists(path):
        os.unlink(path)
    logf = open(args.log, "a")
    logf.write("\n--- starting Ingen\n")
    logf.flush()
    ingen = subprocess.Popen([args.start[0], "-e", "-p", "2", "-S", path, args.start[1]],
                             stdout=logf, stderr=subprocess.STDOUT)
    for _ in range(150):
        if os.path.exists(path):
            return
        if ingen.poll() is not None:
            break
        time.sleep(0.2)
    raise SystemExit("Ingen didn't start; see %s" % args.log)


def send(msg):
    try:
        s.sendall(msg.encode())
    except OSError:
        raise Crashed()


def messages(wait):
    """Yield decoded JSON bundles received within `wait` seconds."""
    global buf
    end = time.time() + wait
    while time.time() < end:
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            chunk = None
        except OSError:
            raise Crashed()
        if chunk == b"":
            raise Crashed()
        if chunk:
            buf += chunk
        while b"\0" in buf:
            part, buf = buf.split(b"\0", 1)
            try:
                yield json.loads(part.decode("utf-8", "replace"))
            except ValueError:
                pass


def connect():
    """(Re)connect, starting Ingen first if this script manages it."""
    global s, buf
    if args.start and (ingen is None or ingen.poll() is not None):
        start_ingen()
    for _ in range(150):
        try:
            s = socket.socket(socket.AF_UNIX)
            s.connect(path)
            break
        except OSError:
            s.close()
            time.sleep(0.2)
    else:
        raise SystemExit("can't connect to Ingen at %s" % path)
    s.settimeout(0.2)
    buf = b""
    send('[] a patch:Put ; patch:subject <%s> ; patch:body [ a ingen:Graph ] .\n' % SCRATCH)
    list(messages(0.5))


uris = {}
for models in module_info.effect_type_maps.values():
    for name, uri in models.items():
        uris.setdefault(uri, name)

connect()
ok, failed, crashed = [], [], []
for i, (uri, name) in enumerate(sorted(uris.items(), key=lambda x: x[1])):
    sub = "%s/m%d" % (SCRATCH, i)
    created, error = False, None
    try:
        send('[] a patch:Put ; patch:subject <%s> ; patch:body [ a ingen:Block ; lv2:prototype <%s> ] .\n'
             % (sub, uri))
        for bundle in messages(1.0):
            for m in bundle.values():
                types = m.get("a", [])
                if "patch:Put" in types and m.get("patch:subject", [""])[0] == "ingen:" + sub:
                    created = True
                if "patch:Response" in types and m.get("patch:body", ["0"]) != ["0"]:
                    error = m.get("patch:body")
            if created:
                break
        send('[] a patch:Delete ; patch:subject <%s> .\n' % sub)
        list(messages(0.1))
    except Crashed:
        crashed.append((name, uri))
        print("  Ingen stopped while loading %s (%s)" % (name, uri), flush=True)
        if not args.start or len(crashed) > 25:
            break
        time.sleep(0.5)
        connect()
        continue
    (ok if created else failed).append((name, uri, error))

try:
    send('[] a patch:Delete ; patch:subject <%s> .\n' % SCRATCH)
except Crashed:
    pass
if ingen is not None:
    ingen.terminate()
print("modules that load: %d of %d" % (len(ok), len(uris)))
for name, uri in crashed:
    print("  CRASHES INGEN:  %-24s %s" % (name, uri))
for name, uri, err in failed:
    print("  not loaded: %-24s %s" % (name, uri))
