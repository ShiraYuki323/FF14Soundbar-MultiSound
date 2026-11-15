"""Application binaries and user-owned audio/configuration have separate lifetimes."""
from __future__ import annotations

import os
import shutil
import hashlib
import json
import uuid
from pathlib import Path


def user_data_dir() -> Path:
    override = os.environ.get('FF14_SFX_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    return base / 'FF14Soundbar'


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(512 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name('.' + target.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_bytes(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name('.' + target.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _rewrite_references(value, mapping):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_rewrite_references(item, mapping) for item in value]
    if isinstance(value, dict):
        return {mapping.get(key, key): _rewrite_references(item, mapping) for key, item in value.items()}
    return value


def ensure_empty_sound_config(data_dir: Path) -> None:
    """An importer-created library is explicitly empty, rather than 'first run autofill'."""
    from sounds_config import SoundsConfig
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / 'sounds.json'
    if target.exists():
        return
    temporary = data_dir / ('.empty-config-' + uuid.uuid4().hex + '.json')
    try:
        config = SoundsConfig(temporary)
        config.load()
        config.save()
        # Remember only the untouched placeholder. Real user edits always win.
        _atomic_bytes(data_dir / '.empty-config.sha256', _hash(temporary).encode('ascii'))
        if not target.exists():
            os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_user_data(legacy_dir: Path, data_dir: Path, resource_dir: Path | None = None) -> Path:
    legacy_dir, data_dir = Path(legacy_dir), Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    sounds = data_dir / 'sounds'
    sounds.mkdir(exist_ok=True)
    marker = data_dir / '.initialized'
    source_sounds = legacy_dir / 'sounds'
    legacy_id = hashlib.sha256(str(legacy_dir.resolve()).casefold().encode()).hexdigest()[:16]
    migration = data_dir / '.migrations' / legacy_id
    mapping_path = migration / 'path-map.json'
    mapping = json.loads(mapping_path.read_text(encoding='utf-8')) if mapping_path.exists() else {}
    # Seeding an empty standalone directory must not mark a future legacy install migrated.
    if source_sounds.is_dir() and source_sounds.resolve() != sounds.resolve() and not (migration / 'sounds.done').exists():
        for source in source_sounds.rglob('*'):
            if not source.is_file():
                continue
            relative = source.relative_to(source_sounds)
            target = sounds / relative
            if target.exists() and _hash(source) != _hash(target):
                relative = Path('迁移音效_' + legacy_id) / relative
                target = sounds / relative
                mapping[source.relative_to(source_sounds).as_posix()] = relative.as_posix()
            if not target.exists():
                _atomic_copy(source, target)
        _atomic_bytes(mapping_path, json.dumps(mapping, ensure_ascii=False).encode('utf-8'))
        _atomic_bytes(migration / 'sounds.done', b'complete')
    for filename in ('config.json', 'sounds.json'):
        source, target = legacy_dir / filename, data_dir / filename
        done = migration / (filename + '.done')
        if not source.is_file() or source.resolve() == target.resolve() or done.exists():
            continue
        placeholder = data_dir / '.empty-config.sha256'
        may_replace = (filename == 'sounds.json' and target.is_file() and placeholder.exists()
                       and placeholder.read_text(encoding='ascii') == _hash(target))
        if not target.exists() or may_replace:
            if filename == 'sounds.json' and mapping:
                rewritten = _rewrite_references(json.loads(source.read_text(encoding='utf-8')), mapping)
                _atomic_bytes(target, json.dumps(rewritten, ensure_ascii=False, indent=2).encode('utf-8'))
            else:
                _atomic_copy(source, target)
            if may_replace:
                placeholder.unlink(missing_ok=True)
        else:
            # Preserve both configurations when this user has already edited the new one.
            _atomic_copy(source, migration / ('original-' + filename))
        _atomic_bytes(done, b'complete')
    if not marker.exists():
        seed = source_sounds if source_sounds.is_dir() else (Path(resource_dir) / 'sounds' if resource_dir is not None else None)
        if seed is not None and seed.is_dir() and seed.resolve() != sounds.resolve():
            for source in seed.rglob('*'):
                if source.is_file():
                    target = sounds / source.relative_to(seed)
                    if not target.exists():
                        _atomic_copy(source, target)
        _atomic_bytes(marker, b'User audio and settings are preserved across upgrades.\n')
    return data_dir
