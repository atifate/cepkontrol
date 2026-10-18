"""One instance per Windows user; a second launch shows the existing window."""
import ctypes
from ctypes import wintypes
import hashlib
import os

kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel.CreateMutexW.restype = wintypes.HANDLE
kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel.CreateEventW.restype = wintypes.HANDLE
kernel.SetEvent.argtypes = [wintypes.HANDLE]
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.CloseHandle.argtypes = [wintypes.HANDLE]

class Instance:
    def __init__(self, action='show', namespace=None):
        identity = namespace or hashlib.sha256(os.environ.get('USERPROFILE','').encode()).hexdigest()[:20]
        prefix = 'Local\\CepKontrol.'+identity
        self.mutex = kernel.CreateMutexW(None, False, prefix)
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        exists = ctypes.get_last_error() == 183
        self.show_event = kernel.CreateEventW(None, False, False, prefix+'.show')
        self.quit_event = kernel.CreateEventW(None, False, False, prefix+'.quit')
        if not self.show_event or not self.quit_event:
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        self.owner = not exists and action != 'quit'
        if exists and action in ('show','quit'):
            kernel.SetEvent(self.quit_event if action == 'quit' else self.show_event)

    def command(self):
        if kernel.WaitForSingleObject(self.quit_event,0) == 0:
            return 'quit'
        if kernel.WaitForSingleObject(self.show_event,0) == 0:
            return 'show'

    def close(self):
        for name in ('show_event','quit_event','mutex'):
            handle = getattr(self,name,None)
            if handle:
                kernel.CloseHandle(handle)
                setattr(self,name,None)
