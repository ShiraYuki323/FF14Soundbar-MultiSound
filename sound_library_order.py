"""Sort library files by name, arrival time, or their on-disk duration."""
from pathlib import Path
import wave

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QMediaPlayer

from skillbar_model import is_combo_reference


SORT_OPTIONS = (
    ('名称', 'name'),
    ('导入时间 · 最新', 'newest'),
    ('导入时间 · 最早', 'oldest'),
    ('时长 · 从短到长', 'duration_asc'),
    ('时长 · 从长到短', 'duration_desc'),
)


class SoundLibraryOrder(QObject):
    durations_changed = Signal()

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self._cache = {}
        self._queue = {}
        self._current = None
        self._player = None
        self._start_timer = QTimer(self)
        self._start_timer.setSingleShot(True)
        self._start_timer.timeout.connect(self._probe_next)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(lambda: self._finish(None))

    def sorted_items(self, items, mode):
        by_duration = mode in ('duration_asc', 'duration_desc')
        by_date = mode in ('oldest', 'newest')
        descending = mode in ('newest', 'duration_desc')
        rows = []
        for name, label in items:
            combination = is_combo_reference(name)
            value = None
            if not combination and (by_duration or by_date):
                path = self.root / name
                try:
                    stat = path.stat()
                except OSError:
                    pass
                else:
                    if by_duration:
                        value = self._duration(path, (stat.st_mtime_ns, stat.st_size))
                    else:
                        value = getattr(stat, 'st_birthtime', stat.st_mtime)
            order = -value if descending and value is not None else value
            key = (combination, order is None, order or 0, label.casefold(), name)
            rows.append((key, (name, label, value if by_duration else None)))
        return [item for _, item in sorted(rows, key=lambda row: row[0])]

    def _duration(self, path, stamp):
        cached = self._cache.get(path)
        if cached and cached[0] == stamp:
            return cached[1]
        if path.suffix.lower() == '.wav':
            try:
                with wave.open(str(path), 'rb') as stream:
                    duration = stream.getnframes() / stream.getframerate()
                self._cache[path] = (stamp, duration)
                return duration
            except (wave.Error, EOFError, OSError):
                pass
        if self._current != (path, stamp):
            self._queue[path] = stamp
        if self._current is None and not self._start_timer.isActive():
            self._start_timer.start(0)
        return None

    def _probe_next(self):
        if self._current is not None:
            return
        if not self._queue:
            if self._player is not None:
                self._player.setSource(QUrl())
            return
        if self._player is None:
            self._player = QMediaPlayer(self)
            self._player.durationChanged.connect(self._duration_received)
            self._player.errorOccurred.connect(lambda *_: self._finish(None))
        path = next(iter(self._queue))
        self._current = (path, self._queue.pop(path))
        self._timeout.start(2500)
        self._player.setSource(QUrl.fromLocalFile(str(path)))

    def _duration_received(self, milliseconds):
        if milliseconds > 0:
            self._finish(milliseconds / 1000)

    def _finish(self, duration):
        if self._current is None:
            return
        path, stamp = self._current
        self._current = None
        self._timeout.stop()
        self._cache[path] = (stamp, duration)
        # Reset the media source after Qt returns from its duration/error signal.
        self._start_timer.start(0)
        if duration is not None:
            self.durations_changed.emit()
