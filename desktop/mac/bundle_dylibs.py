#!/usr/bin/env python3
"""Make Beebo.app self-contained: copy every non-system library its
programs and plugins use into Contents/Frameworks, point them there with
@loader_path, and ad-hoc sign everything (Apple Silicon refuses to run
unsigned code).

    python3 desktop/mac/bundle_dylibs.py build/mac/Beebo.app
"""
import os
import shutil
import subprocess
import sys

APP = os.path.abspath(sys.argv[1])
FW = os.path.join(APP, "Contents", "Frameworks")
SYSTEM = ("/usr/lib/", "/System/")


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout


def is_macho(path):
    if os.path.islink(path) or not os.path.isfile(path):
        return False
    with open(path, "rb") as f:
        magic = f.read(4)
    return magic in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")


def deps(path):
    out = sh("otool", "-L", path).splitlines()[1:]
    return [l.strip().split(" (")[0] for l in out if l.strip()]


def rpaths(path):
    out = sh("otool", "-l", path).splitlines()
    rp = []
    for i, l in enumerate(out):
        if l.strip() == "cmd LC_RPATH":
            rp.append(out[i + 2].strip().split(" ")[1])
    return rp


def resolve(dep, owner):
    """Find the real file for a dependency (handles @rpath / @loader_path)."""
    if dep.startswith("@rpath/"):
        for rp in rpaths(owner):
            base = rp.replace("@loader_path", os.path.dirname(owner)).replace(
                "@executable_path", os.path.dirname(owner))
            cand = os.path.join(base, dep[len("@rpath/"):])
            if os.path.exists(cand):
                return os.path.realpath(cand)
        for base in ("/opt/homebrew/lib", "/usr/local/lib"):
            cand = os.path.join(base, os.path.basename(dep))
            if os.path.exists(cand):
                return os.path.realpath(cand)
        return None
    if dep.startswith("@loader_path/"):
        cand = os.path.join(os.path.dirname(owner), dep[len("@loader_path/"):])
        return os.path.realpath(cand) if os.path.exists(cand) else None
    if dep.startswith("@"):
        return None
    return os.path.realpath(dep) if os.path.exists(dep) else None


def inside_app(path):
    return os.path.realpath(path).startswith(os.path.realpath(APP) + os.sep)


def relocate(path, todo):
    changed = False
    for dep in deps(path):
        if dep.startswith(SYSTEM):
            continue
        real = resolve(dep, path)
        if real is None:
            continue
        if inside_app(real) and not real.startswith(FW):
            # a library that already lives in the app (e.g. Ingen's own): make
            # an absolute reference to it relative, so the app can be moved
            if dep.startswith("/"):
                rel = os.path.relpath(real, os.path.dirname(path))
                subprocess.run(["install_name_tool", "-change", dep, "@loader_path/" + rel, path],
                               capture_output=True)
                changed = True
            continue
        name = os.path.basename(dep)
        target = os.path.join(FW, name)
        if not os.path.exists(target):
            shutil.copy2(real, target)
            os.chmod(target, 0o755)
            todo.append(target)
        rel = os.path.relpath(FW, os.path.dirname(path))
        new = "@loader_path/" + (name if rel == "." else rel + "/" + name)
        if dep != new:
            subprocess.run(["install_name_tool", "-change", dep, new, path], capture_output=True)
            changed = True
    if path.startswith(FW) or (path.endswith(".dylib") and ("/ingen/lib/" in path or "/jack/lib/" in path)):
        subprocess.run(["install_name_tool", "-id", "@loader_path/" + os.path.basename(path), path],
                       capture_output=True)
        changed = True
    return changed


def main():
    os.makedirs(FW, exist_ok=True)
    files = []
    for root, _, names in os.walk(APP):
        for n in names:
            p = os.path.join(root, n)
            if is_macho(p):
                files.append(p)
    todo = list(files)
    done = set()
    while todo:
        p = todo.pop()
        if p in done:
            continue
        done.add(p)
        os.chmod(p, os.stat(p).st_mode | 0o200)
        relocate(p, todo)
    # sign innermost first, then the app
    for p in sorted(done, key=lambda x: -x.count(os.sep)):
        subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", p],
                       capture_output=True)
    r = subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", APP],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stderr)
    # report anything still pointing outside the app
    bad = []
    for p in done:
        own_id = sh("otool", "-D", p).splitlines()[1:]  # a library's own name isn't a dependency
        for dep in deps(p):
            if dep in own_id:
                continue
            if dep.startswith(("/opt/homebrew", "/usr/local", "/Users/")):
                bad.append((p, dep))
    for p, dep in bad[:50]:
        print("still external: %s -> %s" % (os.path.relpath(p, APP), dep))
    print("bundled %d Mach-O files, %d libraries in Frameworks, %d external references left"
          % (len(done), len(os.listdir(FW)), len(bad)))


if __name__ == "__main__":
    main()
