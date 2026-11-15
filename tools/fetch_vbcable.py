"""Restore the pinned, unmodified official bundle for a build; never execute it."""
from pathlib import Path
import hashlib
import os
import sys
import tempfile
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from virtual_cable import PACKAGE_NAME,PACKAGE_SHA256,PACKAGE_BYTES


def main():
    target=Path(__file__).resolve().parents[1]/'assets'/'vbcable'/PACKAGE_NAME
    url='https://download.vb-audio.com/Download_CABLE/'+PACKAGE_NAME
    with urlopen(url,timeout=30) as response:data=response.read(PACKAGE_BYTES+1)
    if len(data)!=PACKAGE_BYTES or hashlib.sha256(data).hexdigest()!=PACKAGE_SHA256:
        raise ValueError('下载包与本版校验值不一致，原有文件保持不变。')
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='vbcable-',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as output:output.write(data);output.flush();os.fsync(output.fileno())
        os.replace(name,target)
    finally:Path(name).unlink(missing_ok=True)
    print(f'Official original ZIP verified: {PACKAGE_SHA256} ({len(data)} bytes). Not executed.')


if __name__=='__main__':main()
