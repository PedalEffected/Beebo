"""Start the Beebo screen on a desktop computer (Qt 6 / PySide6 or Qt 5)."""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "desktop"))
os.environ.setdefault("BEEBO_DESKTOP", "1")
# Qt 5 finds the poly_style controls style through this path; Qt 6 through
# the qml import path set below.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE_PATH", HERE)

import qt_compat  # noqa: E402
qt_compat.install()


def _install_audio_menu():
    """Run the screen as a QApplication (not a plain QGuiApplication) so it can
    have a menu bar, and add Audio > Change Audio Device. Choosing it leaves a
    request file for the launcher and closes the screen; the launcher stops
    the engine, shows the audio setup window and starts everything again."""
    request = os.environ.get("BEEBO_AUDIO_SETUP_REQUEST")
    if not request:
        return
    from PySide2 import QtGui, QtWidgets

    class BeeboApp(QtWidgets.QApplication):
        def __init__(self, *args):
            super().__init__(*args)
            self._menubar = QtWidgets.QMenuBar(None)   # the macOS menu bar
            # keep Python references, or PySide deletes the menu right away
            self._audio_menu = self._menubar.addMenu("Audio")
            self._audio_action = self._audio_menu.addAction("Change Audio Device…")
            self._audio_action.setShortcut(QtGui.QKeySequence("Ctrl+,"))
            self._audio_action.triggered.connect(self._audio_setup)

        def _audio_setup(self):
            try:
                os.makedirs(os.path.dirname(request), exist_ok=True)
                with open(request, "w") as f:
                    f.write("1\n")
            except OSError:
                return
            self.quit()

    QtGui.QGuiApplication = BeeboApp


_install_audio_menu()

sys.argv[0] = os.path.join(HERE, "show_widget.py")
runpy.run_path(sys.argv[0], run_name="__main__")
