"""Seed newly bundled audio once, without overwriting users or undoing deletions."""
import json
from pathlib import Path
from app_paths import _atomic_bytes,_atomic_copy,_hash
from sound_deletion import SoundTrash

def sync_bundled_audio(source,data):
    source=Path(source);data=Path(data);root=data/'sounds';root.mkdir(parents=True,exist_ok=True)
    if not source.is_dir() or source.resolve()==root.resolve():return
    manifest=data/'.bundled-audio.json';seen=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    deleted=SoundTrash(root).deleted_names()
    for path in source.rglob('*'):
        if not path.is_file() or not path.resolve().is_relative_to(source.resolve()):continue
        relative=path.relative_to(source)
        if any(part.startswith('.') for part in relative.parts) or path.suffix.lower() not in ('.wav','.mp3','.ogg','.flac','.m4a'):continue
        name=relative.as_posix();digest=_hash(path);target=root/relative
        if not target.resolve().is_relative_to(root.resolve()):continue
        if name not in deleted and not target.exists() and seen.get(name)!=digest:_atomic_copy(path,target)
        seen[name]=digest
    _atomic_bytes(manifest,json.dumps(seen,ensure_ascii=False).encode('utf-8'))
