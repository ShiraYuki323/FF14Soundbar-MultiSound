import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtWidgets import QApplication


class SkillbarRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_wheel_only_blocks_direct_playback_but_allows_wheel_selection_and_pause(self):
        import sr_roulette as sr
        from skillbar_model import SkillbarConfig
        from skillbar_runtime import SkillbarInputPoller
        with tempfile.TemporaryDirectory() as folder:
            model=SkillbarConfig(Path(folder)/'bar.json')
            model.bind(12,'a.wav')
            calls=[];down=set()
            audio=SimpleNamespace(play=lambda i:calls.append(i),play_repeat_last=lambda:calls.append('tap'),
                                  play_next=lambda:calls.append('next'),stop_all=lambda:calls.append('stop'))
            wheel=SimpleNamespace(raw=None,active=False,poll_selection=lambda:None)
            wheel.show_wheel=lambda:setattr(wheel,'active',True)
            wheel.hide_wheel=lambda:setattr(wheel,'active',False)
            def select_sound():
                wheel.hide_wheel()
                return 12
            wheel.commit=select_sound
            cfg=dict(sr.DEFAULT_CONFIG,wheel_only=True,pause_key='f12',cycle_key='f11',hold_ms=0)
            with patch.object(sr,'is_down',side_effect=lambda code:code in down):
                poller=SkillbarInputPoller(cfg,wheel,audio,model)
                def keys(*names):
                    down.clear();down.update(map(sr.vk_of,names));poller.tick()
                keys('1');keys();keys('f11');keys();keys('y');keys()
                self.assertEqual(calls,[])
                keys('y');keys('y');self.assertTrue(wheel.active)
                keys()
                self.assertFalse(wheel.active);self.assertEqual(calls,[12])
                keys('f12');keys('f12');keys()
                keys('y','1');keys('y','1');self.assertFalse(wheel.active)
                keys('f12','1');keys('1');self.assertEqual(calls,[12,'stop'])
                cfg['wheel_only']=False
                poller.rebuild_bindings()
                keys('1');self.assertEqual(calls,[12,'stop'])
                keys();keys('1');self.assertEqual(calls,[12,'stop',12])
                poller.deleteLater()

    def test_sparse_bank_preserves_slot_indices_and_independent_volume(self):
        from skillbar_model import SkillbarConfig
        from skillbar_runtime import SkillbarBank
        from sounds_config import SoundsConfig
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'a.wav').write_bytes(b'fixture')
            model = SkillbarConfig(root / 'bar.json')
            model.bind(0, 'a.wav')
            model.bind(23, 'a.wav')
            model.update_slot(23, volume=0.3)
            effects = SoundsConfig(root / 'sounds.json')
            effects.load()
            effects.setting('a.wav').volume = 0.5
            bank = SkillbarBank(model, root, effects)
            self.assertEqual(len(bank), 36)
            self.assertIsNone(bank.path_at(12))
            self.assertEqual(bank.path_at(23), (root / 'a.wav').resolve())
            self.assertAlmostEqual(bank.setting_at(0).volume, 0.5)
            self.assertAlmostEqual(bank.setting_at(23).volume, 0.15)
            self.assertEqual(effects.setting('a.wav').volume, 0.5)

    def test_global_cooldown_drops_inputs_and_failed_play_does_not_consume_it(self):
        from skillbar_model import SkillbarConfig
        from skillbar_runtime import CooldownAudio
        with tempfile.TemporaryDirectory() as folder:
            model = SkillbarConfig(Path(folder) / 'bar.json')
            model.bind(0, 'a.wav'); model.bind(23, 'b.wav'); model.bind(5, 'bad.wav')
            now = [0.0]
            played = []
            def output(index):
                played.append(index)
                if index != 5:
                    engine.last_idx = index
                return index != 5
            engine = SimpleNamespace(play=output, last_idx=None)
            audio = CooldownAudio(engine, model, clock=lambda: now[0])
            self.assertFalse(audio.play(5))
            self.assertTrue(audio.play(0))
            now[0] = 2.49
            self.assertFalse(audio.play(23))
            self.assertFalse(audio.play_repeat_last())
            self.assertEqual(played, [5, 0])
            now[0] = 2.5
            self.assertTrue(audio.play(23))
            self.assertEqual(played, [5, 0, 23])
            model.set_cooldown(1)
            now[0] = 4.99
            self.assertFalse(audio.play_next())
            now[0] = 5.0
            self.assertTrue(audio.play_next())
            now[0] = 6.0
            self.assertTrue(audio.play_repeat_last())

    def test_combo_key_does_not_fire_bare_key_and_hold_or_pause_never_replays(self):
        import sr_roulette as sr
        from skillbar_model import SkillbarConfig
        from skillbar_runtime import SkillbarInputPoller
        with tempfile.TemporaryDirectory() as folder:
            model = SkillbarConfig(Path(folder) / 'bar.json')
            model.bind(0, 'a.wav'); model.bind(12, 'b.wav')
            played = []
            audio = SimpleNamespace(play=lambda i: played.append(i),
                                    play_repeat_last=lambda: None, play_next=lambda: None)
            wheel = SimpleNamespace(raw=None, active=False)
            down = set()
            with patch.object(sr, 'is_down', side_effect=lambda code: code in down):
                poller = SkillbarInputPoller(dict(sr.DEFAULT_CONFIG), wheel, audio, model)
                down.update([sr.vk_of('ctrl'), sr.vk_of('1')])
                poller.tick(); poller.tick()
                self.assertEqual(played, [0])
                down.remove(sr.vk_of('ctrl')); poller.tick()
                down.add(sr.vk_of('ctrl')); poller.tick()
                self.assertEqual(played, [0], '持续按住 1 时切换修饰键不能伪造新的按下')
                down.clear(); poller.tick()
                down.add(sr.vk_of('1')); poller.tick()
                self.assertEqual(played, [0, 12])
                poller.paused = lambda: True
                poller.tick()
                poller.paused = lambda: False
                poller.tick()
                self.assertEqual(played, [0, 12])
                poller.deleteLater()

    def test_two_abilities_can_play_during_gcd_without_sharing_their_debounce(self):
        from skillbar_model import SkillbarConfig
        from skillbar_runtime import CooldownAudio
        with tempfile.TemporaryDirectory() as folder:
            model = SkillbarConfig(Path(folder) / 'bar.json')
            for i in range(5):
                model.update_slot(i, sound='same.wav', ability=i in (1,2,4))
            now = [0.0]
            output = []
            def play(index):
                if index == 4:return False
                output.append(index);return True
            audio = CooldownAudio(SimpleNamespace(play=play), model, lambda: now[0])
            self.assertTrue(audio.play(0))
            now[0] = .6
            self.assertTrue(audio.play(1))
            self.assertFalse(audio.play(1))
            self.assertFalse(audio.play(4))
            self.assertEqual(audio.ability_cooldown(4)[0],0)
            now[0] = 1.4
            self.assertTrue(audio.play(2))
            self.assertFalse(audio.play(3))
            now[0] = 1.59
            self.assertFalse(audio.play(1))
            now[0] = 1.6
            self.assertTrue(audio.play(1))
            self.assertEqual(audio.ability_cooldown(1), (1.0, 1.0))
            now[0] = 2.5
            self.assertTrue(audio.play(3))
            self.assertFalse(audio.play(1))
            now[0] = 3.1
            self.assertTrue(audio.play(1))
            self.assertEqual(output, [0,1,2,1,3,1])

    def test_temporary_gcd_changes_only_new_public_cycles_and_expires(self):
        from skillbar_model import SkillbarConfig
        from skillbar_runtime import CooldownAudio
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bar.json'
            model = SkillbarConfig(path)
            model.update_slot(12, sound='same.wav')
            model.update_slot(13, temporary_gcd=1.5, temporary_duration=5)
            model.update_slot(14, temporary_gcd=1.8, temporary_duration=3)
            model.save_preset()
            model = SkillbarConfig(path)
            now = [0.0]
            engine = SimpleNamespace(play=lambda index: True)
            audio = CooldownAudio(engine, model, lambda: now[0])
            self.assertTrue(audio.play(12))
            now[0] = 1.0
            audio.press_skill(13)
            self.assertEqual(audio.remaining(), 1.5)
            now[0] = 2.5
            self.assertTrue(audio.play(12))
            self.assertEqual(audio.duration, 1.5)
            now[0] = 3.0
            audio.press_skill(14)
            now[0] = 4.0
            audio.press_skill(13)
            self.assertTrue(audio.play(12))
            self.assertEqual(audio.duration, 1.8)
            now[0] = 6.0
            audio.press_skill(14)
            self.assertTrue(audio.play(12))
            self.assertEqual(audio.duration, 1.8)
            now[0] = 9.0
            self.assertTrue(audio.play(12))
            self.assertEqual(audio.duration, 2.5)


if __name__ == '__main__':
    unittest.main()
