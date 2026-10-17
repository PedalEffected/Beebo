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
            # View menu: zoom (same as the slider above the screen)
            import desktop_ui
            ui = desktop_ui.get()
            self._view_menu = self._menubar.addMenu("View")
            self._zoom_actions = []
            for text, keys, fn in (("Zoom In", QtGui.QKeySequence.ZoomIn, ui.zoomIn),
                                   ("Zoom Out", QtGui.QKeySequence.ZoomOut, ui.zoomOut),
                                   ("Fit to Window", QtGui.QKeySequence("Ctrl+0"), ui.zoomFit)):
                a = self._view_menu.addAction(text)
                a.setShortcut(keys)
                a.triggered.connect(fn)
                self._zoom_actions.append(a)
            # quit if the launcher has gone (so a stuck screen can't linger
            # in the background and block the next start)
            launcher = int(os.environ.get("BEEBO_LAUNCHER_PID", "0") or 0)
            if launcher:
                # a thread, so it still works if the screen itself is stuck
                import threading
                import time

                def watch():
                    while True:
                        time.sleep(2)
                        try:
                            os.kill(launcher, 0)
                        except ProcessLookupError:
                            os._exit(0)
                        except OSError:
                            pass
                threading.Thread(target=watch, daemon=True).start()

            self._start_freeze_recorder()

        def _start_freeze_recorder(self):
            """If the screen stops responding for more than 3 seconds, write
            every thread's Python stack to logs/ui-freeze.log (again every 10
            seconds while it stays stuck), so a freeze can be diagnosed."""
            import faulthandler
            import threading
            import time
            from PySide2.QtCore import QTimer
            import beebo_paths
            log_dir = os.path.join(beebo_paths.DATA_DIR, "logs")
            beat = {"t": time.time()}
            self._heartbeat = QTimer()
            self._heartbeat.timeout.connect(lambda: beat.__setitem__("t", time.time()))
            self._heartbeat.start(500)

            def watch():
                last_dump = 0
                while True:
                    time.sleep(1)
                    now = time.time()
                    if now - beat["t"] > 3 and now - last_dump > 10:
                        last_dump = now
                        try:
                            os.makedirs(log_dir, exist_ok=True)
                            with open(os.path.join(log_dir, "ui-freeze.log"), "a") as f:
                                f.write("\n=== screen not responding for %.0f s (%s)\n"
                                        % (now - beat["t"], time.strftime("%H:%M:%S")))
                                f.flush()
                                faulthandler.dump_traceback(file=f, all_threads=True)
                        except Exception:
                            pass
            threading.Thread(target=watch, daemon=True).start()

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
