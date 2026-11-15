"""Capture only wheel scrolling while the native selector is open.

The callback only accumulates integers. Never install real hooks offscreen;
tests supply a fake backend. Nothing moves/clicks the system pointer.
"""
import ctypes,os
from ctypes import wintypes
_LIVE_HOOKS=set()


class MouseHookData(ctypes.Structure):
    _fields_=[('point',wintypes.POINT),('mouseData',wintypes.DWORD),('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]


class WindowsWheelBackend:
    def __init__(self):
        self.user=ctypes.WinDLL('user32',use_last_error=True);self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.callback_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM)
        self.user.SetWindowsHookExW.argtypes=[ctypes.c_int,self.callback_type,wintypes.HINSTANCE,wintypes.DWORD];self.user.SetWindowsHookExW.restype=wintypes.HANDLE
        self.user.CallNextHookEx.argtypes=[wintypes.HANDLE,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM];self.user.CallNextHookEx.restype=ctypes.c_ssize_t
        self.user.UnhookWindowsHookEx.argtypes=[wintypes.HANDLE];self.user.UnhookWindowsHookEx.restype=wintypes.BOOL
        self.kernel.GetModuleHandleW.argtypes=[wintypes.LPCWSTR];self.kernel.GetModuleHandleW.restype=wintypes.HMODULE
    def install(self,callback):return self.user.SetWindowsHookExW(14,callback,self.kernel.GetModuleHandleW(None),0)
    def remove(self,handle):return bool(self.user.UnhookWindowsHookEx(handle))
    def next(self,handle,code,message,data):return self.user.CallNextHookEx(handle,code,message,data)


class WheelCapture:
    def __init__(self,backend=None):
        self.backend=backend;self.injected=backend is not None;self.handle=None;self.callback=None;self.active=False;self.delta=0

    def start(self):
        self.delta=0
        if not self.injected:
            from PySide6.QtWidgets import QApplication
            app=QApplication.instance()
            if os.environ.get('QT_QPA_PLATFORM')=='offscreen' or (app and app.platformName()=='offscreen'):return False
        try:
            if self.backend is None:self.backend=WindowsWheelBackend()
            if self.handle:self.active=True;return True
            self.callback=self.backend.callback_type(self._hook)
            self.handle=self.backend.install(self.callback);self.active=bool(self.handle)
            if self.handle:_LIVE_HOOKS.add(self)
        except (OSError,AttributeError):self.active=False
        return self.active

    def _hook(self,code,message,data):
        try:
            if code>=0 and self.active and message==0x20A:
                event=ctypes.cast(data,ctypes.POINTER(MouseHookData)).contents
                self.delta+=ctypes.c_short(event.mouseData>>16).value
                return 1
        except Exception:pass
        return self.backend.next(self.handle,code,message,data)

    def take(self):result=self.delta;self.delta=0;return result

    def stop(self):
        self.active=False;self.delta=0
        if self.handle and self.backend.remove(self.handle):self.handle=None;_LIVE_HOOKS.discard(self)
        # Keep callback alive even if Windows rejects unhook; inactive callbacks
        # forward everything and can be reused or removed at shutdown.
