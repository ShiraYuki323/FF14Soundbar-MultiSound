import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import tempfile
import unittest
from pathlib import Path
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication
from qt_cleanup import close_test_windows


class SkillbarUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sounds = self.root / 'sounds'; self.sounds.mkdir()
        from test_audio_import import write_wave
        write_wave(self.sounds / 'one.wav')
        write_wave(self.sounds / 'two.wav')
        icons = self.root / 'icons'; icons.mkdir()
        image = QImage(80, 80, QImage.Format_ARGB32)
        image.fill(QColor('#5577aa')); image.save(str(icons / 'skill.png'))
        (icons / 'catalog.json').write_text(json.dumps({'jobs': [
            {'id': 'blackmage', 'name': '黑魔法师', 'image': 'skill.png', 'skills': ['skill.png']}
        ]}), encoding='utf-8')
        from skillbar_icons import IconCatalog
        from skillbar_model import SkillbarConfig
        from skillbar_ui import SkillbarWindow
        self.model = SkillbarConfig(self.root / 'bar.json')
        self.model.update_slot(23, icon='skill.png', key='alt+q', volume=0.7)
        self.window = SkillbarWindow(self.model, self.sounds, IconCatalog(icons), {'hotkey': 'y', 'tap_action': 'repeat_last'})

    def tearDown(self):
        close_test_windows(self.app)
        self.temp.cleanup()

    def test_bind_opens_all_slots_without_mutating_then_click_binds_and_undo_restores(self):
        before = self.model.path.read_bytes()
        self.window.show_library()
        self.window.bind_buttons['one.wav'].click()
        self.assertFalse(self.window.binding_panel.isHidden())
        self.assertEqual(len(self.window.binding_grid.buttons), 36)
        self.assertEqual(self.model.path.read_bytes(), before)
        self.window.binding_grid.buttons[0].click()
        self.window.binding_grid.buttons[23].click()
        self.assertEqual(self.window.bound_indices('one.wav'), [0, 23])
        self.window.bind_buttons['two.wav'].click()
        self.window.binding_grid.buttons[23].click()
        self.assertEqual(self.window.bound_indices('one.wav'), [0])
        self.assertEqual(self.window.bound_indices('two.wav'), [23])
        self.window.undo_button.click()
        self.assertEqual(self.window.bound_indices('one.wav'), [0, 23])
        slot = self.model.slots[23]
        self.assertEqual((slot.icon, slot.key, slot.volume), ('skill.png', 'alt+q', 0.7))
        self.window.finish_binding.click()
        from skillbar_model import SkillbarConfig
        self.assertEqual(SkillbarConfig(self.model.path).slots[23].sound, 'one.wav')

    def test_refresh_new_audio_does_not_assign_and_close_binding_changes_nothing(self):
        self.window.show_library()
        self.window.bind_buttons['one.wav'].click()
        before = self.model.path.read_bytes()
        self.window.finish_binding.click()
        from test_audio_import import write_wave
        write_wave(self.sounds / 'new.wav')
        self.window.refresh_library()
        self.assertIn('new.wav', self.window.bind_buttons)
        self.assertEqual(self.window.bound_indices('new.wav'), [])
        self.assertEqual(self.model.path.read_bytes(), before)

    def test_profession_picker_applies_only_icon_to_selected_skill(self):
        self.model.bind(23, 'one.wav')
        self.window.select_slot(23)
        self.window.open_icon_picker()
        picker = self.window.icon_picker
        self.assertIn('blackmage', picker.job_buttons)
        picker.job_buttons['blackmage'].click()
        self.assertEqual(len(picker.skill_buttons), 1)
        picker.skill_buttons[0].click()
        self.assertEqual(self.model.slots[23].sound, 'one.wav')
        self.assertEqual(self.model.slots[23].icon, 'skill.png')
        self.assertEqual(self.model.slots[23].key, 'alt+q')

    def test_native_key_capture_accepts_minus_equal_and_mouse_side_key(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.model.update_slot(22,key='')
        self.window.select_slot(12)
        QTest.keyClick(self.window.key_box.edit,Qt.Key_Minus)
        self.assertEqual(self.model.slots[12].key,'-')
        QTest.keyClick(self.window.key_box.edit,Qt.Key_Equal)
        self.assertEqual(self.model.slots[12].key,'=')
        self.window._change_key('mouse_left')
        self.assertEqual(self.model.slots[12].key,'mouse_left')

    def test_frame_atlas_uses_one_transparent_frame_instead_of_whole_sheet(self):
        image=QImage(852,288,QImage.Format_ARGB32)
        image.fill(QColor('transparent'))
        image.save(str(self.root/'icons'/'frame.png'))
        frame=self.window.icons.pixmap('frame.png')
        self.assertEqual((frame.width(),frame.height()),(88,91))

    def test_dropdown_has_dark_background_and_readable_unselected_text(self):
        from PySide6.QtGui import QPalette
        combo=self.window.sound_select
        self.window.show(); self.app.processEvents()
        combo.showPopup(); self.app.processEvents()
        view=combo.view(); view.ensurePolished()
        palette=view.palette()
        self.assertLess(palette.color(QPalette.Base).lightness(),100)
        self.assertGreater(palette.color(QPalette.Text).lightness(),170)
        combo.hidePopup()

    def test_import_table_and_detached_menu_use_same_dark_palette(self):
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QMenu
        from sound_import_ui import SoundImportDialog
        dialog=SoundImportDialog(self.sounds,[],self.window)
        menu=QMenu(self.window); menu.addAction('设置')
        for name,widget,role in [('导入表格',dialog.table.viewport(),QPalette.Base),('托盘菜单',menu,QPalette.Window)]:
            widget.ensurePolished()
            with self.subTest(surface=name):
                self.assertLess(widget.palette().color(role).lightness(),100)
        dialog.close(); menu.close()


if __name__ == '__main__':
    unittest.main()
