import json
import sys
import tempfile
import time
import unittest
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from audio_import import AudioData, AudioLibrary, ImportCancelled
except ModuleNotFoundError:
    AudioLibrary = None


def write_wave(path, amplitude=0.05, seconds=0.1):
    path.parent.mkdir(parents=True, exist_ok=True)
    count = int(48000 * seconds)
    values = np.where(np.arange(count) % 100 < 50, amplitude, -amplitude)
    pcm = np.repeat(values[:, None], 2, axis=1)
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(np.round(pcm * 32767).astype('<i2').tobytes())
    return path


def read_wave(path, cancelled=None):
    with wave.open(str(path), 'rb') as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
        samples = samples.reshape(-1, source.getnchannels()).astype(np.float32) / 32768
        return AudioData(samples, source.getframerate())


class AudioImportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(AudioLibrary, '桌面音效导入服务尚未实现')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = write_wave(self.root / '下载' / '我的音效.wav')
        self.original = self.source.read_bytes()
        self.library = AudioLibrary(self.root / '用户库', read_wave)

    def test_import_keeps_original_and_remains_playable_after_source_removed(self):
        result = self.library.import_file(self.source, normalize=False)
        self.assertEqual(result.status, 'imported')
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(result.original_path.read_bytes(), self.original)
        self.source.unlink()
        with wave.open(str(result.path), 'rb') as clip:
            self.assertEqual((clip.getframerate(), clip.getsampwidth(), clip.getnchannels()), (48000, 2, 2))
            self.assertEqual(clip.getnframes(), 4800)

    def test_identical_content_under_another_name_deduplicates_after_restart(self):
        first = self.library.import_file(self.source)
        other = self.source.with_name('换了名字.wav')
        other.write_bytes(self.original)
        reopened = AudioLibrary(self.library.root, read_wave)
        second = reopened.import_file(other)
        self.assertEqual(second.status, 'duplicate')
        self.assertEqual(second.path, first.path)
        self.assertEqual(len(list(self.library.root.glob('*.wav'))), 1)

    def test_same_filename_with_different_content_does_not_overwrite(self):
        first = self.library.import_file(self.source, normalize=False)
        first_bytes = first.path.read_bytes()
        other = write_wave(self.root / '另一个下载' / self.source.name, amplitude=0.3)
        second = self.library.import_file(other, normalize=False)
        self.assertNotEqual(first.path, second.path)
        self.assertEqual(first.path.read_bytes(), first_bytes)
        self.assertTrue(second.path.exists())

    def test_normalization_is_optional_and_peak_limited(self):
        quiet = self.library.import_file(self.source, normalize=False)
        normalized = self.library.import_file(self.source, normalize=True)
        raw = read_wave(quiet.path).samples
        loud = read_wave(normalized.path).samples
        self.assertAlmostEqual(float(np.sqrt(np.mean(raw * raw))), 0.05, places=3)
        self.assertAlmostEqual(float(np.sqrt(np.mean(loud * loud))), 0.1, places=3)
        self.assertLessEqual(float(np.max(np.abs(loud))), 0.892)

    def test_trim_creates_a_distinct_variant_and_preserves_original(self):
        full = self.library.import_file(self.source)
        short = self.library.import_file(self.source, trim=(0.02, 0.06))
        self.assertNotEqual(full.path, short.path)
        self.assertAlmostEqual(short.duration, 0.04, places=4)
        self.assertEqual(short.original_path.read_bytes(), self.original)

    def test_invalid_trim_rejects_without_leaving_audio(self):
        for trim in ((0.08, 0.02), (0.2, None), (-1, 0.05), (float('nan'), None)):
            with self.subTest(trim=trim), self.assertRaises(ValueError):
                self.library.import_file(self.source, trim=trim)
        self.assertEqual(list(self.library.root.glob('*.wav')), [])

    def test_corrupt_or_unsupported_files_do_not_enter_library(self):
        corrupt = self.root / '损坏.wav'
        corrupt.write_bytes(b'not audio')
        unsupported = self.root / '视频.mp4'
        unsupported.write_bytes(self.original)
        for path in (corrupt, unsupported):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.library.import_file(path)
        self.assertEqual(list(self.library.root.glob('*.wav')), [])

    def test_cancelled_import_does_not_leave_partial_files(self):
        with self.assertRaises(ImportCancelled):
            self.library.import_file(self.source, cancelled=lambda: True)
        self.assertEqual(list(self.library.root.glob('*.wav')), [])
        self.assertEqual(list((self.library.root / '.importing').iterdir()), [])

    def test_metadata_failure_rolls_back_only_new_files(self):
        keep = self.library.import_file(self.source, normalize=False)
        keep_bytes = keep.path.read_bytes()
        other = write_wave(self.root / 'new.wav', amplitude=0.2)
        with patch.object(self.library, '_save_index', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.library.import_file(other)
        self.assertEqual(list(self.library.root.glob('*.wav')), [keep.path])
        self.assertEqual(keep.path.read_bytes(), keep_bytes)
        index = json.loads((self.library.root / '.library.json').read_text(encoding='utf-8'))
        self.assertEqual(len(index['entries']), 1)

    def test_silence_is_valid_and_long_audio_is_not_automatically_truncated(self):
        silent = write_wave(self.root / '静音.wav', amplitude=0, seconds=6.1)
        result = self.library.import_file(silent)
        self.assertAlmostEqual(result.duration, 6.1, places=2)
        self.assertIn('较长', result.warning)
        self.assertTrue(np.all(read_wave(result.path).samples == 0))

    def test_nonfinite_decoded_audio_is_rejected(self):
        invalid = AudioLibrary(self.root / 'invalid', lambda *args, **kwargs: AudioData(np.array([[float('nan'), 0]], dtype=np.float32), 48000))
        with self.assertRaises(ValueError):
            invalid.import_file(self.source)
        self.assertEqual(list(invalid.root.glob('*.wav')), [])

    def test_partial_original_copy_failure_leaves_no_broken_archive(self):
        def failing_copy(source, target):
            Path(target).write_bytes(b'partial copy')
            raise OSError('disk full')
        with patch('audio_import.shutil.copy2', side_effect=failing_copy):
            with self.assertRaises(OSError):
                self.library.import_file(self.source)
        self.assertEqual(list(self.library.originals.iterdir()), [])
        self.assertEqual(list(self.library.root.glob('*.wav')), [])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_two_library_instances_cannot_lose_metadata_or_duplicate_one_sound(self):
        other = AudioLibrary(self.library.root, read_wave)
        for library in (self.library, other):
            real_save = library._save_index
            def slow_save(index, save=real_save):
                time.sleep(0.05)
                return save(index)
            library._save_index = slow_save
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(library.import_file, self.source) for library in (self.library, other)]
            results = [future.result() for future in futures]
        self.assertEqual(sorted(result.status for result in results), ['duplicate', 'imported'])
        self.assertEqual(len(list(self.library.root.glob('*.wav'))), 1)


if __name__ == '__main__':
    unittest.main()
