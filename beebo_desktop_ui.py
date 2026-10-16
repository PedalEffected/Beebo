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

sys.argv[0] = os.path.join(HERE, "show_widget.py")
runpy.run_path(sys.argv[0], run_name="__main__")
