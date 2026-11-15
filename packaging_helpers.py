"""Keep Windows system ICU forwarders out of frozen applications.

Qt 6.12 uses the Windows ICU API. A third-party ICU on PATH can have the
same DLL name but versioned exports, so PyInstaller must not bundle it.
"""
from pathlib import PureWindowsPath


def without_system_icu(binaries):
    def keep(entry):
        name = PureWindowsPath(entry[0]).name.lower()
        return not (name.startswith('icu') and name.endswith('.dll'))

    return [entry for entry in binaries if keep(entry)]
