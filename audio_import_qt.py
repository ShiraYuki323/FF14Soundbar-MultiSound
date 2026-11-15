"""Use the same bundled Qt multimedia runtime as the player, off the UI thread."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

from audio_import import AudioData, ImportCancelled


def decode_audio(path: Path, cancelled=None) -> AudioData:
    cancelled = cancelled or (lambda: False)
    if cancelled():
        raise ImportCancelled('已取消')
    if QCoreApplication.instance() is None:
        raise ValueError('音频解码需要应用已启动。')
    fmt = QAudioFormat()
    fmt.setSampleRate(48000)
    fmt.setChannelCount(2)
    fmt.setSampleFormat(QAudioFormat.Float)
    decoder = QAudioDecoder()
    decoder.setAudioFormat(fmt)
    loop = QEventLoop()
    chunks, errors = [], []
    finished, was_cancelled = False, False
    total_bytes = 0

    def receive():
        nonlocal total_bytes
        buffer = decoder.read()
        if not buffer.isValid():
            return
        actual = buffer.format()
        if actual.sampleRate() != 48000 or actual.channelCount() != 2 or actual.sampleFormat() != QAudioFormat.Float:
            errors.append('当前解码器没有提供兼容的音频格式。')
            loop.quit()
            return
        data = np.frombuffer(bytes(buffer.constData()), dtype='<f4').copy().reshape(-1, 2)
        total_bytes += data.nbytes
        if total_bytes > 192 * 1024 * 1024:
            errors.append('音频过长，解码内存超过 192MB；请先截取较短片段。')
            loop.quit()
            return
        chunks.append(data)

    def complete():
        nonlocal finished
        finished = True
        loop.quit()

    def failed(*_):
        errors.append(decoder.errorString() or '无法解码该音频文件。')
        loop.quit()

    def check_cancel():
        nonlocal was_cancelled
        if cancelled():
            was_cancelled = True
            loop.quit()

    decoder.bufferReady.connect(receive)
    decoder.finished.connect(complete)
    decoder.error.connect(failed)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lambda: (errors.append('解码超时，请检查文件是否损坏。'), loop.quit()))
    cancellation = QTimer()
    cancellation.timeout.connect(check_cancel)
    timeout.start(20000)
    cancellation.start(50)
    try:
        decoder.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
        if not errors:
            # Some invalid streams fail synchronously in start(). Start only after
            # exec() is running, otherwise a synchronous quit() would be lost.
            QTimer.singleShot(0, decoder.start)
            loop.exec()
    finally:
        timeout.stop()
        cancellation.stop()
        decoder.stop()
        decoder.deleteLater()
    if was_cancelled or cancelled():
        raise ImportCancelled('已取消')
    if errors or not finished or not chunks:
        raise ValueError('; '.join(errors) or '文件没有可播放的音频。')
    return AudioData(np.concatenate(chunks), 48000)
