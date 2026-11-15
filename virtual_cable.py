"""Offline original VB-CABLE package and explicit, interactive Windows launch.

Nothing in this module installs a driver on import, verification or preparation.
Only start_install/launch_elevated may invoke the original vendor installer.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path,PurePosixPath
import hashlib
import io
import os
import re
import stat
import struct
import tempfile
import zipfile

PACKAGE_NAME='VBCABLE_Driver_Pack45.zip'
PACKAGE_SHA256='b950e39f01af1d04ea623c8f6d8eb9b6ea5c477c637295fabf20631c85116bfb'
PACKAGE_BYTES=1318877
OFFICIAL_URL='https://vb-audio.com/Cable/'
LICENSE_URL='https://vb-audio.com/Services/licensing.htm'
SUPPORT_URL='https://shop.vb-audio.com/en/win-apps/11-vb-cable.html'


@dataclass(frozen=True)
class CableStatus:
    playback:str=''
    capture:str=''
    present:bool=False

    @property
    def ready(self):return bool(self.playback and self.capture)


def detect_cable(playbacks,captures):
    def base_name(name):
        low=str(name).casefold()
        return bool(re.search(r'\bcable\s+(?:input|output|in\s+16ch|out\s+16ch)\b',low))
    playback=next((name for name in playbacks if re.search(r'\bcable\s+input\b',name,re.I)),'')
    capture=next((name for name in captures if re.search(r'\bcable\s+output\b',name,re.I)),'')
    return CableStatus(playback,capture,any(base_name(name) for name in [*playbacks,*captures]))


def _archive_path(name):
    name=name.replace('\\','/');path=PurePosixPath(name)
    if path.is_absolute() or ':' in name or any(ord(c)<32 for c in name) or any(part in ('','.', '..') or part.endswith((' ','.')) for part in name.split('/')):
        raise ValueError('安装包含有不安全路径。')
    return path


def _linked(path):
    return path.is_symlink() or getattr(path,'is_junction',lambda:False)()


@dataclass(frozen=True)
class PreparedInstallation:
    directory:Path
    executable:Path
    hashes:dict
    allowed_root:Path

    def verify(self):
        if _linked(self.directory) or not self.directory.resolve().is_relative_to(self.allowed_root):
            raise ValueError('安装缓存位置已变化，请重新准备安装包。')
        files=set()
        for path in self.directory.rglob('*'):
            if _linked(path) or not path.resolve().is_relative_to(self.directory.resolve()):raise ValueError('安装缓存含有链接，已停止启动。')
            if path.is_file():files.add(path.relative_to(self.directory).as_posix())
        if files!=set(self.hashes):raise ValueError('安装缓存文件缺失或发生变化，请重新准备。')
        for name,digest in self.hashes.items():
            if hashlib.sha256((self.directory/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('安装文件校验失败，已停止启动。')
        if not self.executable.is_file() or self.executable.parent!=self.directory:
            raise ValueError('官方安装器缺失。')
        return self


class CablePackage:
    def __init__(self,resources,data_dir):
        self.path=Path(resources)/'assets'/'vbcable'/PACKAGE_NAME
        self.data_dir=Path(data_dir)

    def read_verified(self):
        if not self.path.is_file() or self.path.stat().st_size!=PACKAGE_BYTES:raise ValueError('内置VB-CABLE包缺失或损坏，请重新下载完整应用。')
        data=self.path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=PACKAGE_SHA256:raise ValueError('内置VB-CABLE包校验失败，请重新下载完整应用。')
        return data

    def available(self):
        try:self.read_verified();return True
        except (OSError,ValueError):return False

    def prepare(self,is_64bit=None):
        data=self.read_verified();payload={}
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            items=archive.infolist()
            if len(items)!=31 or sum(item.file_size for item in items)>8*1024*1024:raise ValueError('官方安装包内容不完整。')
            seen=set()
            for item in items:
                name=_archive_path(item.filename).as_posix()
                if stat.S_ISLNK(item.external_attr>>16) or name.casefold() in seen:raise ValueError('安装包含有链接或重复路径。')
                seen.add(name.casefold());payload[name]=archive.read(item)
        is_64bit=struct.calcsize('P')==8 if is_64bit is None else is_64bit
        executable='VBCABLE_Setup_x64.exe' if is_64bit else 'VBCABLE_Setup.exe'
        if executable not in payload or 'readme.txt' not in payload:raise ValueError('官方安装器或说明文件缺失。')
        root=self.data_dir.resolve();cache=root/'installers';cache.mkdir(parents=True,exist_ok=True)
        if not cache.resolve().is_relative_to(root) or _linked(cache):raise ValueError('安装缓存目录不能位于应用数据目录以外。')
        directory=Path(tempfile.mkdtemp(prefix='VB-CABLE-Pack45-',dir=cache))
        for name,content in payload.items():
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as stream:stream.write(content)
        prepared=PreparedInstallation(directory,directory/executable,{name:hashlib.sha256(content).hexdigest() for name,content in payload.items()},root)
        return prepared.verify()


class InstallerCancelled(Exception):pass
class InstallerUntracked(OSError):pass


class WindowsInstallerProcess:
    """Observe an installer; closing this observer never terminates the process."""
    def __init__(self,handle,kernel):self.handle=handle;self.kernel=kernel

    def poll(self):
        import ctypes
        from ctypes import wintypes
        if not self.handle:return None
        code=wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle,ctypes.byref(code)):raise ctypes.WinError(ctypes.get_last_error())
        return None if code.value==259 else code.value

    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None


def launch_elevated(executable):
    if os.environ.get('QT_QPA_PLATFORM')=='offscreen':raise OSError('离屏自检不会启动驱动安装器。')
    if os.name!='nt':raise OSError('此安装器仅适用于Windows。')
    import ctypes
    from ctypes import wintypes as w
    class ShellExecuteInfo(ctypes.Structure):
        _fields_=[('cbSize',w.DWORD),('fMask',w.ULONG),('hwnd',w.HWND),('lpVerb',w.LPCWSTR),('lpFile',w.LPCWSTR),
                  ('lpParameters',w.LPCWSTR),('lpDirectory',w.LPCWSTR),('nShow',ctypes.c_int),('hInstApp',w.HINSTANCE),
                  ('lpIDList',w.LPVOID),('lpClass',w.LPCWSTR),('hkeyClass',w.HKEY),('dwHotKey',w.DWORD),
                  ('hIconOrMonitor',w.HANDLE),('hProcess',w.HANDLE)]
    shell=ctypes.WinDLL('shell32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    shell.ShellExecuteExW.argtypes=[ctypes.POINTER(ShellExecuteInfo)];shell.ShellExecuteExW.restype=w.BOOL
    kernel.GetExitCodeProcess.argtypes=[w.HANDLE,ctypes.POINTER(w.DWORD)];kernel.GetExitCodeProcess.restype=w.BOOL
    kernel.CloseHandle.argtypes=[w.HANDLE];kernel.CloseHandle.restype=w.BOOL
    info=ShellExecuteInfo();info.cbSize=ctypes.sizeof(info);info.fMask=0x40|0x100
    info.lpVerb='runas';info.lpFile=str(executable);info.lpDirectory=str(executable.parent);info.nShow=1
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        error=ctypes.get_last_error()
        if error==1223:raise InstallerCancelled('已取消Windows管理员授权，安装器未启动。')
        raise ctypes.WinError(error)
    if not info.hProcess:raise InstallerUntracked('已请求打开安装器，但无法跟踪进程；请检查官方安装器窗口并完成后重启。')
    return WindowsInstallerProcess(info.hProcess,kernel)


def start_install(prepared,launcher=None):
    prepared.verify()
    return (launcher or launch_elevated)(prepared.executable)
