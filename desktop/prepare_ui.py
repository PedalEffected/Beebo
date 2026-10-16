#!/usr/bin/env python3
"""Generate the files the Beebo screen needs that aren't stored in git.

    python3 desktop/prepare_ui.py [UI folder]

- qml/controls/      the PolyControls module (copied from poly_style/, with
                     its polyconst.js import adjusted for its new location)
- desktop/qml_shims/poly_style/
                     poly_style as a Qt 6 style module (qmldir + controls)
- qml/module_info.js the module list, from module_info.py
- stand-in icons for artwork that's only on the pedal

With --qt6 it also removes version numbers from QML imports
("import QtQuick 2.4" -> "import QtQuick"). Qt 6 checks those numbers
strictly and rejects properties newer than the version named, while Qt 5
requires them, so only do this to a copy that will run on Qt 6 (the Mac app).

Safe to run again; it only rewrites generated files.
"""
import os
import re
import subprocess
import sys

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
QT6 = "--qt6" in sys.argv
UI = os.path.abspath(ARGS[0] if ARGS else os.path.join(os.path.dirname(__file__), ".."))
STYLE = os.path.join(UI, "poly_style")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def controls_module():
    out = os.path.join(UI, "qml", "controls")
    if os.path.islink(out):
        os.unlink(out)
    os.makedirs(out, exist_ok=True)
    for name in sorted(os.listdir(STYLE)):
        if name.endswith(".qml"):
            with open(os.path.join(STYLE, name), encoding="utf-8") as f:
                text = f.read()
            write(os.path.join(out, name), text.replace('"../qml/polyconst.js"', '"../polyconst.js"'))


def qt6_style_module():
    out = os.path.join(UI, "desktop", "qml_shims", "poly_style")
    os.makedirs(out, exist_ok=True)
    names = sorted(n for n in os.listdir(STYLE) if n.endswith(".qml"))
    rel = os.path.relpath(os.path.join(UI, "qml", "polyconst.js"), out).replace(os.sep, "/")
    for name in names:
        with open(os.path.join(STYLE, name), encoding="utf-8") as f:
            text = f.read()
        write(os.path.join(out, name), text.replace('"../qml/polyconst.js"', '"%s"' % rel))
    qmldir = ["module poly_style", "import QtQuick.Controls.Material auto"]
    qmldir += ["%s 2.0 %s" % (n[:-4], n) for n in names]
    write(os.path.join(out, "qmldir"), "\n".join(qmldir) + "\n")


def module_info_js():
    subprocess.check_call([sys.executable, "effect_proto_to_js.py"], cwd=UI,
                          stdout=subprocess.DEVNULL)


def icons():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow not installed: skipping stand-in icons")
        return
    subprocess.check_call([sys.executable, os.path.join(UI, "desktop", "make_placeholder_icons.py"), UI])


_IMPORT = re.compile(r"^(\s*import\s+[A-Za-z][\w.]*)\s+\d+(?:\.\d+)?(\s+as\s+\w+)?\s*$", re.M)


def _controls_last(text):
    """On Qt 6, `import QtQuick.Controls.Material` brings Material's own
    Button, Slider, ... into scope and hides the poly_style ones that Qt 5
    used. Importing poly_style again after it puts them back in front."""
    if not re.search(r"^\s*import QtQuick\.Controls\.Material\s*$", text, re.M):
        return text
    if re.search(r"^\s*import poly_style\s*$", text, re.M):
        return text
    lines = text.split("\n")
    last = max(i for i, l in enumerate(lines) if l.strip().startswith("import "))
    lines.insert(last + 1, "import poly_style")
    return "\n".join(lines)


def _material_button_colors(text):
    """Qt 6 turned Material.buttonColor / highlightedButtonColor /
    buttonDisabledColor into one function, buttonColor(theme, background,
    accent, enabled, flat, highlighted, checked)."""
    def repl(m):
        obj, name = m.group(1) or "", m.group(2)
        o = obj  # "control." or ""
        enabled = "false" if name == "buttonDisabledColor" else (o + "enabled" if o else "true")
        highlighted = "true" if name == "highlightedButtonColor" else "false"
        return ("%sMaterial.buttonColor(%sMaterial.theme, %sMaterial.background, %sMaterial.accent, "
                "%s, false, %s, false)" % (o, o, o, o, enabled, highlighted))
    return re.sub(r"(\b\w+\.)?Material\.(buttonColor|highlightedButtonColor|buttonDisabledColor)\b(?!\s*\()",
                  repl, text)


def strip_import_versions():
    n = 0
    for folder in (os.path.join(UI, "qml"), os.path.join(UI, "desktop", "qml_shims")):
        for root, _, files in os.walk(folder):
            in_style = os.path.basename(root) in ("poly_style", "controls")
            for name in files:
                if not name.endswith(".qml"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                new = _IMPORT.sub(lambda m: m.group(1) + (m.group(2) or ""), text)
                if not in_style:
                    new = _controls_last(new)
                new = _material_button_colors(new)
                # Qt 6 renamed RegExpValidator (and its regExp property)
                new = re.sub(r"\bRegExpValidator\b", "RegularExpressionValidator", new)
                new = re.sub(r"(?<![\w.])regExp:", "regularExpression:", new)
                if new != text:
                    write(path, new)
                    n += 1
    print("Qt 6: removed import versions in %d files" % n)


def main():
    controls_module()
    qt6_style_module()
    module_info_js()
    icons()
    if QT6:
        strip_import_versions()
    print("UI prepared in", UI)


if __name__ == "__main__":
    main()
