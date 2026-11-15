"""Batch import UI. Audition stays local and never enters the microphone mixer."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDoubleSpinBox,
    QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from audio_import import AudioLibrary, ImportCancelled
from audio_import_qt import decode_audio
from ui_theme import STYLE, dark_palette, choose_audio_files

FILE_FILTER = '音频文件 (*.wav *.mp3 *.ogg *.flac *.m4a);;所有文件 (*)'


class ImportWorker(QThread):
    item_done = Signal(int, object, str)

    def __init__(self, root, jobs, normalize, parent=None):
        super().__init__(parent)
        self.root, self.jobs, self.normalize = root, jobs, normalize

    def run(self):
        try:
            library = AudioLibrary(self.root, decode_audio)
        except Exception as exc:
            for i in range(len(self.jobs)):
                self.item_done.emit(i, None, '失败：' + str(exc))
            return
        for i, (path, trim) in enumerate(self.jobs):
            if self.isInterruptionRequested():
                for remaining in range(i, len(self.jobs)):
                    self.item_done.emit(remaining, None, '已取消')
                break
            try:
                result = library.import_file(path, normalize=self.normalize, trim=trim,
                                             cancelled=self.isInterruptionRequested)
                text = '已导入' if result.status == 'imported' else '已存在，跳过'
                if result.warning:
                    text += ' · ' + result.warning
                self.item_done.emit(i, result, text)
            except ImportCancelled:
                self.item_done.emit(i, None, '已取消')
            except Exception as exc:
                self.item_done.emit(i, None, '失败：' + str(exc))


class SoundImportDialog(QDialog):
    library_changed = Signal(int)
    batch_finished = Signal()

    def __init__(self, root, paths=(), parent=None):
        super().__init__(parent)
        self.setPalette(dark_palette())
        self.setStyleSheet(STYLE)
        self.root = Path(root)
        self.paths = []
        self.trims = {}
        self._worker = None
        self._close_pending = False
        self._imported = 0
        self.setWindowTitle('导入音效')
        self.resize(780, 520)
        self.setMinimumSize(620, 420)
        self.setModal(True)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.output.setVolume(0.4)
        self.player.setAudioOutput(self.output)
        self.player.errorOccurred.connect(lambda _error, text: self.status.setText('试听失败：' + text))
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.add_button = QPushButton('添加音效…')
        self.add_button.clicked.connect(self.choose_files)
        self.preview_button = QPushButton('试听所选文件')
        self.preview_button.clicked.connect(self.preview_selected)
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.preview_button)
        toolbar.addStretch()
        self.normalize = QCheckBox('统一音量')
        self.normalize.setChecked(True)
        toolbar.addWidget(self.normalize)
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['文件', '时长', '结果'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self.show_trim)
        layout.addWidget(self.table, 1)
        trim_row = QHBoxLayout()
        trim_row.addWidget(QLabel('所选文件截取：开始'))
        self.trim_start = QDoubleSpinBox()
        self.trim_end = QDoubleSpinBox()
        for control in (self.trim_start, self.trim_end):
            control.setRange(0, 86400)
            control.setDecimals(2)
            control.setSuffix(' 秒')
            control.valueChanged.connect(self.save_trim)
        self.trim_end.setSpecialValueText('直到结尾')
        trim_row.addWidget(self.trim_start)
        trim_row.addWidget(QLabel('结束'))
        trim_row.addWidget(self.trim_end)
        layout.addLayout(trim_row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.start_button = QPushButton('开始导入')
        self.start_button.setToolTip('保留原文件；新音效不会自动绑定。')
        self.start_button.clicked.connect(self.start_import)
        self.close_button = QPushButton('关闭')
        self.close_button.clicked.connect(self.cancel_or_close)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.add_paths(paths)

    def is_importing(self):
        return self._worker is not None

    def add_paths(self, paths):
        for path in paths:
            path = Path(path).resolve()
            if path in self.paths:
                continue
            row = len(self.paths)
            self.paths.append(path)
            self.table.insertRow(row)
            for column, text in enumerate((path.name, '—', '待导入')):
                item = QTableWidgetItem(text)
                item.setToolTip(str(path) if column == 0 else text)
                self.table.setItem(row, column, item)
        if self.paths and self.table.currentRow() < 0:
            self.table.selectRow(0)
        self.start_button.setEnabled(bool(self.paths))

    def choose_files(self):
        paths = choose_audio_files(self, '选择要导入的音效', FILE_FILTER)
        self.add_paths(paths)

    def show_trim(self):
        row = self.table.currentRow()
        start, end = self.trims.get(row, (0, None))
        for control, value in ((self.trim_start, start), (self.trim_end, end or 0)):
            control.blockSignals(True)
            control.setValue(value)
            control.blockSignals(False)

    def save_trim(self):
        row = self.table.currentRow()
        if row >= 0:
            self.trims[row] = (self.trim_start.value(), self.trim_end.value() or None)

    def preview_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(self.paths[row])))
        self.player.play()
        self.status.setText('正在本地试听：' + self.paths[row].name)

    def start_import(self):
        if self.is_importing() or not self.paths:
            return
        self.player.stop()
        self._imported = 0
        self.progress.setRange(0, len(self.paths))
        self.progress.setValue(0)
        for row in range(len(self.paths)):
            self.table.item(row, 2).setText('等待处理')
        for widget in (self.add_button, self.preview_button, self.normalize, self.table,
                       self.trim_start, self.trim_end, self.start_button):
            widget.setEnabled(False)
        self.close_button.setText('取消导入')
        self.status.setText('正在后台检查并导入，请稍候…')
        jobs = [(path, self.trims.get(i)) for i, path in enumerate(self.paths)]
        self._worker = ImportWorker(self.root, jobs, self.normalize.isChecked(), self)
        self._worker.item_done.connect(self._item_done)
        self._worker.finished.connect(self._finished)
        self._worker.start()

    def _item_done(self, row, result, text):
        self.table.item(row, 2).setText(text)
        self.table.item(row, 2).setToolTip(text)
        if result is not None:
            self.table.item(row, 1).setText(f'{result.duration:.2f} 秒')
            if result.status == 'imported':
                self._imported += 1
        self.progress.setValue(row + 1)

    def _finished(self):
        worker, self._worker = self._worker, None
        worker.deleteLater()
        for widget in (self.add_button, self.preview_button, self.normalize, self.table,
                       self.trim_start, self.trim_end, self.start_button):
            widget.setEnabled(True)
        self.close_button.setText('关闭')
        self.status.setText(f'处理完成：新增 {self._imported} 个音效。重复、失败或取消的文件请查看各行结果。')
        if self._imported:
            self.library_changed.emit(self._imported)
        self.batch_finished.emit()
        if self._close_pending:
            self.player.stop()
            super().reject()

    def cancel_or_close(self):
        if self.is_importing():
            self._worker.requestInterruption()
            self.status.setText('正在取消，将保留此前已经成功导入的音效。')
        else:
            self.reject()

    def reject(self):
        self.player.stop()
        if self.is_importing():
            self._close_pending = True
            self.cancel_or_close()
        else:
            super().reject()

    def closeEvent(self, event):
        if self.is_importing():
            self._close_pending = True
            self.cancel_or_close()
            event.ignore()
        else:
            self.player.stop()
            super().closeEvent(event)
