#!/usr/bin/env python3
"""Load every Beebo module into a running Ingen and report which ones fail.

    python3 desktop/test_modules.py [socket path]

Ingen must already be running (the desktop launcher starts it). Each module
is added to a scratch graph and removed again; a module that Ingen can't
instantiate shows up as an error response.
"""
import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
sys.path.insert(0, UI)
import module_info  # noqa: E402
from beebo_paths import INGEN_SOCKET  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else INGEN_SOCKET
s = socket.socket(socket.AF_UNIX)
s.connect(path)
s.settimeout(0.2)
buf = b""


def send(msg):
    s.sendall(msg.encode())


def messages(wait):
    """Yield decoded JSON bundles received within `wait` seconds."""
    global buf
    end = time.time() + wait
    while time.time() < end:
        try:
            chunk = s.recv(65536)
            if not chunk:
                return
            buf += chunk
        except socket.timeout:
            pass
        while b"\0" in buf:
            part, buf = buf.split(b"\0", 1)
            try:
                yield json.loads(part.decode("utf-8", "replace"))
            except ValueError:
                pass


uris = {}
for models in module_info.effect_type_maps.values():
    for name, uri in models.items():
        uris.setdefault(uri, name)

send('[] a patch:Put ; patch:subject </main/beebo_test> ; patch:body [ a ingen:Graph ] .\n')
list(messages(0.5))
ok, failed = [], []
for i, (uri, name) in enumerate(sorted(uris.items(), key=lambda x: x[1])):
    sub = "/main/beebo_test/m%d" % i
    send('[] a patch:Put ; patch:subject <%s> ; patch:body [ a ingen:Block ; lv2:prototype <%s> ] .\n' % (sub, uri))
    created, error = False, None
    for bundle in messages(1.0):
        for m in bundle.values():
            types = m.get("a", [])
            if "patch:Put" in types and m.get("patch:subject", [""])[0] == "ingen:" + sub:
                created = True
            if "patch:Response" in types and m.get("patch:body", ["0"]) != ["0"]:
                error = m.get("patch:body")
        if created:
            break
    (ok if created else failed).append((name, uri, error))
    send('[] a patch:Delete ; patch:subject <%s> .\n' % sub)
    list(messages(0.1))
send('[] a patch:Delete ; patch:subject </main/beebo_test> .\n')
print("modules that load: %d of %d" % (len(ok), len(uris)))
for name, uri, err in failed:
    print("  not loaded: %-24s %s" % (name, uri))
