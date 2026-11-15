"""Transactional file ownership and audio preparation, independent of the GUI."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from contextlib import contextmanager

import numpy as np

SUPPORTED_EXTENSIONS = frozenset({'.wav', '.mp3', '.ogg', '.flac', '.m4a'})


class ImportCancelled(Exception):
    pass


@dataclass
class AudioData:
    samples: np.ndarray
    sample_rate: int


@dataclass
class ImportResult:
    status: str
    path: Path
    original_path: Path
    duration: float
    warning: str = ''


class AudioLibrary:
    def __init__(self, root: Path, decoder: Callable):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.staging = self.root / '.importing'
        self.originals = self.root / '.originals'
        self.staging.mkdir(exist_ok=True)
        self.originals.mkdir(exist_ok=True)
        self.index_path = self.root / '.library.json'
        self.decoder = decoder
        self._lock = threading.RLock()

    def _load_index(self) -> dict:
        if not self.index_path.exists():
            return {'version': 1, 'entries': []}
        try:
            index = json.loads(self.index_path.read_text(encoding='utf-8'))
            if index.get('version') != 1 or not isinstance(index.get('entries'), list):
                raise ValueError('invalid index')
            for item in index['entries']:
                for key in ('path', 'original'):
                    path = (self.root / item[key]).resolve()
                    if not path.is_relative_to(self.root):
                        raise ValueError('unsafe library path')
            return index
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError('音效库索引无法读取，已停止导入以保护原有文件。') from exc

    def _save_index(self, index: dict) -> None:
        temporary = self.staging / (uuid.uuid4().hex + '.json')
        try:
            with temporary.open('w', encoding='utf-8') as target:
                json.dump(index, target, ensure_ascii=False, indent=2)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.index_path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _check_cancel(cancelled: Callable[[], bool]) -> None:
        if cancelled():
            raise ImportCancelled('已取消')

    @staticmethod
    def _stem(name: str) -> str:
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:80]
        if not name:
            return '音效'
        if name.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
            name = '_' + name
        return name

    @contextmanager
    def _process_lock(self, cancelled):
        with (self.root / '.library.lock').open('a+b') as lock:
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b'\0')
                lock.flush()
            deadline = time.monotonic() + 30
            while True:
                self._check_cancel(cancelled)
                lock.seek(0)
                try:
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (11, 13, 36) or time.monotonic() >= deadline:
                        raise OSError('音效库正被其他窗口使用，请稍后重试。') from exc
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def import_file(self, source: Path, normalize: bool = True,
                    trim: tuple[float, float | None] | None = None,
                    cancelled: Callable[[], bool] | None = None) -> ImportResult:
        cancelled = cancelled or (lambda: False)
        with self._lock, self._process_lock(cancelled):
            return self._import_file(source, normalize, trim, cancelled)

    def _import_file(self, source: Path, normalize: bool = True,
                    trim: tuple[float, float | None] | None = None,
                    cancelled: Callable[[], bool] | None = None) -> ImportResult:
        source = Path(source)
        cancelled = cancelled or (lambda: False)
        self._check_cancel(cancelled)
        if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError('不支持的格式，请选择 WAV、MP3、OGG、FLAC 或 M4A。')
        if not source.is_file():
            raise ValueError('文件不存在或无法读取。')
        start, end = trim or (0.0, None)
        start = float(start)
        end = None if end is None or end == 0 else float(end)
        if not math.isfinite(start) or start < 0 or (end is not None and (not math.isfinite(end) or end <= start)):
            raise ValueError('截取范围无效：结束时间须大于开始时间。')
        snapshot = self.staging / (uuid.uuid4().hex + source.suffix.lower())
        rendered = self.staging / (uuid.uuid4().hex + '.wav')
        published: Path | None = None
        original_path: Path | None = None
        created_original = False
        committed = False
        try:
            digest = hashlib.sha256()
            with source.open('rb') as incoming, snapshot.open('xb') as target:
                while chunk := incoming.read(512 * 1024):
                    self._check_cancel(cancelled)
                    digest.update(chunk)
                    target.write(chunk)
            if snapshot.stat().st_size == 0:
                raise ValueError('音频文件为空。')
            source_hash = digest.hexdigest()
            options = {'normalize': bool(normalize), 'start': start, 'end': end}
            identity = hashlib.sha256((source_hash + json.dumps(options, sort_keys=True)).encode()).hexdigest()
            with self._lock:
                index = self._load_index()
                for entry in index['entries']:
                    if entry.get('id') == identity and (self.root / entry['path']).is_file() and (self.root / entry['original']).is_file():
                        return ImportResult('duplicate', self.root / entry['path'], self.root / entry['original'], float(entry['duration']), '相同音效及处理设置已存在。')
            self._check_cancel(cancelled)
            try:
                decoded = self.decoder(snapshot, cancelled=cancelled)
            except ImportCancelled:
                raise
            except Exception as exc:
                raise ValueError('音频无法解码或文件已损坏：' + str(exc)) from exc
            samples = np.asarray(decoded.samples, dtype=np.float32).copy()
            if samples.ndim == 1:
                samples = samples[:, None]
            if decoded.sample_rate != 48000 or samples.ndim != 2 or samples.shape[1] not in (1, 2) or samples.shape[0] == 0 or not np.all(np.isfinite(samples)):
                raise ValueError('音频没有可用数据或解码格式无效。')
            if samples.shape[1] == 1:
                samples = np.repeat(samples, 2, axis=1)
            begin = round(start * 48000)
            finish = len(samples) if end is None else min(len(samples), round(end * 48000))
            if begin >= finish:
                raise ValueError('截取范围超出了音频长度。')
            samples = samples[begin:finish]
            self._check_cancel(cancelled)
            if normalize:
                rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
                peak = float(np.max(np.abs(samples)))
                if rms > 1e-9 and peak > 1e-9:
                    samples *= min(10 ** (-20 / 20) / rms, 10 ** (-1 / 20) / peak)
            pcm = np.round(np.clip(samples, -1, 1) * 32767).astype('<i2')
            with wave.open(str(rendered), 'wb') as target:
                target.setnchannels(2)
                target.setsampwidth(2)
                target.setframerate(48000)
                target.writeframes(pcm.tobytes())
            duration = len(samples) / 48000
            with self._lock:
                self._check_cancel(cancelled)
                index = self._load_index()
                # Another queued import may have completed while this file was decoding.
                for entry in index['entries']:
                    if entry.get('id') == identity and (self.root / entry['path']).is_file():
                        return ImportResult('duplicate', self.root / entry['path'], self.root / entry['original'], float(entry['duration']), '相同音效及处理设置已存在。')
                original_path = self.originals / (source_hash + source.suffix.lower())
                if not original_path.exists():
                    created_original = True
                    shutil.copy2(snapshot, original_path)
                stem = self._stem(source.stem)
                number = 1
                while True:
                    candidate = self.root / (stem + ('' if number == 1 else f' ({number})') + '.wav')
                    try:
                        target = candidate.open('xb')
                        break
                    except FileExistsError:
                        number += 1
                published = candidate
                with target, rendered.open('rb') as incoming:
                    shutil.copyfileobj(incoming, target)
                self._check_cancel(cancelled)
                index['entries'].append({'id': identity, 'source_hash': source_hash, 'path': published.name,
                                         'original': original_path.relative_to(self.root).as_posix(),
                                         'duration': duration, 'options': options})
                self._save_index(index)
                committed = True
            warning = '音效较长，可通过截取起止时间缩短。' if duration > 6 else ''
            return ImportResult('imported', published, original_path, duration, warning)
        finally:
            snapshot.unlink(missing_ok=True)
            rendered.unlink(missing_ok=True)
            if not committed:
                if published is not None:
                    published.unlink(missing_ok=True)
                if created_original and original_path is not None:
                    original_path.unlink(missing_ok=True)
