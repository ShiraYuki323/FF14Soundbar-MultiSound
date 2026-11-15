import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skillbar_model import SkillbarConfig


class PresetTests(unittest.TestCase):
    def test_empty_preset_avoids_summon_key_and_deleting_active_restores_review_snapshot(self):
        from screenshot_import import VisualResult
        with tempfile.TemporaryDirectory() as folder:
            model=SkillbarConfig(Path(folder)/'bar.json');first=model.active_preset
            model.apply_visuals([VisualResult(review=('icon','key')) for _ in range(24)]);model.save_preset()
            other=model.new_preset('空白',reserved_key='1')
            self.assertEqual(model.slots[12].key,'');self.assertFalse(model.review)
            self.assertTrue(all(slot.sound is None and slot.icon is None for slot in model.slots))
            model.delete_preset(other)
            self.assertEqual(model.active_preset,first);self.assertEqual(set(model.review[0]),{'icon','key'})
            model.update_slot(0,volume=.7);model.rename_preset(first,'新名字')
            self.assertTrue(model.dirty);self.assertEqual(model.slots[0].volume,.7)

    def test_old_working_config_migrates_without_losing_values_and_dirty_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bar.json';model=SkillbarConfig(path)
            model.bind(0,'old.wav');model.update_slot(0,volume=.4,key='alt+q',icon='job/a.png');model.set_cooldown(1.9)
            raw=json.loads(path.read_text(encoding='utf-8'));raw.pop('presets',None);raw.pop('active_preset',None)
            path.write_text(json.dumps(raw),encoding='utf-8')
            migrated=SkillbarConfig(path)
            self.assertEqual(len(migrated.presets),1);self.assertFalse(migrated.dirty)
            self.assertEqual((migrated.slots[0].sound,migrated.cooldown),('old.wav',1.9))
            migrated.bind(1,'new.wav');self.assertTrue(migrated.dirty)
            loaded=SkillbarConfig(path);self.assertTrue(loaded.dirty);self.assertEqual(loaded.slots[1].sound,'new.wav')
            loaded.save_preset();self.assertFalse(loaded.dirty);self.assertFalse(SkillbarConfig(path).dirty)

    def test_named_presets_restore_every_field_and_are_independent(self):
        from screenshot_import import VisualResult
        with tempfile.TemporaryDirectory() as folder:
            model=SkillbarConfig(Path(folder)/'bar.json')
            model.bind(0,'same.wav');model.update_slot(0,icon='bm/fire.png',key='alt+q',volume=.7);model.set_cooldown(2.1)
            black=model.save_as('黑魔战斗');saved=list(model.slots)
            model.bind(0,'other.wav');model.update_slot(0,icon='whm/cure.png',key='shift+q',volume=1.2);model.set_cooldown(1.5)
            white=model.save_as('白魔');self.assertNotEqual(black,white)
            model.activate_preset(black,reserved_key='y');self.assertEqual(model.slots,saved);self.assertEqual(model.cooldown,2.1)
            self.assertIsNone(model.last_binding);self.assertFalse(model.dirty)
            model.rename_preset(black,'黑魔法师');self.assertEqual(model.preset_name,'黑魔法师')
            loaded=SkillbarConfig(model.path);self.assertEqual(loaded.active_preset,black);self.assertEqual(loaded.slots,saved)
            loaded.delete_preset(white);self.assertNotIn(white,loaded.presets)
            initial=next(i for i in loaded.presets if i!=black);loaded.delete_preset(initial)
            with self.assertRaises(ValueError):loaded.delete_preset(black)

    def test_all_preset_writes_roll_back_and_conflicts_do_not_mutate(self):
        import copy
        with tempfile.TemporaryDirectory() as folder:
            model=SkillbarConfig(Path(folder)/'bar.json');first=model.active_preset
            model.bind(0,'a.wav');other=model.save_as('Other');model.update_slot(0,key='y');model.save_preset()
            model.activate_preset(first)
            for operation in [lambda:model.save_as('Other'),lambda:model.save_as(' '),lambda:model.save_as('x\ny'),lambda:model.activate_preset(other,reserved_key='y')]:
                before=model.path.read_bytes()
                with self.assertRaises(ValueError):operation()
                self.assertEqual(model.path.read_bytes(),before)
            for operation in [lambda:model.save_as('new'),model.save_preset,lambda:model.activate_preset(other),lambda:model.rename_preset(first,'renamed'),lambda:model.delete_preset(other)]:
                before=model.path.read_bytes();state=(list(model.slots),model.cooldown,model.active_preset,copy.deepcopy(model.presets))
                with patch('skillbar_model.os.replace',side_effect=OSError('full')):
                    with self.assertRaises(OSError):operation()
                self.assertEqual(model.path.read_bytes(),before)
                self.assertEqual((model.slots,model.cooldown,model.active_preset,model.presets),state)


if __name__=='__main__':unittest.main()
