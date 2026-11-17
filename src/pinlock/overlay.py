"""The login screen overlay (`pinlock overlay`).

pinlockd starts this as the greeter's own user, on the greeter's Wayland
display, and drives it over stdin:

    show <dots>   show the panel with that many digits typed
    hide          hide it

It hides itself after IDLE_MS without input, and exits when stdin closes.
"""
import os
import sys

IDLE_MS = 20000
PINPAD_PATHS = [
    "/usr/share/plasma/shells/io.github.v6bv.pinlock/contents/lockscreen/PinPad.qml",
    # Running from a git checkout.
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "data", "plasma-shell", "io.github.v6bv.pinlock", "contents", "lockscreen",
                 "PinPad.qml"),
]


def pinpad_path():
    for path in PINPAD_PATHS:
        if os.path.exists(path):
            return path
    sys.exit("pinlock overlay: PinPad.qml not found")


def main():
    os.environ.setdefault("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell")
    from PyQt6.QtCore import (QObject, QSocketNotifier, QTimer, QUrl, pyqtProperty,
                              pyqtSignal)
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtQml import QQmlApplicationEngine

    class Controller(QObject):
        changed = pyqtSignal()

        def __init__(self):
            super().__init__()
            self._shown = False
            self._dots = 0
            self.idle = QTimer(self, singleShot=True, interval=IDLE_MS,
                               timeout=lambda: self.update(False, self._dots))

        @pyqtProperty(bool, notify=changed)
        def shown(self):
            return self._shown

        @pyqtProperty(int, notify=changed)
        def dots(self):
            return self._dots

        def update(self, shown, dots):
            self._shown, self._dots = shown, dots
            self.changed.emit()
            if shown:
                self.idle.start()

    app = QGuiApplication(sys.argv)
    controller = Controller()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    engine.rootContext().setContextProperty("pinpadUrl", QUrl.fromLocalFile(pinpad_path()))
    engine.load(QUrl.fromLocalFile(os.path.join(os.path.dirname(__file__), "qml", "Overlay.qml")))
    if not engine.rootObjects():
        sys.exit("pinlock overlay: failed to load Overlay.qml")

    fd = sys.stdin.fileno()
    pending = b""

    def read_commands():
        # Raw reads: a buffered readline could leave commands stuck in Python's
        # buffer where the socket notifier never sees them.
        nonlocal pending
        chunk = os.read(fd, 4096)
        if not chunk:  # pinlockd closed the pipe
            app.quit()
            return
        *lines, pending = (pending + chunk).split(b"\n")
        for line in lines:
            cmd, _, arg = line.decode(errors="replace").strip().partition(" ")
            if cmd == "show":
                controller.update(True, int(arg) if arg.isdigit() else 0)
            elif cmd == "hide":
                controller.update(False, 0)

    notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read)
    notifier.activated.connect(read_commands)
    sys.exit(app.exec())
