"""Let the pedal's PySide2 / Qt 5 code run on Qt 6 and modern Python.

The pedal runs PySide2 (Qt 5.15). PySide2 has no builds for Apple Silicon
or current Python, so the desktop app uses PySide6 instead. Importing this
module first makes `import PySide2.QtCore` (and friends) load PySide6, and
`import liblo` load pyliblo3, without changing the pedal code.
"""
import importlib
import sys


def _alias(old, new):
    try:
        mod = importlib.import_module(new)
    except ImportError:
        return False
    sys.modules.setdefault(old, mod)
    return True


def install():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    # On any desktop: a stand-in for the pedal's on-screen keyboard
    # (computers have a real one), so the screens load without it.
    desktop_qml = os.path.join(here, "qml_desktop")
    for var in ("QML_IMPORT_PATH", "QML2_IMPORT_PATH"):
        os.environ[var] = os.pathsep.join(p for p in (desktop_qml, os.environ.get(var)) if p)
    try:
        import PySide2  # noqa: F401  (real PySide2 available: use it)
    except ImportError:
        if _alias("PySide2", "PySide6"):
            for sub in ("QtCore", "QtGui", "QtQml", "QtQuick", "QtWidgets",
                        "QtNetwork", "QtSvg"):
                _alias("PySide2." + sub, "PySide6." + sub)
            _patch_qt6()
    try:
        import liblo  # noqa: F401
    except ImportError:
        _alias("liblo", "pyliblo3")


def _patch_qt6():
    """Small API differences between PySide2 and PySide6."""
    import os
    shims = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml_shims")
    # Qt 6 stand-ins for the two Qt 5 QML modules the screens import
    # (QtGraphicalEffects, Qt.labs.handlers). Only on Qt 6: on Qt 5 they would
    # hide the real modules.
    os.environ["QML_IMPORT_PATH"] = os.pathsep.join(
        p for p in (shims, os.environ.get("QML_IMPORT_PATH")) if p)
    # The pedal picks its "poly_style" controls style in qtquickcontrols2.conf;
    # on Qt 6 that style is the module generated in qml_shims/poly_style.
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "poly_style")
    os.environ.setdefault("QT_QUICK_CONTROLS_FALLBACK_STYLE", "Material")
    from PySide6 import QtCore, QtGui, QtWidgets
    for cls in (QtGui.QGuiApplication, QtWidgets.QApplication, QtCore.QCoreApplication):
        if not hasattr(cls, "exec_"):
            cls.exec_ = cls.exec
