import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from qt_cleanup import close_test_windows

class InteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def tearDown(self):close_test_windows(self.app)
    def native(self,root):
        from ff14_app import NativeApplication
        return NativeApplication(root,root,enable_input=False,enable_audio=False)
    def test_foreground_skill_keys_play_but_key_entry_and_dialogs_block_triggers(self):
        import sr_roulette as sr
        from PySide6.QtWidgets import QDialog
        from skillbar_runtime import SkillbarInputPoller

        with tempfile.TemporaryDirectory() as folder, ExitStack() as cleanup:
            native=self.native(Path(folder))
            window=native.window
            cleanup.callback(native.shutdown)
            window.model.update_slot(12,key='f5',sound='a.wav')
            window.show()
            window.activateWindow()
            window.grid.buttons[12].setFocus()
            self.app.processEvents()
            self.assertIs(self.app.activeWindow(),window)

            down=set()
            audio=SimpleNamespace(play=Mock(),play_repeat_last=Mock(),play_next=Mock())
            wheel=SimpleNamespace(raw=None,active=False)
            with patch.object(sr,'is_down',side_effect=lambda code:code in down):
                poller=SkillbarInputPoller(native.cfg,wheel,audio,native.model)
                poller.paused=native.settings_active

                def press():
                    down.add(sr.vk_of('f5'))
                    poller.tick()
                    down.clear()
                    poller.tick()

                press()
                audio.play.assert_called_once_with(12)
                window.key_box.edit.setFocus()
                self.app.processEvents()
                press()
                audio.play.assert_called_once()

                window.grid.buttons[12].setFocus()
                poller.tick()
                dialog=QDialog(window)
                dialog.open()
                self.app.processEvents()
                self.assertTrue(native.settings_active())
                press()
                audio.play.assert_called_once()
                dialog.close()

                window.activateWindow()
                window.grid.buttons[12].setFocus()
                self.app.processEvents()
                poller.tick()
                press()
                self.assertEqual(audio.play.call_count,2)

    def test_bar_switches_apply_and_keep_their_values_after_reopen(self):
        from PySide6.QtCore import Qt

        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            native=self.native(root)
            window=native.window
            window.show()
            self.app.processEvents()
            self.assertTrue(window.bar_page.isAncestorOf(window.wheel_only))
            self.assertTrue(window.bar_page.isAncestorOf(window.always_on_top))
            self.assertFalse(window.windowFlags() & Qt.WindowStaysOnTopHint)
            window.wheel_only.click()
            self.assertFalse(window.tap_action.isEnabled())
            window.always_on_top.click()
            self.assertTrue(window.isVisible())
            self.assertTrue(window.windowFlags() & Qt.WindowStaysOnTopHint)
            native.shutdown()
            window.close()

            native=self.native(root)
            window=native.window
            self.assertTrue(window.wheel_only.isChecked())
            self.assertTrue(window.always_on_top.isChecked())
            self.assertTrue(window.windowFlags() & Qt.WindowStaysOnTopHint)
            window.always_on_top.click()
            self.assertFalse(window.isVisible())
            self.assertFalse(window.windowFlags() & Qt.WindowStaysOnTopHint)
            native.shutdown()
    def test_old_default_migrates_bottom_first_but_custom_order_is_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'config.json').write_text(json.dumps({'wheel_order':list(range(24))}))
            native=self.native(root);self.assertEqual(native.cfg['wheel_order'],list(range(12,24))+list(range(12))+list(range(24,36)));native.shutdown()
            custom=list(reversed(range(24)));(root/'config.json').write_text(json.dumps({'wheel_order':custom}))
            native=self.native(root);self.assertEqual(native.cfg['wheel_order'],custom+list(range(24,36)));native.shutdown()
    def test_capture_crop_and_auto_recognition_with_injected_image_only(self):
        from screen_capture_ui import begin_capture
        with tempfile.TemporaryDirectory() as folder:
            native=self.native(Path(folder));window=native.window;image=QImage(1600,900,QImage.Format_RGB32);image.fill(QColor('blue'))
            fake=SimpleNamespace(path='fake',worker=None,start=Mock())
            def opened(path):
                saved=QImage(str(path));self.assertEqual((saved.width(),saved.height()),(400,200));window.screenshot_dialog=fake
            with patch('screen_capture_ui.QTimer.singleShot',side_effect=lambda delay,fn:fn()),patch.object(window,'open_screenshot',side_effect=opened):
                begin_capture(window,provider=lambda:(image,QRect(0,0,800,450)))
                window.region_capture.region=QRect(10,20,200,100);window.region_capture.accept()
            fake.start.assert_called_once();self.assertFalse(window.capture_pending);native.shutdown()
    def test_offscreen_capture_guard_and_three_close_choices(self):
        from screen_capture_ui import begin_capture
        with tempfile.TemporaryDirectory() as folder:
            native=self.native(Path(folder));window=native.window;begin_capture(window)
            self.assertFalse(window.capture_pending);self.assertIn('禁止',window.status.text())
            window.quit_requested.disconnect();quit_call=Mock();window.quit_requested.connect(quit_call)
            with patch.object(window,'ask_close_action',return_value='cancel'),patch.object(window,'close') as close:
                window.request_close();close.assert_not_called()
            with patch.object(window,'ask_close_action',return_value='background'):window.request_close()
            quit_call.assert_not_called()
            with patch.object(window,'ask_close_action',return_value='quit'):window.request_close()
            quit_call.assert_called_once();native.shutdown()
