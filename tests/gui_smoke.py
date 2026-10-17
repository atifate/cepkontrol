"""Exercise our Tk UI against the real Ubuntu relay, without injecting input."""
import os
import sys
import time
import tkinter as tk
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import App
from transport import Session
from wire import parse_code, make_code
import app as app_module


def spin(root, condition, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        root.update()
        if condition():
            return
        time.sleep(.02)
    raise AssertionError('GUI state timed out')


def find_button(widget, text):
    for child in widget.winfo_children():
        if isinstance(child, tk.Button) and child['text'] == text:
            return child
        found = find_button(child, text)
        if found:
            return found


root = tk.Tk()
temporary_config = tempfile.TemporaryDirectory()
app_module.CONFIG = Path(temporary_config.name) / 'settings.json'
app = App(root)
app.server.set(os.environ.get('RELAY_TEST_URL', 'ws://192.168.1.69:8765'))
app.share()
spin(root, lambda: bool(app.code.get()))
assert app.phone_popup is not None, 'Phone QR must be visible'
frames = []
viewer = Session(parse_code(app.code.get(), app.server.get()), 'viewer',
                 lambda k, p: frames.append(p.size) if k == 'frame' else None)
viewer.start()
spin(root, lambda: app.consent is not None)
assert not viewer.approved.is_set(), 'Consent must be required'
find_button(app.consent, 'Bağlantıya izin ver').invoke()
spin(root, lambda: bool(frames))
assert app.phone_popup is None, 'QR must close after accepting the phone'
assert frames[0][0] > 0 and frames[0][1] > 0
app.disconnect()
viewer.close()
assert app.code.get() == ''
root.update()
print('HOST GUI: consent + actual screen capture + disconnect OK', frames[0])

code, data = make_code(app.server.get())
host = Session(data, 'host', lambda k, p: None)
host.start()
spin(root, lambda: host.ws is not None)
app.remote_code.set(code)
app.connect()
spin(root, lambda: host.pending)
host.accept(True, control=False)
spin(root, lambda: app.viewer is not None and app.photo is not None)
assert app.view_bounds[2] > 0
app.fullscreen()
root.update()
app.fullscreen()
app.disconnect()
host.close()
root.destroy()
temporary_config.cleanup()
print('VIEWER GUI: decode + render + fullscreen + disconnect OK')
