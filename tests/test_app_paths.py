import sys
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from app_paths import prepare_user_data
except ModuleNotFoundError:
    prepare_user_data = None


class UserDataTests(unittest.TestCase):
    def test_empty_importer_config_can_be_replaced_by_later_legacy_bindings(self):
        import app_paths
        self.assertTrue(hasattr(app_paths, 'ensure_empty_sound_config'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            standalone, legacy, user = root / 'standalone', root / 'legacy', root / 'user'
            standalone.mkdir()
            legacy.mkdir()
            (legacy / 'sounds.json').write_text('{"order":["old.wav"]}', encoding='utf-8')
            prepare_user_data(standalone, user)
            app_paths.ensure_empty_sound_config(user)
            prepare_user_data(legacy, user)
            self.assertEqual((user / 'sounds.json').read_bytes(), (legacy / 'sounds.json').read_bytes())

    def test_name_collision_migrates_legacy_sound_without_rebinding_to_new_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy, user = root / 'legacy', root / 'user'
            (legacy / 'sounds').mkdir(parents=True)
            (user / 'sounds').mkdir(parents=True)
            (legacy / 'sounds' / 'same.wav').write_bytes(b'old content')
            (user / 'sounds' / 'same.wav').write_bytes(b'new content')
            (legacy / 'sounds.json').write_text('{"order":["same.wav"],"items":{"same.wav":{"hotkey":"1"}}}', encoding='utf-8')
            prepare_user_data(legacy, user)
            self.assertEqual((user / 'sounds' / 'same.wav').read_bytes(), b'new content')
            config = json.loads((user / 'sounds.json').read_text(encoding='utf-8'))
            old_key = config['order'][0]
            self.assertNotEqual(old_key, 'same.wav')
            self.assertEqual((user / 'sounds' / old_key).read_bytes(), b'old content')
            self.assertEqual(config['items'][old_key]['hotkey'], '1')

    def test_standalone_setup_does_not_prevent_later_legacy_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            standalone, legacy, user = root / 'standalone', root / 'legacy', root / 'user'
            standalone.mkdir()
            (legacy / 'sounds').mkdir(parents=True)
            (legacy / 'config.json').write_text('{"hotkey":"ctrl+y"}', encoding='utf-8')
            (legacy / 'sounds.json').write_text('{"order":["old.wav"]}', encoding='utf-8')
            (legacy / 'sounds' / 'old.wav').write_bytes(b'old audio')
            prepare_user_data(standalone, user)
            prepare_user_data(legacy, user)
            self.assertTrue((user / 'config.json').is_file(), '后发现的旧配置也必须迁移')
            self.assertEqual((user / 'config.json').read_bytes(), (legacy / 'config.json').read_bytes())
            self.assertEqual((user / 'sounds.json').read_bytes(), (legacy / 'sounds.json').read_bytes())
            self.assertTrue((user / 'sounds' / 'old.wav').exists())

    def test_interrupted_copy_is_retried_without_retaining_partial_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy, user = root / 'legacy', root / 'user'
            legacy.mkdir()
            (legacy / 'config.json').write_text('{"hotkey":"alt+y"}', encoding='utf-8')
            def partial_copy(source, target):
                Path(target).write_bytes(b'{broken')
                raise OSError('disk full')
            with patch('app_paths.shutil.copy2', side_effect=partial_copy):
                with self.assertRaises(OSError):
                    prepare_user_data(legacy, user)
            prepare_user_data(legacy, user)
            self.assertEqual((user / 'config.json').read_bytes(), (legacy / 'config.json').read_bytes())

    def test_copy_migration_keeps_bindings_and_never_overwrites_or_refills(self):
        self.assertIsNotNone(prepare_user_data, '独立用户数据目录尚未实现')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy, user = root / '旧程序', root / '用户数据'
            (legacy / 'sounds' / '自定义').mkdir(parents=True)
            (legacy / 'sounds' / '自定义' / 'hello.wav').write_bytes(b'original audio')
            (legacy / 'sounds.json').write_text('{"order":["自定义/hello.wav"]}', encoding='utf-8')
            (legacy / 'config.json').write_text('{"hotkey":"ctrl+y"}', encoding='utf-8')
            prepare_user_data(legacy, user)
            self.assertEqual((user / 'sounds.json').read_bytes(), (legacy / 'sounds.json').read_bytes())
            self.assertTrue((user / 'sounds' / '自定义' / 'hello.wav').exists())
            (user / 'config.json').write_text('user choice', encoding='utf-8')
            (user / 'sounds' / '自定义' / 'hello.wav').unlink()
            prepare_user_data(legacy, user)
            self.assertEqual((user / 'config.json').read_text(encoding='utf-8'), 'user choice')
            self.assertFalse((user / 'sounds' / '自定义' / 'hello.wav').exists())
            self.assertTrue((legacy / 'sounds' / '自定义' / 'hello.wav').exists())


if __name__ == '__main__':
    unittest.main()
