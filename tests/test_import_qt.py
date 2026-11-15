import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from test_audio_import import write_wave
from qt_cleanup import close_test_windows

try:
    from audio_import_qt import decode_audio
    from sound_import_ui import SoundImportDialog
except ModuleNotFoundError as exc:
    if exc.name not in ('audio_import_qt', 'sound_import_ui'):
        raise
    decode_audio = SoundImportDialog = None


class QtImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        close_test_windows(self.app)

    def test_real_qt_decoder_accepts_wav_and_rejects_corrupt_input(self):
        self.assertIsNotNone(decode_audio, 'Qt 导入解码尚未实现')
        with tempfile.TemporaryDirectory() as directory:
            good = write_wave(Path(directory) / '中文音效.wav')
            decoded = decode_audio(good)
            self.assertEqual(decoded.sample_rate, 48000)
            self.assertEqual(decoded.samples.shape, (4800, 2))
            bad = Path(directory) / '损坏.mp3'
            bad.write_bytes(b'not an audio stream')
            with self.assertRaises(ValueError):
                decode_audio(bad)

    def test_batch_continues_after_invalid_audio_and_refreshes_only_when_imported(self):
        self.assertIsNotNone(SoundImportDialog, '桌面导入窗口尚未实现')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = write_wave(root / '下载' / 'valid.wav')
            bad = root / 'bad.wav'
            bad.write_bytes(b'broken')
            library = root / 'library'
            dialog = SoundImportDialog(library, [bad, good])
            dialog.normalize.setChecked(False)
            notifications = []
            dialog.library_changed.connect(notifications.append)
            loop = QEventLoop()
            dialog.batch_finished.connect(loop.quit)
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(10000)
            dialog.start_import()
            loop.exec()
            self.assertFalse(dialog.is_importing())
            self.assertEqual(notifications, [1])
            self.assertEqual(len(list(library.glob('*.wav'))), 1)
            self.assertIn('失败', dialog.table.item(0, 2).text())
            self.assertIn('已导入', dialog.table.item(1, 2).text())
            self.assertTrue(good.exists())
            dialog.close()
            timer.stop()


if __name__ == '__main__':
    unittest.main()
