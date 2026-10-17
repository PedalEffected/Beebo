#!/usr/bin/env python3
"""Build the LV2 modules the Beebo screen offers, for this computer.

    python3 desktop/build_plugins.py --out STAGE/lv2 [--work DIR] [--only a,b]

Each entry in RECIPES fetches one open-source project (at a fixed commit
where possible), builds just the plugins Beebo uses, and installs the LV2
bundles into --out. A recipe that fails is reported and skipped; the rest
carry on. At the end every module URI in module_info.py is checked against
what was installed, and a report (plugins-report.json / .md) says which
modules are available and which aren't, and why.

Works on macOS (Apple Silicon or Intel) and Linux.
"""
import argparse
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
DARWIN = sys.platform == "darwin"
ARCH = platform.machine()
JOBS = str(os.cpu_count() or 2)

# Portable optimisation flags (the projects' defaults are x86 SSE or
# Cortex-A53 specific).
OPT = "-O3 -ffast-math -fno-finite-math-only -fomit-frame-pointer -DNDEBUG"

LOG = None


def log(*a):
    msg = " ".join(str(x) for x in a)
    print(msg, flush=True)
    if LOG:
        LOG.write(msg + "\n")
        LOG.flush()


def run(cmd, cwd=None, env=None, check=True):
    e = dict(os.environ)
    if env:
        e.update(env)
    shown = cmd if isinstance(cmd, str) else " ".join(cmd)
    log("$ (%s) %s" % (os.path.relpath(cwd or ".", WORK) if cwd else ".", shown))
    p = subprocess.run(cmd, cwd=cwd, env=e, shell=isinstance(cmd, str),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if LOG:
        LOG.write(p.stdout)
    if check and p.returncode != 0:
        tail = "\n".join(p.stdout.splitlines()[-40:])
        raise RuntimeError("command failed (%d): %s\n%s" % (p.returncode, shown, tail))
    return p.stdout


# ------------------------------------------------------------------ fetching

def git(name, url, ref=None, submodules=False):
    """Clone url into WORK/name (shallow), at ref if given."""
    dest = os.path.join(WORK, name)
    if not os.path.isdir(os.path.join(dest, ".git")):
        if ref and re.fullmatch(r"[0-9a-f]{7,40}", ref):
            os.makedirs(dest, exist_ok=True)
            run(["git", "init", "-q"], cwd=dest)
            run(["git", "remote", "add", "origin", url], cwd=dest)
            run(["git", "fetch", "-q", "--depth", "1", "origin", ref], cwd=dest)
            run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=dest)
        else:
            args = ["git", "clone", "-q", "--depth", "1"]
            if ref:
                args += ["--branch", ref]
            run(args + [url, dest])
    if submodules:
        run(["git", "submodule", "update", "--init", "--recursive", "--depth", "1", "-q"], cwd=dest)
    commit = run(["git", "rev-parse", "--short", "HEAD"], cwd=dest).strip()
    SOURCES[name] = {"url": url, "commit": commit}
    return dest


def tarball(name, url):
    dest = os.path.join(WORK, name)
    if not os.path.isdir(dest):
        arc = os.path.join(WORK, os.path.basename(url))
        if not os.path.exists(arc):
            log("download", url)
            urllib.request.urlretrieve(url, arc)
        with tarfile.open(arc) as t:
            top = t.getnames()[0].split("/")[0]
            t.extractall(WORK)
        os.rename(os.path.join(WORK, top), dest)
    SOURCES[name] = {"url": url}
    return dest


# ------------------------------------------------------------------ building

# CMake 4 refuses projects that declare a minimum version below 3.5
CMAKE_OLD_OK = "-DCMAKE_POLICY_VERSION_MINIMUM=3.5"


def darwin_setup():
    """macOS differences that affect many projects at once."""
    # GNU install (several Makefiles use "install -t", which macOS lacks)
    for prefix in ("/opt/homebrew", "/usr/local"):
        gnubin = os.path.join(prefix, "opt", "coreutils", "libexec", "gnubin")
        if os.path.isdir(gnubin):
            os.environ["PATH"] = gnubin + os.pathsep + os.environ["PATH"]
            break
    # Homebrew's LV2 only has the current header layout (lv2/core/lv2.h).
    # Older plugins include lv2/lv2plug.in/ns/... or a bare lv2.h, so add
    # a folder that maps those names onto the installed headers.
    try:
        inc = subprocess.run(["pkg-config", "--variable=includedir", "lv2"],
                             capture_output=True, text=True).stdout.strip()
    except OSError:
        inc = ""
    lv2 = os.path.join(inc, "lv2")
    if not os.path.isdir(os.path.join(lv2, "core")):
        return
    compat = os.path.join(WORK, "_lv2compat")
    ns = os.path.join(compat, "lv2", "lv2plug.in", "ns")
    for sub in ("ext", "extensions"):
        os.makedirs(os.path.join(ns, sub), exist_ok=True)
    for d in sorted(os.listdir(lv2)):
        if not os.path.isdir(os.path.join(lv2, d)) or d == "lv2plug.in":
            continue
        if d == "core":
            link = os.path.join(ns, "lv2core")
        elif d in ("ui", "units"):
            link = os.path.join(ns, "extensions", d)
        else:
            link = os.path.join(ns, "ext", d)
        if not os.path.lexists(link):
            os.symlink(os.path.join(lv2, d), link)
    with open(os.path.join(compat, "lv2.h"), "w") as f:
        f.write('#include "%s"\n' % os.path.join(lv2, "core", "lv2.h"))
    # the compat folder first, then the real headers (some Makefiles replace
    # CFLAGS entirely, so pkg-config's -I never reaches the compiler)
    extra = compat + os.pathsep + inc
    os.environ["CPATH"] = extra + (os.pathsep + os.environ["CPATH"] if os.environ.get("CPATH") else "")
    log("macOS: LV2 header compatibility folder", compat)


def patch_file(path, old, new, count=1):
    """Small source fix-up; does nothing if already applied."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    if old in text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new, count))


GNU_LD_FLAGS = ("-Wl,--as-needed", "-Wl,--strip-all", "-Wl,--no-undefined", "-Wl,--gc-sections",
                "-Wl,-O1", "-Wl,--exclude-libs,ALL")


def strip_gnu_ld_flags(root):
    """macOS's linker rejects GNU ld options some Makefiles hard-code."""
    if not DARWIN:
        return
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.startswith("Makefile") or f.endswith((".mk", ".mak")):
                for flag in GNU_LD_FLAGS:
                    patch_file(os.path.join(dirpath, f), flag, "", count=-1)


def make(path, *targets, **vars):
    if DARWIN and "STRIP" not in vars:
        # several Makefiles pass GNU strip options (or strip one file from
        # parallel jobs); stripping only saves space, so skip it on macOS
        vars["STRIP"] = "true"
    if DARWIN and "CXX" not in vars:
        # Apple's compiler still defaults to C++98; these projects expect a
        # modern standard (GCC on Linux defaults to C++17; C++14 still
        # accepts the old "register" keyword some of them use)
        vars["CXX"] = "c++ -std=gnu++14"
    args = ["make", "-j", JOBS] + list(targets)
    args += ["%s=%s" % (k, v) for k, v in vars.items()]
    return run(args, cwd=path)


def make_install(path, **vars):
    v = {"OPTIMIZATIONS": OPT, "PREFIX": "/usr", "LV2DIR": OUT, "DESTDIR": ""}
    v.update(vars)
    make(path, **{k: v[k] for k in v if k != "DESTDIR"})
    make(path, "install", **v)


def meson_install(path, *opts):
    build = os.path.join(path, "build-beebo")
    if not os.path.isdir(build):
        run(["meson", "setup", build, "--prefix", os.path.join(WORK, "_prefix"),
             "-Dlv2dir=" + OUT, "--buildtype=release"] + list(opts), cwd=path)
    run(["ninja", "-C", build, "install"], cwd=path)


def cmake_install(path, *opts):
    build = os.path.join(path, "build-beebo")
    run(["cmake", "-S", path, "-B", build, "-DCMAKE_BUILD_TYPE=Release", CMAKE_OLD_OK,
         "-DCMAKE_INSTALL_PREFIX=" + os.path.join(WORK, "_prefix")] + list(opts))
    run(["cmake", "--build", build, "-j", JOBS])
    return build


def copy_bundle(src, name=None):
    """Copy a built bundle folder into OUT (replacing an older copy)."""
    dst = os.path.join(OUT, name or os.path.basename(src.rstrip("/")))
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=False)
    return dst


# ------------------------------------------------------------------ recipes
# Each recipe builds and installs bundles into OUT. Keep them small: build
# only what Beebo uses, skip GUIs (the Beebo screen is the GUI).

def r_beebo_custom():
    """BiPoSeq and Droplets, from this repo."""
    make_install(os.path.join(UI, "biposeq", "lv2"), CFLAGS=OPT + " -Wall")
    make_install(os.path.join(UI, "droplets", "lv2"), CXXFLAGS=OPT)


def r_polylv2():
    src = git("PolyLV2", "https://github.com/polyeffects/PolyLV2")
    failed = []
    for d in sorted(os.listdir(src)):
        p = os.path.join(src, d)
        if os.path.isfile(os.path.join(p, "Makefile")):
            try:
                make_install(p)
            except RuntimeError as e:
                failed.append(d)
                log("  ! PolyLV2/%s failed: %s" % (d, e))
    if failed:
        raise RuntimeError("PolyLV2 parts failed: " + ", ".join(failed))


def r_lenticular():
    src = git("lenticular_lv2", "https://github.com/polyeffects/lenticular_lv2", submodules=True)
    # a stray "" line in one recipe makes make try to run an empty command
    patch_file(os.path.join(src, "Makefile"), '$(BUILDDIR)$(LV2NAME_RINGS).ttl\n\t""\n', '$(BUILDDIR)$(LV2NAME_RINGS).ttl\n')
    make_install(src)


def r_poly_filters():
    src = git("poly_filters", "https://github.com/polyeffects/poly_filters")
    # the Makefile expects poly_filter.cpp; the file is poly_filters.cpp
    if not os.path.exists(os.path.join(src, "poly_filter.cpp")):
        shutil.copy(os.path.join(src, "poly_filters.cpp"), os.path.join(src, "poly_filter.cpp"))
    # uses std::tan / std::pow without including <cmath> (GCC lets that pass)
    patch_file(os.path.join(src, "poly_filter.cpp"), '#include <math.h>', '#include <math.h>\n#include <cmath>')
    make_install(src)


def r_polyconvo():
    src = git("polyconvo.lv2", "https://github.com/polyeffects/polyconvo.lv2")
    # uses std::string / std::min without including them (GCC lets that pass)
    make_install(src, STATICZITA="yes",
                 CXXFLAGS=OPT + " -Wall -include string -include algorithm -include cmath")


def r_tuna():
    src = git("tuna.lv2", "https://github.com/polyeffects/tuna.lv2", submodules=True)
    make_install(src, MOD="1", BUILDOPENGL="no", BUILDJACKAPP="no")


def _x42(name, **vars):
    src = git(name, "https://github.com/x42/%s" % name, submodules=True)
    v = {"MOD": "1", "BUILDOPENGL": "no", "BUILDGTK": "no", "BUILDJACKAPP": "no"}
    v.update(vars)
    make_install(src, **v)


def r_midifilter():
    _x42("midifilter.lv2")


def r_darc():
    _x42("darc.lv2", INLINEDISPLAY="no")


def r_fil4():
    _x42("fil4.lv2")


def r_matrixmixer():
    # Beebo uses the 4-in / 3-out variant
    _x42("matrixmixer.lv2", N_INPUTS="4", N_OUTPUTS="3")


def r_mclk():
    _x42("mclk.lv2")


def r_zconvo():
    _x42("zconvo.lv2", STATICZITA="yes")


def r_bwhirl():
    src = git("setBfree", "https://github.com/pantherb/setBfree")
    # only the rotary speaker (b_whirl), DSP only
    v = {"OPTIMIZATIONS": OPT, "ENABLE_CONVOLUTION": "no", "RW": "/nonexistent/"}
    make(src + "/b_whirl", **v)
    make(src + "/b_whirl", "install", PREFIX="/usr", lv2dir=OUT, LV2DIR=OUT, **v)
    # it installs as "b_whirl"; name the bundle like the others
    if os.path.isdir(os.path.join(OUT, "b_whirl")):
        if os.path.isdir(os.path.join(OUT, "b_whirl.lv2")):
            shutil.rmtree(os.path.join(OUT, "b_whirl.lv2"))
        os.rename(os.path.join(OUT, "b_whirl"), os.path.join(OUT, "b_whirl.lv2"))


def r_tap():
    src = git("tap-lv2", "https://github.com/moddevices/tap-lv2")
    # The shared Makefile.mk uses GNU-ld-only link flags and x86 SSE flags,
    # so give the flags on the command line (which overrides its +=).
    for d in ("pitch", "reflector", "sigmoid", "tubewarmth"):
        p = os.path.join(src, d)
        flags = dict(NOOPT="true", CFLAGS=OPT + " -fPIC -DPIC -I../utils",
                     LDFLAGS="-shared -lm" + ("" if DARWIN else " -lrt"))
        make(p, **flags)
        make(p, "install", INSTALL_PATH=OUT, **flags)


def r_mod_cv():
    src = git("mod-cv-plugins", "https://github.com/moddevices/mod-cv-plugins", submodules=True)
    p = os.path.join(src, "source", "mod-cv-meter")
    if not os.path.isdir(p):
        p = [d for d in glob.glob(os.path.join(src, "**", "*cv-meter*"), recursive=True) if os.path.isdir(d)][0]
    strip_gnu_ld_flags(src)
    make(p, "NOOPT=true", "HAVE_OPENGL=false", "HAVE_CAIRO=false")
    for b in glob.glob(os.path.join(src, "**", "mod-cv-meter.lv2"), recursive=True):
        dst = copy_bundle(b)
        # upstream .ttl has an unterminated string, which makes it unloadable
        patch_file(os.path.join(dst, "mod-cv-meter.ttl"),
                   'doap:license "http://spdx.org/licenses/GPL-2.0-or-later.html ;',
                   'doap:license <http://spdx.org/licenses/GPL-2.0-or-later.html> ;')
        break


def _dpf(name, url, plugin_dirs, bundles, submodules=True):
    src = git(name, url, submodules=submodules)
    for d in plugin_dirs:
        make(os.path.join(src, d), "lv2_dsp", "NOOPT=true", "HAVE_OPENGL=false",
             "HAVE_CAIRO=false", "HAVE_DGL=false", "WITH_LTO=false")
    # the .ttl files are generated by loading the built plugin
    dpf = os.path.join(src, "dpf")
    make(os.path.join(dpf, "utils", "lv2-ttl-generator"))
    run(["bash", os.path.join(dpf, "utils", "generate-ttl.sh")], cwd=src)
    for b in bundles:
        found = glob.glob(os.path.join(src, "**", b), recursive=True)
        if not found:
            raise RuntimeError("%s not built" % b)
        copy_bundle(found[0])


def r_stone_phaser():
    _dpf("stone-phaser", "https://github.com/jpcima/stone-phaser",
         ["plugins/stone-phaser", "plugins/stone-phaser-stereo"],
         ["stone-phaser.lv2", "stone-phaser-stereo.lv2"])


def r_ykchorus():
    _dpf("ykchorus", "https://github.com/SpotlightKid/ykchorus", ["plugins/YKChorus"],
         ["ykchorus.lv2"])


def r_mverb():
    _dpf("DPF-Plugins", "https://github.com/DISTRHO/DPF-Plugins", ["plugins/MVerb"],
         ["MVerb.lv2"])


def r_infamous():
    src = git("infamousPlugins", "https://github.com/ssj71/infamousPlugins")
    build = os.path.join(src, "build-beebo")
    os.makedirs(build, exist_ok=True)
    out = os.path.join(WORK, "_infamous")
    # GUIs need NTK, which isn't available on macOS; the plugins work without.
    run(["cmake", "..", "-DCMAKE_BUILD_TYPE=Release", CMAKE_OLD_OK, "-DCMAKE_INSTALL_PREFIX=" + out,
         "-DLIBDIR=lib", "-DLV2_INSTALL_DIR=" + out + "/lv2"], cwd=build)
    for t in ("envfollower", "powercut", "stuck"):
        run(["cmake", "--build", ".", "--target", t, "-j", JOBS], cwd=build)
    for t in ("envfollower", "powercut", "stuck"):
        lib = [f for f in glob.glob(os.path.join(build, "src", t, t + ".*"))
               if f.endswith((".so", ".dylib"))]
        if not lib:
            raise RuntimeError("%s not built" % t)
        dst = os.path.join(OUT, t + ".lv2")
        os.makedirs(dst, exist_ok=True)
        shutil.copy(lib[0], os.path.join(dst, t + ".so"))
        for ttl in ("manifest.ttl", t + ".ttl"):
            shutil.copy(os.path.join(src, "src", t, ttl), dst)


def r_midimsg():
    """Compiled directly: its bundled waf doesn't run on current Python."""
    src = git("midimsg-lv2", "https://github.com/blablack/midimsg-lv2")
    out = os.path.join(OUT, "midimsg.lv2")
    os.makedirs(out, exist_ok=True)
    for n in ("controller", "modwheel", "aftertouch"):
        run("{cxx} {opt} -fPIC -shared -I{src}/src {src}/src/{n}.cpp $(pkg-config --cflags lv2) "
            "-o {out}/{n}.so".format(cxx=os.environ.get("CXX", "c++"), opt=OPT, src=src, n=n, out=out))
    for ttl in glob.glob(os.path.join(src, "midimsg.lv2", "*.ttl")):
        shutil.copy(ttl, out)


def r_nam():
    src = git("neural-amp-modeler-lv2", "https://github.com/polyeffects/neural-amp-modeler-lv2",
              submodules=True)
    # libstdc++fs is GCC's; on macOS std::filesystem is in libc++ itself
    patch_file(os.path.join(src, "CMakeLists.txt"), "link_libraries(stdc++fs)",
               "if(NOT APPLE)\n  link_libraries(stdc++fs)\nendif()")
    build = cmake_install(src, "-DUSE_NATIVE_ARCH=OFF")
    found = glob.glob(os.path.join(build, "**", "neural_amp_modeler.lv2"), recursive=True)
    if not found:
        raise RuntimeError("neural_amp_modeler.lv2 not built")
    copy_bundle(found[0])


def _build_drobilla_src(src):
    if os.path.exists(os.path.join(src, "meson.build")):
        meson_install(src)
    else:
        run([sys.executable, "waf", "configure", "--prefix=/usr", "--lv2dir=" + OUT], cwd=src)
        run([sys.executable, "waf", "build"], cwd=src)
        run([sys.executable, "waf", "install"], cwd=src)


def _drobilla(name, version):
    url = "https://download.drobilla.net/%s-%s.tar.xz" % (name, version)
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30)
    except Exception:
        # not there: take the newest release listed on the download page
        index = urllib.request.urlopen("https://download.drobilla.net/", timeout=30).read().decode()
        base = re.escape(name.replace("-lv2", "").replace(".lv2", ""))
        found = re.findall(r'href="(%s(?:[.-]lv2)?-([0-9.]+)\.tar\.(?:xz|bz2|gz))"' % base, index)
        if not found:
            names = sorted(set(re.findall(r'href="([^"]*%s[^"]*)"' % base, index)))
            raise RuntimeError("no %s release on download.drobilla.net (listed: %s)"
                               % (name, ", ".join(names) or "none"))
        best = max(found, key=lambda f: [int(x) for x in f[1].split(".") if x.isdigit()])
        url = "https://download.drobilla.net/" + best[0]
    src = tarball(name, url)
    if os.path.exists(os.path.join(src, "meson.build")):
        meson_install(src)
    else:
        run([sys.executable, "waf", "configure", "--prefix=/usr", "--lv2dir=" + OUT], cwd=src)
        run([sys.executable, "waf", "build"], cwd=src)
        run([sys.executable, "waf", "install"], cwd=src)


def _patch_blop_product(src):
    """blop's product (Beebo's attenuverter) has "morph" ports whose type the
    host is meant to switch, and an output whose type follows the inputs.
    Ingen leaves that auto-switching output unconnected, so the plugin writes
    through a null pointer and takes the engine down. Beebo only uses it with
    CV, so make it a plain CV module."""
    ttl = os.path.join(src, "blop.lv2", "product.ttl")
    with open(ttl, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"a lv2:ControlPort ,\s*lv2:(Input|Output)Port ,\s*morph:(?:Auto)?MorphPort ;",
                  r"a lv2:CVPort ,\n\t\t\tlv2:\1Port ;", text)
    text = re.sub(r"\s*morph:supportsType lv2:ControlPort ,\s*lv2:CVPort\s*", "\n\t", text)
    with open(ttl, "w", encoding="utf-8") as f:
        f.write(text)
    c = os.path.join(src, "src", "product.c")
    patch_file(c, "\tplugin->input1_is_cv = 0;\n\tplugin->input2_is_cv = 0;\n\tplugin->output_is_cv = 0;",
               "\tplugin->input1_is_cv = 1;\n\tplugin->input2_is_cv = 1;\n\tplugin->output_is_cv = 1;\n"
               "\tplugin->input1 = plugin->input2 = NULL;\n\tplugin->output = NULL;")
    patch_file(c, "\tfloat* const         output = plugin->output;\n",
               "\tfloat* const         output = plugin->output;\n"
               "\tif (!input1 || !input2 || !output) {\n\t\treturn;\n\t}\n")


def r_blop():
    src = tarball("blop-lv2", "https://download.drobilla.net/blop-lv2-1.0.4.tar.xz")
    _patch_blop_product(src)
    _build_drobilla_src(src)


def r_omins():
    # omins has no release tarball on download.drobilla.net; use its git repo
    for url in ("https://gitlab.com/drobilla/omins.lv2", "https://gitlab.com/drobilla/omins-lv2",
                "https://gitlab.com/drobilla/omins", "https://git.drobilla.net/omins.lv2"):
        if subprocess.run(["git", "ls-remote", "-q", url], capture_output=True,
                          env=dict(os.environ, GIT_TERMINAL_PROMPT="0")).returncode == 0:
            log("omins source:", url)
            _build_drobilla_src(git("omins", url))
            return
    raise RuntimeError("omins source not found (tried gitlab.com/drobilla and git.drobilla.net)")


def r_fomp():
    _drobilla("fomp", "1.2.4")


def r_mda():
    _drobilla("mda-lv2", "1.2.10")


def r_avw():
    """The five avw modules Beebo uses, compiled directly (the project's
    own build wants GTK 2 for its GUIs)."""
    src = git("avwlv2", "https://github.com/polyeffects/avwlv2")
    lvtk = git("lvtk", "https://github.com/lvtk/lvtk", "1.2.0")
    # avw includes <lvtk-1/lvtk/plugin.hpp>
    inc = os.path.join(WORK, "_lvtk_include")
    os.makedirs(inc, exist_ok=True)
    if not os.path.exists(os.path.join(inc, "lvtk-1")):
        os.symlink(lvtk, os.path.join(inc, "lvtk-1"))
    names = {"lfo_tempo": "lfo_tempo", "samplehold": "samplehold", "slew": "slew",
             "vcaexp_audio": "vcaexp_audio", "vcpanning": "vcpanning"}
    bundle_src = os.path.join(src, "avw.lv2")
    out = os.path.join(OUT, "avw.lv2")
    os.makedirs(out, exist_ok=True)
    for n in names:
        cpp = os.path.join(src, "src", n + ".cpp")
        if not os.path.exists(cpp):
            cpp = glob.glob(os.path.join(src, "**", n + ".cpp"), recursive=True)[0]
        run("{cxx} {opt} -std=c++11 -fPIC -shared -I{inc} -I{lvtk} -I{src}/src {cpp} {src}/src/synthdata.cpp {lvtk}/src/plugin.cpp "
            "$(pkg-config --cflags lv2) -o {out}/{n}.so".format(
                cxx=os.environ.get("CXX", "c++"), opt=OPT, inc=inc, lvtk=lvtk, src=src, cpp=cpp, n=n,
                out=out))
    for ttl in glob.glob(os.path.join(bundle_src, "*.ttl")):
        shutil.copy(ttl, out)


def r_gx():
    src = git("GxPlugins.lv2", "https://github.com/brummer10/GxPlugins.lv2", submodules=True)
    # "make mod" builds the plugin without its X11 GUI
    for d in ("GxCreamMachine.lv2", "GxSVT.lv2", "GxSlowGear.lv2", "GxSupersonic.lv2"):
        p = os.path.join(src, d)
        if DARWIN:
            # ELF section names (".rt.text") aren't valid in Mach-O; the
            # sections are only a hint for memory locking, so drop them
            for f in glob.glob(os.path.join(p, "plugin", "*.cpp")):
                patch_file(f, '__attribute__((section(".rt.text")))', "", count=-1)
                patch_file(f, '__attribute__((section(".rt.data")))', "", count=-1)
            strip_gnu_ld_flags(p)
        make(p, "mod")
        built = [b for b in glob.glob(os.path.join(p, "gx_*.lv2")) if os.path.isfile(os.path.join(b, "manifest.ttl"))]
        if not built:
            raise RuntimeError("%s: no bundle built" % d)
        for b in built:
            copy_bundle(b)


def r_calf_vinyl():
    raise RuntimeError("Calf (vinyl) isn't built yet: Calf's build pulls in its whole plugin set")


RECIPES = [
    ("beebo-custom", r_beebo_custom),
    ("PolyLV2", r_polylv2),
    ("lenticular", r_lenticular),
    ("poly_filters", r_poly_filters),
    ("polyconvo", r_polyconvo),
    ("tuna", r_tuna),
    ("midifilter", r_midifilter),
    ("darc", r_darc),
    ("fil4", r_fil4),
    ("matrixmixer", r_matrixmixer),
    ("mclk", r_mclk),
    ("zconvo", r_zconvo),
    ("b_whirl", r_bwhirl),
    ("tap", r_tap),
    ("mod-cv-meter", r_mod_cv),
    ("stone-phaser", r_stone_phaser),
    ("ykchorus", r_ykchorus),
    ("mverb", r_mverb),
    ("infamous", r_infamous),
    ("midimsg", r_midimsg),
    ("nam", r_nam),
    ("blop", r_blop),
    ("omins", r_omins),
    ("fomp", r_fomp),
    ("mda", r_mda),
    ("avw", r_avw),
    ("guitarix", r_gx),
    ("calf-vinyl", r_calf_vinyl),
]


# ------------------------------------------------------------------ checking

def fix_binaries():
    """Make every lv2:binary named in a bundle's .ttl files exist.

    Many Makefiles name the library .dylib on macOS while their .ttl files
    say .so (or the other way round). dlopen doesn't mind the extension, so
    rename the file to what the .ttl says."""
    for bundle in glob.glob(os.path.join(OUT, "*.lv2")):
        names = set()
        for ttl in glob.glob(os.path.join(bundle, "*.ttl")):
            with open(ttl, encoding="utf-8", errors="ignore") as f:
                names.update(re.findall(r"lv2:binary\s*<([^>]+)>", f.read()))
        for n in names:
            want = os.path.join(bundle, n)
            if os.path.exists(want):
                continue
            stem = os.path.splitext(want)[0]
            for ext in (".so", ".dylib", ".bundle"):
                if os.path.exists(stem + ext):
                    os.rename(stem + ext, want)
                    log("  renamed %s -> %s" % (os.path.basename(stem + ext), n))
                    break


def fill_missing_seealso():
    """Some bundles list data files they don't ship (DPF plugins built without
    their MOD GUI still name modgui.ttl). lilv then refuses to instantiate the
    plugin, so give each missing file a valid, empty body."""
    for bundle in glob.glob(os.path.join(OUT, "*.lv2")):
        for ttl in glob.glob(os.path.join(bundle, "*.ttl")):
            with open(ttl, encoding="utf-8", errors="ignore") as f:
                text = f.read()
            for ref in re.findall(r"<([^>:/]+\.ttl)>", text):
                path = os.path.join(bundle, ref)
                if not os.path.exists(path):
                    with open(path, "w") as f:
                        f.write("@prefix lv2: <http://lv2plug.in/ns/lv2core#> .\n")
                    log("  added empty %s/%s" % (os.path.basename(bundle), ref))


def installed_plugins():
    """URI -> bundle for everything in OUT, by reading the manifests."""
    found = {}
    for bundle in glob.glob(os.path.join(OUT, "*.lv2")):
        for ttl in glob.glob(os.path.join(bundle, "*.ttl")):
            with open(ttl, encoding="utf-8", errors="ignore") as f:
                text = f.read()
            prefixes = dict(re.findall(r"@prefix\s+(\w*):\s*<([^>]+)>", text))
            for m in re.finditer(r"(<[^>]+>|[\w-]+:[\w#/.-]+)\s+(?:a|rdf:type)\s+(?:lv2:Plugin|<http://lv2plug.in/ns/lv2core#Plugin>)", text):
                s = m.group(1)
                if s.startswith("<"):
                    uri = s[1:-1]
                else:
                    p, local = s.split(":", 1)
                    uri = prefixes.get(p, p + ":") + local
                found[uri] = os.path.basename(bundle)
    return found


def check_against_modules(results):
    sys.path.insert(0, UI)
    import module_info
    wanted = {}
    for models in module_info.effect_type_maps.values():
        for name, uri in models.items():
            wanted.setdefault(uri, []).append(name)
    have = installed_plugins()
    modules = []
    for uri, names in sorted(wanted.items()):
        modules.append({"modules": sorted(set(names)), "uri": uri,
                        "bundle": have.get(uri), "available": uri in have})
    ok = sum(1 for m in modules if m["available"])
    report = {"built": time.strftime("%Y-%m-%d %H:%M:%S"), "platform": "%s %s" % (sys.platform, ARCH),
              "recipes": results, "sources": SOURCES, "modules": modules,
              "summary": {"modules_available": ok, "modules_total": len(modules)}}
    with open(os.path.join(REPORT_DIR, "plugins-report.json"), "w") as f:
        json.dump(report, f, indent=1)
    lines = ["# Beebo desktop: module build report", "",
             "%s, %s. **%d of %d modules available.**" % (report["built"], report["platform"], ok, len(modules)), "",
             "## Recipes", "", "| Recipe | Result | Note |", "| --- | --- | --- |"]
    for r in results:
        lines.append("| %s | %s | %s |" % (r["recipe"], "ok" if r["ok"] else "**failed**",
                                         (r.get("error") or "").splitlines()[0][:120].replace("|", "/") if not r["ok"] else ""))
    lines += ["", "## Modules not available", "", "| Module | Plugin URI |", "| --- | --- |"]
    for m in modules:
        if not m["available"]:
            lines.append("| %s | `%s` |" % (", ".join(m["modules"]), m["uri"]))
    with open(os.path.join(REPORT_DIR, "plugins-report.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    log("\n%d of %d modules available" % (ok, len(modules)))


def main():
    global WORK, OUT, LOG, REPORT_DIR, SOURCES
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="folder to install LV2 bundles into")
    ap.add_argument("--work", default=os.path.join(UI, "build", "plugins"), help="build folder")
    ap.add_argument("--only", help="comma-separated recipe names")
    ap.add_argument("--report-dir", help="where to write the report (default: --work)")
    args = ap.parse_args()
    WORK = os.path.abspath(args.work)
    OUT = os.path.abspath(args.out)
    REPORT_DIR = os.path.abspath(args.report_dir or WORK)
    SOURCES = {}
    for d in (WORK, OUT, REPORT_DIR):
        os.makedirs(d, exist_ok=True)
    LOG = open(os.path.join(REPORT_DIR, "plugins-build.log"), "a")
    only = set(args.only.split(",")) if args.only else None
    if DARWIN:
        darwin_setup()
    results = []
    for name, fn in RECIPES:
        if only and name not in only:
            continue
        log("\n=== %s" % name)
        t = time.time()
        try:
            fn()
            results.append({"recipe": name, "ok": True, "seconds": round(time.time() - t)})
            log("=== %s: ok" % name)
        except Exception as e:  # keep going: one project failing shouldn't stop the rest
            results.append({"recipe": name, "ok": False, "error": str(e),
                            "seconds": round(time.time() - t)})
            log("=== %s: FAILED\n%s" % (name, e))
            LOG.write(traceback.format_exc())
    fix_binaries()
    fill_missing_seealso()
    check_against_modules(results)


WORK = OUT = REPORT_DIR = None
SOURCES = {}

if __name__ == "__main__":
    main()
