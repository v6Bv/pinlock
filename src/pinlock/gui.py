"""pinlock-setup: a controller-friendly app to set up pinlock.

Everything can be done from the couch with a controller (D-pad + A/B in menus,
buttons-as-digits on the PIN screen), or with keyboard and mouse. Changes that
need root go through `pkexec pinlock ...`, which shows the desktop's normal
admin password prompt.
"""
import os
import sys

from PyQt6.QtCore import QEvent, QObject, QProcess, QSocketNotifier, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QMainWindow, QStackedWidget,
                             QVBoxLayout, QWidget)
from evdev import ecodes as e

from . import __author__, __url__, __version__, config, keymap, lockscreen, pam, pinstore

HOLD_MS = 800
FLASH_MS = 180
ACCENT = "#66c0f4"
FACE_COLORS = {"A": "#6cc04a", "B": "#e3443c", "X": "#3b8eea", "Y": "#f2c037"}

STYLE = f"""
* {{ color: #e6edf3; font-size: 18px; }}
QMainWindow, #root {{ background: #171a21; }}
#title {{ font-size: 40px; font-weight: 700; }}
#subtitle {{ color: #8b949e; }}
#heading {{ font-size: 30px; font-weight: 600; }}
#card {{ background: #1f2430; border-radius: 14px; }}
#message {{ font-size: 20px; min-height: 30px; }}
#message[tone="error"] {{ color: #ff7b72; }}
#message[tone="ok"] {{ color: #7ee787; }}
#dots {{ font-size: 46px; letter-spacing: 10px; color: {ACCENT}; }}
#footer {{ color: #8b949e; font-size: 17px; }}
#credit {{ color: #5c6773; font-size: 14px; }}
QListWidget {{ background: transparent; border: none; outline: none; font-size: 24px; }}
QListWidget::item {{ padding: 16px 20px; border-radius: 10px; margin: 3px 0; }}
QListWidget::item:selected {{ background: #2a475e; color: white; }}
QListWidget::item:hover:!selected {{ background: #222a36; }}
#tile {{ background: #1f2430; border-radius: 14px; border: 2px solid #1f2430; }}
#tile[lit="true"] {{ background: #2a475e; border-color: {ACCENT}; }}
#tileButton {{ font-size: 22px; font-weight: 700; }}
#tileDigit {{ font-size: 40px; font-weight: 700; }}
"""


def pinlock_cmd():
    """The pinlock CLI next to this launcher (installed or git checkout)."""
    return os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "pinlock")


def label(text="", name=None, cls=None, align=None):
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    if cls:
        w.setProperty("class", cls)
    if align is not None:
        w.setAlignment(align)
    w.setWordWrap(True)
    return w


def restyle(w):
    w.style().unpolish(w)
    w.style().polish(w)


class Gamepads(QObject):
    """Reads every connected controller and emits button names.

    Hotplug is handled by rescanning; Sunshine/Steam virtual pads come and go.
    """
    pressed = pyqtSignal(str)
    released = pyqtSignal(str)
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.devices = {}  # fd -> (InputDevice, QSocketNotifier)
        self.timer = QTimer(self, interval=2000, timeout=self.scan)
        self.timer.start()
        self.scan()

    def names(self):
        return [dev.name for dev, _ in self.devices.values()]

    def scan(self):
        found = keymap.open_gamepads({dev.path for dev, _ in self.devices.values()})
        for dev in found:
            n = QSocketNotifier(dev.fd, QSocketNotifier.Type.Read, self)
            n.activated.connect(lambda *_, fd=dev.fd: self.read(fd))
            self.devices[dev.fd] = (dev, n)
        if found:
            self.changed.emit()

    def read(self, fd):
        dev, notifier = self.devices[fd]
        try:
            events = list(dev.read())
        except OSError:  # unplugged
            notifier.setEnabled(False)
            notifier.deleteLater()
            del self.devices[fd]
            self.changed.emit()
            return
        for ev in events:
            btn = keymap.button_pressed(ev)
            if btn:
                self.pressed.emit(btn)
            elif ev.type == e.EV_KEY and ev.value == 0 and ev.code in keymap.KEY_BUTTONS:
                self.released.emit(keymap.KEY_BUTTONS[ev.code])
            elif ev.type == e.EV_ABS and ev.value == 0 and ev.code in (e.ABS_HAT0X, e.ABS_HAT0Y):
                for (axis, _), name in keymap.HAT_BUTTONS.items():
                    if axis == ev.code:
                        self.released.emit(name)


class Tile(QFrame):
    """One button in the legend: its name over the digit it types."""

    def __init__(self, button, glyph, digit):
        super().__init__(objectName="tile")
        self.button = button
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 10, 12)
        top = label(glyph, "tileButton", align=Qt.AlignmentFlag.AlignCenter)
        if button in FACE_COLORS:
            top.setStyleSheet(f"color: {FACE_COLORS[button]};")
        lay.addWidget(top)
        lay.addWidget(label(digit, "tileDigit", align=Qt.AlignmentFlag.AlignCenter))
        self.timer = QTimer(self, singleShot=True, interval=FLASH_MS,
                            timeout=lambda: self.light(False))

    def light(self, on=True):
        self.setProperty("lit", "true" if on else "false")
        restyle(self)

    def flash(self):
        self.light()
        self.timer.start()


class Legend(QWidget):
    def __init__(self, extra=()):
        super().__init__()
        grid = QGridLayout(self)
        grid.setSpacing(12)
        self.tiles = {}
        items = [(b, g, keymap.DIGITS[b]) for b, g in keymap.LEGEND] + list(extra)
        for i, (btn, glyph, digit) in enumerate(items):
            t = Tile(btn, glyph, digit)
            self.tiles[btn] = t
            grid.addWidget(t, i // 5, i % 5)

    def flash(self, btn):
        if btn in self.tiles:
            self.tiles[btn].flash()


class Page(QWidget):
    """A screen in the app. Subclasses handle buttons and keys."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(60, 40, 60, 30)
        self.lay.setSpacing(18)

    def footer(self, text):
        f = label(text, "footer", align=Qt.AlignmentFlag.AlignCenter)
        self.lay.addStretch(1)
        self.lay.addWidget(f)
        return f

    def shown(self):
        pass

    def button(self, btn):
        pass

    def hold(self, btn):
        pass

    def key(self, event):
        return False


class HomePage(Page):
    def __init__(self, app):
        super().__init__(app)
        head = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QIcon.fromTheme("pinlock", app.windowIcon()).pixmap(64, 64))
        head.addWidget(icon)
        titles = QVBoxLayout()
        titles.addWidget(label("pinlock", "title"))
        titles.addWidget(label("Log in and unlock with your controller", "subtitle"))
        head.addLayout(titles, 1)
        self.lay.addLayout(head)

        card = QFrame(objectName="card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 18, 24, 18)
        self.status = label()
        self.status.setTextFormat(Qt.TextFormat.RichText)
        cl.addWidget(self.status)
        self.lay.addWidget(card)

        self.menu = QListWidget()
        self.menu.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.menu.itemActivated.connect(self.activate)
        self.menu.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lay.addWidget(self.menu)
        self.message = label("", "message", align=Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(self.message)
        self.footer("Ⓐ Select    Ⓑ Quit    ↑ ↓ Move    ← → Change")
        site = __url__.removeprefix("https://")
        credit = label(f"pinlock {__version__}  ·  made by {__author__}  ·  "
                       f"<a href='{__url__}' style='color:#5c6773'>{site}</a>",
                       "credit", align=Qt.AlignmentFlag.AlignCenter)
        credit.setOpenExternalLinks(True)
        self.lay.addWidget(credit)

        self.refresh_timer = QTimer(self, interval=3000, timeout=self.refresh_status)

    def shown(self):
        self.refresh()
        self.refresh_timer.start()
        self.menu.setFocus()

    def hideEvent(self, ev):
        self.refresh_timer.stop()
        super().hideEvent(ev)

    def say(self, text, tone="ok"):
        self.message.setText(text)
        self.message.setProperty("tone", tone)
        restyle(self.message)

    def refresh_status(self):
        ok, bad = "#7ee787", "#ff7b72"

        def row(name, good, text):
            dot = f"<span style='color:{ok if good else bad}'>●</span>"
            return f"<tr><td>{dot}&nbsp;{name}</td><td style='padding-left:24px'>{text}</td></tr>"

        running = self.app.service_active()
        screens = [pam.SERVICES[s] for s, st in pam.status().items() if st == "enabled"]
        pads = self.app.pads.names()
        user = self.app.user
        panel = lockscreen.status()
        self.status.setText("<table>" + "".join([
            row("Background service", running, "running" if running else
                "not running (run install.sh, or sudo systemctl enable --now pinlockd)"),
            row("Login screens", bool(screens), ", ".join(screens) or
                "not hooked up (sudo pinlock pam enable)"),
            row(f"PIN for {user}", pinstore.has_pin(user),
                "set" if pinstore.has_pin(user) else "not set yet"),
            row("Lock screen panel", panel == "on", panel if panel != "off" else
                "off (turn it on below)"),
            row("Controller", bool(pads), ", ".join(dict.fromkeys(pads)) or
                "none found. Connect one."),
        ]) + "</table>")

    def refresh(self):
        self.refresh_status()
        has = pinstore.has_pin(self.app.user)
        row = max(self.menu.currentRow(), 0)
        self.menu.clear()
        settings = config.load()
        entries = [("set", "Change PIN" if has else "Set up a PIN"),
                   ("test", "Test controller"),
                   ("action", f"After unlocking:  {config.ACTIONS[settings['action']]}  ◂ ▸"),
                   ("panel", "Lock screen panel:  " +
                    ("On" if lockscreen.enabled() else "Off") + "  ◂ ▸")]
        if has:
            entries.append(("remove", "Remove PIN"))
        entries.append(("quit", "Quit"))
        for key, text in entries:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.menu.addItem(item)
        self.menu.setCurrentRow(min(row, self.menu.count() - 1))
        # Show every entry; the menu never scrolls.
        self.menu.setFixedHeight(sum(self.menu.visualItemRect(self.menu.item(i)).height() + 6
                                     for i in range(self.menu.count())) + 8)

    def current(self):
        item = self.menu.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def activate(self, *_):
        key = self.current()
        if key == "set":
            self.app.show_page(self.app.pin_page)
        elif key == "test":
            self.app.show_page(self.app.test_page)
        elif key == "action":
            self.cycle_action(1)
        elif key == "panel":
            self.toggle_panel()
        elif key == "remove":
            self.app.show_page(self.app.remove_page)
        elif key == "quit":
            self.app.close()

    def cycle_action(self, step):
        settings = config.load()
        choices = ["steam", "none"] + (["command"] if settings["command"].strip() else [])
        i = choices.index(settings["action"]) if settings["action"] in choices else 0
        settings["action"] = choices[(i + step) % len(choices)]
        config.save(settings)
        self.refresh()
        self.say(f"After unlocking with the controller: {config.ACTIONS[settings['action']]}")

    def toggle_panel(self):
        try:
            if lockscreen.enabled():
                lockscreen.disable()
                self.say("Lock screen panel off from your next login.")
            else:
                lockscreen.enable()
                self.say("Lock screen panel on. It shows up after you log out and back in.")
        except (RuntimeError, OSError) as exc:
            self.say(f"Couldn't change it: {exc}", tone="error")
        self.refresh()

    def button(self, btn):
        n = self.menu.count()
        if btn == "UP":
            self.menu.setCurrentRow((self.menu.currentRow() - 1) % n)
        elif btn == "DOWN":
            self.menu.setCurrentRow((self.menu.currentRow() + 1) % n)
        elif btn in ("LEFT", "RIGHT") and self.current() == "action":
            self.cycle_action(1 if btn == "RIGHT" else -1)
        elif btn in ("LEFT", "RIGHT") and self.current() == "panel":
            self.toggle_panel()
        elif btn in ("A", "START"):
            self.activate()
        elif btn == "B":
            self.app.close()

    def key(self, ev):
        if ev.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.current() == "action":
            self.cycle_action(1 if ev.key() == Qt.Key.Key_Right else -1)
            return True
        if ev.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.current() == "panel":
            self.toggle_panel()
            return True
        if ev.key() == Qt.Key.Key_Escape:
            self.app.close()
            return True
        return False


class PinPage(Page):
    def __init__(self, app):
        super().__init__(app)
        self.heading = label("", "heading", align=Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(self.heading)
        self.sub = label("", "subtitle", align=Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(self.sub)
        self.dots = label("", "dots", align=Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(self.dots)
        self.message = label("", "message", align=Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(self.message)
        self.legend = Legend()
        self.lay.addWidget(self.legend)
        self.footer("Start  Next    View  Delete    Hold View  Back")
        self.proc = None

    def shown(self):
        self.first = None
        self.entry = ""
        self.busy = False
        self.step_new()
        self.setFocus()

    def step_new(self, msg="", tone="error"):
        self.first = None
        self.entry = ""
        self.heading.setText("Choose a PIN")
        self.sub.setText(f"Press {pinstore.MIN_LEN}–{pinstore.MAX_LEN} buttons. "
                         "Each one is a digit, shown below.")
        self.update_view(msg, tone)

    def update_view(self, msg="", tone="error"):
        slots = max(pinstore.MIN_LEN, len(self.entry) + (len(self.entry) < pinstore.MAX_LEN))
        self.dots.setText("●" * len(self.entry) + "○" * (slots - len(self.entry)))
        self.message.setText(msg)
        self.message.setProperty("tone", tone)
        restyle(self.message)

    def add(self, digit):
        if self.busy:
            return
        if len(self.entry) < pinstore.MAX_LEN:
            self.entry += digit
            self.update_view()

    def delete(self):
        if self.busy:
            return
        if self.entry:
            self.entry = self.entry[:-1]
            self.update_view()
        else:
            self.back()

    def back(self):
        if not self.busy:
            self.app.show_page(self.app.home)

    def submit(self):
        if self.busy:
            return
        if self.first is None:
            if not pinstore.valid_pin(self.entry):
                self.update_view(f"Use at least {pinstore.MIN_LEN} buttons.")
                return
            self.first, self.entry = self.entry, ""
            self.heading.setText("Enter it again")
            self.sub.setText("Same buttons, same order.")
            self.update_view()
        elif self.entry != self.first:
            self.step_new("Those didn't match. Let's start over.")
        else:
            self.save(self.entry)

    def save(self, pin):
        self.busy = True
        self.heading.setText("Saving…")
        self.sub.setText("Your computer will ask for your password to confirm.")
        self.update_view()
        self.proc = QProcess(self)
        self.proc.finished.connect(self.saved)
        self.proc.start("pkexec", [pinlock_cmd(), "set", "--stdin"])
        self.proc.write((pin + "\n").encode())
        self.proc.closeWriteChannel()

    def saved(self, code, _status):
        self.busy = False
        err = bytes(self.proc.readAllStandardError()).decode(errors="replace").strip()
        if code == 0:
            self.app.show_page(self.app.home)
            self.app.home.say("PIN saved. Try it on the lock screen (Super+L).")
        elif code in (126, 127):  # pkexec: dialog dismissed / not authorized
            self.step_new("Not saved: the password prompt was cancelled.")
        else:
            self.step_new(f"Not saved: {err or f'error {code}'}")

    def button(self, btn):
        if btn in keymap.DIGITS:
            self.legend.flash(btn)
            self.add(keymap.DIGITS[btn])
        elif btn == "START":
            self.submit()
        elif btn == "VIEW":
            self.delete()

    def hold(self, btn):
        if btn == "VIEW":
            self.back()

    def key(self, ev):
        text = ev.text()
        if text.isdigit() and text.isascii():
            for btn, d in keymap.DIGITS.items():
                if d == text:
                    self.legend.flash(btn)
            self.add(text)
        elif ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.submit()
        elif ev.key() == Qt.Key.Key_Backspace:
            self.delete()
        elif ev.key() == Qt.Key.Key_Escape:
            self.back()
        else:
            return False
        return True


class TestPage(Page):
    def __init__(self, app):
        super().__init__(app)
        self.lay.addWidget(label("Test controller", "heading", align=Qt.AlignmentFlag.AlignCenter))
        self.sub = label("", "subtitle", align=Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(self.sub)
        self.last = label("Press any button", "dots", align=Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(self.last)
        self.legend = Legend(extra=[("START", "Start", "⏎"), ("VIEW", "View", "⌫")])
        self.lay.addWidget(self.legend)
        self.footer("Hold View  Back    (keyboard: Esc)")

    def shown(self):
        pads = self.app.pads.names()
        self.sub.setText(", ".join(dict.fromkeys(pads)) if pads else
                         "No controller found. Connect one and it will show up here.")
        self.last.setText("Press any button")
        self.setFocus()

    def button(self, btn):
        self.legend.flash(btn)
        meaning = dict(keymap.DIGITS, START="Enter", VIEW="Backspace").get(btn, "not used")
        self.last.setText(f"{btn}  →  {meaning}")

    def hold(self, btn):
        if btn == "VIEW":
            self.app.show_page(self.app.home)

    def key(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.app.show_page(self.app.home)
            return True
        return False


class RemovePage(Page):
    def __init__(self, app):
        super().__init__(app)
        self.lay.addStretch(1)
        self.lay.addWidget(label("Remove your PIN?", "heading", align=Qt.AlignmentFlag.AlignCenter))
        self.lay.addWidget(label("You'll need your password to log in and unlock again.",
                                 "subtitle", align=Qt.AlignmentFlag.AlignCenter))
        self.message = label("", "message", align=Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(self.message)
        self.footer("Ⓐ Remove    Ⓑ Keep it")
        self.proc = None

    def shown(self):
        self.message.setText("")
        self.setFocus()

    def remove(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            return
        self.message.setText("Your computer will ask for your password to confirm.")
        self.message.setProperty("tone", "")
        restyle(self.message)
        self.proc = QProcess(self)
        self.proc.finished.connect(self.removed)
        self.proc.start("pkexec", [pinlock_cmd(), "remove"])

    def removed(self, code, _status):
        if code == 0:
            self.app.show_page(self.app.home)
            self.app.home.say("PIN removed. Your password works as before.")
        else:
            self.message.setText("Not removed." if code in (126, 127) else
                                 f"Not removed: error {code}")
            self.message.setProperty("tone", "error")
            restyle(self.message)

    def button(self, btn):
        if btn == "A":
            self.remove()
        elif btn == "B":
            self.app.show_page(self.app.home)

    def key(self, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.remove()
        elif ev.key() == Qt.Key.Key_Escape:
            self.app.show_page(self.app.home)
        else:
            return False
        return True


class SetupWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pinlock")
        self.setWindowIcon(QIcon.fromTheme("pinlock", QIcon.fromTheme("input-gaming")))
        self.resize(1100, 820)
        self.user = os.environ.get("USER") or os.getlogin()
        self.pads = Gamepads()
        self.pads.pressed.connect(self.on_press)
        self.pads.released.connect(self.on_release)
        self.holding = None
        self.hold_timer = QTimer(self, singleShot=True, interval=HOLD_MS, timeout=self.on_hold)

        self.stack = QStackedWidget(objectName="root")
        self.setCentralWidget(self.stack)
        self.home = HomePage(self)
        self.pin_page = PinPage(self)
        self.test_page = TestPage(self)
        self.remove_page = RemovePage(self)
        for p in (self.home, self.pin_page, self.test_page, self.remove_page):
            self.stack.addWidget(p)
        self.pads.changed.connect(self.on_pads_changed)
        self.show_page(self.home)

    def service_active(self):
        return QProcess.execute("systemctl", ["is-active", "--quiet", "pinlockd.service"]) == 0

    def show_page(self, page):
        self.stack.setCurrentWidget(page)
        page.shown()

    def page(self):
        return self.stack.currentWidget()

    def on_pads_changed(self):
        if self.page() is self.test_page:
            self.test_page.shown()
        elif self.page() is self.home:
            self.home.refresh_status()

    # Controller input is global, so only act on it while we're the active window.
    def on_press(self, btn):
        if not self.isActiveWindow():
            return
        self.holding = btn
        self.hold_timer.start()
        self.page().button(btn)

    def on_release(self, btn):
        if btn == self.holding:
            self.hold_timer.stop()
            self.holding = None

    def on_hold(self):
        if self.holding and self.isActiveWindow():
            self.page().hold(self.holding)
        self.holding = None

    def eventFilter(self, obj, ev):
        # Pages see keys before any child widget (e.g. the menu list) does.
        if ev.type() == QEvent.Type.KeyPress and self.isActiveWindow():
            if ev.key() == Qt.Key.Key_F11:
                if self.isFullScreen():
                    self.showNormal()
                else:
                    self.showFullScreen()
                return True
            return self.page().key(ev)
        return False


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("pinlock")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("pinlock-setup")
    app.setStyleSheet(STYLE)
    win = SetupWindow()
    app.installEventFilter(win)
    if "--fullscreen" in sys.argv:
        win.showFullScreen()
    else:
        win.show()
    sys.exit(app.exec())
