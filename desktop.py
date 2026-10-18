"""Visible Windows tray and opt-out per-user logon startup."""
import queue
from pathlib import Path
import subprocess
import sys
import threading
import winreg

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'

def startup_command():
    if getattr(sys, 'frozen', False):
        executable = Path(sys.executable).resolve()
        canonical = executable.with_name('CepKontrol.exe')
        return subprocess.list2cmdline([str(canonical if canonical.exists() else executable), '--background'])
    return subprocess.list2cmdline([sys.executable, str(Path(__file__).with_name('app.py')), '--background'])

def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return bool(winreg.QueryValueEx(key, 'CepKontrol')[0])
    except FileNotFoundError:
        return False

def set_startup(enabled):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, 'CepKontrol', 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, 'CepKontrol')
            except FileNotFoundError:
                pass

class Tray:
    def __init__(self, image_path):
        import pystray
        from PIL import Image
        self.commands = queue.SimpleQueue()
        self.ready = threading.Event()
        self.icon = pystray.Icon('CepKontrol', Image.open(image_path).copy(),
            'CepKontrol · Kayıtlı telefondan erişim', pystray.Menu(
                pystray.MenuItem('CepKontrol’ü aç', lambda *_:self.commands.put('show'), default=True),
                pystray.MenuItem('Tamamen çık', lambda *_:self.commands.put('quit'))))
        def setup(icon):
            icon.visible = True
            self.ready.set()
        self.thread = threading.Thread(target=lambda:self.icon.run(setup=setup), daemon=True)
        self.thread.start()

    def stop(self):
        self.icon.stop()
