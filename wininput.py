"""Unicode typing through the Windows input API (including Turkish letters)."""
import ctypes
from ctypes import wintypes


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('extra', ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('extra', ctypes.c_size_t)]


class PAYLOAD(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('payload',)
    _fields_ = [('type', wintypes.DWORD), ('payload', PAYLOAD)]


def type_unicode(text):
    raw = text.encode('utf-16-le')
    events = []
    for i in range(0, len(raw), 2):
        unit = int.from_bytes(raw[i:i+2], 'little')
        for flag in (4, 6):
            item = INPUT(type=1)
            item.ki = KEYBDINPUT(0, unit, flag, 0, 0)
            events.append(item)
    if events:
        array = (INPUT * len(events))(*events)
        result = ctypes.windll.user32.SendInput(len(array), array, ctypes.sizeof(INPUT))
        if result != len(array):
            raise OSError('Windows bu pencereye yazma izni vermedi.')
