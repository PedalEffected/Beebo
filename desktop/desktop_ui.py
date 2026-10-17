"""Desktop-only screen helpers, shared by the menu bar and the QML screen.

    ui = desktop_ui.get()            # after the QGuiApplication exists
    context.setContextProperty("desktopUI", ui)

desktopUI.zoom      zoom factor on top of "fit to window" (1.0 = fit),
                    remembered between launches
desktopUI.cmdHeld() True while Command (Ctrl on Linux) is held, so a mouse
                    can do the pedal's hold-one-module, touch-another connect
"""
from PySide2.QtCore import Property, QObject, QSettings, Qt, Signal, Slot
from PySide2.QtGui import QGuiApplication

ZOOM_MIN = 0.5
ZOOM_MAX = 3.0
ZOOM_STEP = 0.1

_instance = None


class DesktopUI(QObject):
    zoomChanged = Signal()

    def __init__(self):
        super().__init__()
        self._settings = QSettings("PedalEffected", "Beebo")
        try:
            z = float(self._settings.value("zoom", 1.0))
        except (TypeError, ValueError):
            z = 1.0
        self._zoom = min(max(z, ZOOM_MIN), ZOOM_MAX)

    def _get_zoom(self):
        return self._zoom

    def _set_zoom(self, z):
        z = round(min(max(float(z), ZOOM_MIN), ZOOM_MAX), 2)
        if z != self._zoom:
            self._zoom = z
            self._settings.setValue("zoom", z)
            self.zoomChanged.emit()

    zoom = Property(float, _get_zoom, _set_zoom, notify=zoomChanged)

    @Property(float, constant=True)
    def zoomMin(self):
        return ZOOM_MIN

    @Property(float, constant=True)
    def zoomMax(self):
        return ZOOM_MAX

    @Slot()
    def zoomIn(self):
        self._set_zoom(self._zoom + ZOOM_STEP)

    @Slot()
    def zoomOut(self):
        self._set_zoom(self._zoom - ZOOM_STEP)

    @Slot()
    def zoomFit(self):
        self._set_zoom(1.0)

    @Slot(result=bool)
    def cmdHeld(self):
        # Qt reports the Mac's Command key as ControlModifier
        return bool(QGuiApplication.queryKeyboardModifiers() & Qt.ControlModifier)


def get():
    global _instance
    if _instance is None:
        _instance = DesktopUI()
    return _instance
