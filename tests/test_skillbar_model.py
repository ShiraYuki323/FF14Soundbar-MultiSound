import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SkillbarModelTests(unittest.TestCase):
    def test_screenshot_apply_is_visual_only_atomic_and_keeps_review_after_restart(self):
        from screenshot_import import VisualResult
        with tempfile.TemporaryDirectory() as folder:
            model=self.model(Path(folder)/'bar.json')
            model.bind(0,'keep.wav');model.update_slot(0,volume=.4);model.set_cooldown(1.8)
            results=[VisualResult(icon=None,review=('icon','key')) for _ in range(24)]
            results[0]=VisualResult(key='alt+q',icon='blackmage/skill.png')
            model.apply_visuals(results,reserved_key='y')
            loaded=self.model(model.path)
            self.assertEqual((loaded.slots[0].key,loaded.slots[0].icon,loaded.slots[0].sound,loaded.slots[0].volume,loaded.cooldown),('alt+q','blackmage/skill.png','keep.wav',.4,1.8))
            self.assertEqual(set(loaded.review[1]),{'key','icon'})
            loaded.update_slot(1,key='a');self.assertEqual(loaded.review[1],('icon',))
            loaded.update_slot(1,icon=None);self.assertNotIn(1,loaded.review)
            before=loaded.path.read_bytes();slots=list(loaded.slots);review=dict(loaded.review)
            results[0].key='y'
            with self.assertRaises(ValueError):loaded.apply_visuals(results,reserved_key='y')
            results[0].key='alt+q'
            with patch('skillbar_model.os.replace',side_effect=OSError('full')):
                with self.assertRaises(OSError):loaded.apply_visuals(results)
            self.assertEqual(loaded.path.read_bytes(),before);self.assertEqual(loaded.slots,slots);self.assertEqual(loaded.review,review)

    def model(self, path):
        import skillbar_model
        return skillbar_model.SkillbarConfig(path)

    def test_same_audio_in_separate_slots_survives_restart_and_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bar.json'
            model = self.model(path)
            self.assertEqual(len(model.slots), 36)
            self.assertTrue(all(slot.sound is None for slot in model.slots))
            model.update_slot(23, icon='blackmage/451.png', key='alt+q', volume=0.4)
            model.bind(0, 'folder/笑.wav')
            model.bind(23, 'folder/笑.wav')
            loaded = self.model(path)
            self.assertEqual(loaded.slots[0].sound, 'folder/笑.wav')
            self.assertEqual(loaded.slots[23].sound, 'folder/笑.wav')
            loaded.bind(23, 'new.wav')
            self.assertTrue(loaded.undo())
            restored = self.model(path).slots[23]
            self.assertEqual((restored.sound, restored.icon, restored.key, restored.volume),
                             ('folder/笑.wav', 'blackmage/451.png', 'alt+q', 0.4))

    def test_legacy_preset_migrates_and_two_row_import_preserves_new_row(self):
        from screenshot_import import VisualResult
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bar.json'
            legacy=[{} for _ in range(24)]
            legacy[12]={'key':'1','sound':'keep.wav','volume':.5}
            state={'slots':legacy,'cooldown':1.8,'ability_overrides':{'12':True},'review':{'2':['icon']}}
            path.write_text(json.dumps({'version':1,**state,'presets':{'default':{'name':'原套装',**state}},
                                        'active_preset':'default'}),encoding='utf-8')
            model=self.model(path)
            self.assertFalse(model.dirty)
            self.assertEqual(len(model.slots),36)
            self.assertEqual(model.slots[12].sound,'keep.wav')
            self.assertTrue(model.slots[12].ability)
            self.assertEqual(model.review[2],('icon',))
            model.update_slot(24,key='f1',sound='top.wav')
            model.apply_visuals([VisualResult() for _ in range(24)])
            self.assertEqual((model.slots[24].key,model.slots[24].sound),('f1','top.wav'))
            model.save_preset()
            self.assertEqual(self.model(path).presets['default']['slots'][24]['key'],'f1')

    def test_invalid_paths_duplicate_keys_and_nonfinite_values_do_not_mutate(self):
        with tempfile.TemporaryDirectory() as folder:
            model = self.model(Path(folder) / 'bar.json')
            for value in ['../escape.wav', 'C:/outside.wav', '/outside.wav', '..\\outside.wav']:
                with self.assertRaises(ValueError):
                    model.bind(0, value)
            with self.assertRaises(ValueError):
                model.update_slot(0, key='1')
            with self.assertRaises(ValueError):
                model.update_slot(0, icon='../outside.png')
            for value in [float('nan'), float('inf'), -1]:
                with self.assertRaises(ValueError):
                    model.set_cooldown(value)
            self.assertIsNone(model.slots[0].sound)
            self.assertEqual(model.cooldown, 2.5)

    def test_failed_save_rolls_back_memory_and_preserves_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bar.json'
            model = self.model(path)
            model.bind(0, 'old.wav')
            before = path.read_bytes()
            with patch('skillbar_model.os.replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    model.bind(0, 'new.wav')
            self.assertEqual(model.slots[0].sound, 'old.wav')
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_corrupt_or_incompatible_config_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bar.json'
            for text in ['{broken', json.dumps({'version': 99, 'slots': []})]:
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.model(path)
                self.assertEqual(path.read_text(encoding='utf-8'), text)


if __name__ == '__main__':
    unittest.main()
