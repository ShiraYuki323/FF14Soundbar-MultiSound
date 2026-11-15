import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from qt_cleanup import close_test_windows

class ShareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def tearDown(self):close_test_windows(self.app)
    def test_delete_batch_rollback_and_undo(self):
        from sound_deletion import SoundTrash
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);root.mkdir(exist_ok=True);(root/'a.wav').write_bytes(b'a');(root/'b.wav').write_bytes(b'b');trash=SoundTrash(root)
            with patch('sound_deletion._atomic_bytes',side_effect=OSError('full')):
                with self.assertRaises(OSError):trash.delete(['a.wav','b.wav'])
            self.assertTrue((root/'a.wav').exists());self.assertTrue((root/'b.wav').exists())
            trash.delete(['a.wav','b.wav']);self.assertFalse((root/'a.wav').exists());self.assertEqual(trash.deleted_names(),{'a.wav','b.wav'})
            trash.undo();self.assertEqual((root/'a.wav').read_bytes(),b'a');self.assertFalse(trash.deleted_names())
            with self.assertRaises(ValueError):trash.delete(['../outside.wav'])
    def test_export_contains_only_bounded_redacted_logs_and_environment(self):
        from diagnostics import export_diagnostics
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'logs').mkdir();(root/'logs'/'app.log').write_text(str(root)+' secret.wav ERROR',encoding='utf-8')
            (root/'config.json').write_text('private');(root/'screen.png').write_bytes(b'private')
            target=root/'export.zip';export_diagnostics(root,target)
            with zipfile.ZipFile(target) as archive:
                self.assertNotIn('config.json',archive.namelist());self.assertNotIn('screen.png',archive.namelist())
                self.assertNotIn(str(root),archive.read('logs/app.log').decode());self.assertIn('environment.json',archive.namelist())
    def test_double_click_uses_local_preview_and_maker_link(self):
        from ff14_app import NativeApplication
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);native=NativeApplication(root,root,enable_input=False,enable_audio=False);window=native.window
            window.model.bind(12,'a.wav');window.refresh();window.show();self.app.processEvents()
            with patch.object(window,'preview_entry') as preview:QTest.mouseDClick(window.grid.buttons[12],Qt.LeftButton);preview.assert_called_once_with('a.wav',1.0)
            with patch('skillbar_ui.sys.platform','win32'),patch('skillbar_ui.os.startfile',create=True) as launch:
                QTest.mouseClick(window.maker,Qt.LeftButton,pos=QPoint(2,2))
                launch.assert_called_once_with('https://space.bilibili.com/1603158')
            native.shutdown()
    def test_bundle_update_does_not_restore_deleted_files_or_overwrite_user_audio(self):
        from bundled_audio import sync_bundled_audio
        from sound_deletion import SoundTrash
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bundle=root/'bundle';bundle.mkdir();data=root/'data';(data/'sounds').mkdir(parents=True)
            (bundle/'a.wav').write_bytes(b'a');sync_bundled_audio(bundle,data);SoundTrash(data/'sounds').delete(['a.wav'])
            (bundle/'b.wav').write_bytes(b'b');sync_bundled_audio(bundle,data)
            self.assertFalse((data/'sounds'/'a.wav').exists());self.assertEqual((data/'sounds'/'b.wav').read_bytes(),b'b')
            (data/'sounds'/'b.wav').write_bytes(b'user');(bundle/'b.wav').write_bytes(b'new');sync_bundled_audio(bundle,data)
            self.assertEqual((data/'sounds'/'b.wav').read_bytes(),b'user')
