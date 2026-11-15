import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from qt_cleanup import close_test_windows


class RepeatAccelerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def tearDown(self):close_test_windows(self.app)

    def engine(self,root,combo=False):
        import sr_roulette as sr
        from skillbar_model import SkillbarConfig
        from skillbar_runtime import SkillbarBank
        from sounds_config import SoundsConfig,ComboDef,ComboItem
        from test_audio_import import write_wave
        write_wave(root/'a.wav',seconds=.2);model=SkillbarConfig(root/'bar.json');effects=SoundsConfig(root/'sounds.json');effects.load()
        name='a.wav'
        if combo:
            effects.combos['c']=ComboDef(cid='c',items=[ComboItem(sound=name),ComboItem(sound=name,delay_ms=200)])
            name='combo::c'
        model.bind(0,name);model.bind(1,name)
        cfg={**sr.DEFAULT_CONFIG,'repeat_accel_enabled':True};engine=sr.AudioEngine(SkillbarBank(model,root,effects),cfg)
        mix=Mock();mix.trigger.return_value=True
        return engine,model,mix

    def test_same_slot_accelerates_caps_and_distinct_slot_or_gap_resets(self):
        import sr_roulette as sr
        with tempfile.TemporaryDirectory() as folder:
            engine,model,mix=self.engine(Path(folder));now=[0.]
            with patch.object(engine,'_active_mixers',return_value=[mix]),patch.object(sr.time,'monotonic',side_effect=lambda:now[0]):
                for i in range(10):now[0]=i*2.6;self.assertTrue(engine.play(0))
                lengths=[len(call.args[0]) for call in mix.trigger.call_args_list]
                self.assertEqual(lengths[0],9600);self.assertAlmostEqual(lengths[1],9600/1.1,delta=2)
                self.assertEqual(lengths[-1],6000)
                now[0]+=2.6;engine.play(1);self.assertEqual(len(mix.trigger.call_args.args[0]),9600)
                now[0]+=2.6;engine.play(0);self.assertEqual(len(mix.trigger.call_args.args[0]),9600)
                now[0]+=6;engine.play(0);self.assertEqual(len(mix.trigger.call_args.args[0]),9600)

    def test_cooldown_rejected_or_failed_play_does_not_advance(self):
        import sr_roulette as sr
        from skillbar_runtime import CooldownAudio
        with tempfile.TemporaryDirectory() as folder:
            engine,model,mix=self.engine(Path(folder));now=[0.];audio=CooldownAudio(engine,model,lambda:now[0])
            with patch.object(engine,'_active_mixers',return_value=[mix]),patch.object(sr.time,'monotonic',side_effect=lambda:now[0]):
                self.assertTrue(audio.play(0));now[0]=1;self.assertFalse(audio.play(0));self.assertEqual(mix.trigger.call_count,1)
                now[0]=2.6;mix.trigger.return_value=False;self.assertFalse(audio.play(0))
                now[0]=3.;mix.trigger.return_value=True;self.assertTrue(audio.play(0))
                self.assertAlmostEqual(len(mix.trigger.call_args.args[0]),9600/1.1,delta=2)

    def test_combo_members_and_delays_speed_up_and_disabled_is_original(self):
        import sr_roulette as sr
        with tempfile.TemporaryDirectory() as folder:
            engine,model,mix=self.engine(Path(folder),combo=True);now=[0.]
            with patch.object(engine,'_active_mixers',return_value=[mix]),patch.object(sr.time,'monotonic',side_effect=lambda:now[0]):
                engine.play(0);now[0]=2.6;engine.play(0)
                calls=mix.trigger.call_args_list
                self.assertAlmostEqual(len(calls[2].args[0]),9600/1.1,delta=2)
                self.assertAlmostEqual(calls[3].args[2],19200/1.1,delta=26)
                engine.cfg['repeat_accel_enabled']=False;now[0]=5.2;engine.play(0)
                self.assertEqual(len(mix.trigger.call_args.args[0]),9600)

    def test_global_switch_persists_and_failed_save_restores_checkbox(self):
        from ff14_app import NativeApplication
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);native=NativeApplication(root,root,enable_input=False,enable_audio=False);window=native.window
            self.assertFalse(window.repeat_accel.isChecked());window.repeat_accel.setChecked(True)
            self.assertTrue(native.cfg['repeat_accel_enabled']);native.shutdown();window.close()
            other=NativeApplication(root,root,enable_input=False,enable_audio=False)
            self.assertTrue(other.window.repeat_accel.isChecked())
            with patch('ff14_app._atomic_bytes',side_effect=OSError('full')):other.window.repeat_accel.setChecked(False)
            self.assertTrue(other.window.repeat_accel.isChecked());self.assertTrue(other.cfg['repeat_accel_enabled']);other.shutdown()

    def test_short_clips_and_existing_fast_processing_still_accelerate(self):
        import sr_roulette as sr
        from test_audio_import import write_wave
        with tempfile.TemporaryDirectory() as folder:
            engine,model,mix=self.engine(Path(folder));now=[0.]
            setting=engine.bank.scfg.setting('a.wav');setting.speed_fixed=2;setting.speed_mode='up';setting.speed_step=.4;setting.pitch_window_ms=30000
            with patch.object(engine,'_active_mixers',return_value=[mix]),patch.object(sr.time,'monotonic',side_effect=lambda:now[0]):
                engine.play(0);now[0]=2.6;engine.play(0)
                self.assertAlmostEqual(len(mix.trigger.call_args.args[0]),round(9600/2.8)/1.1,delta=2)
                write_wave(Path(folder)/'a.wav',seconds=.04);setting.speed_fixed=1;setting.speed_mode='none';engine.load();now[0]=6
                engine.play(0);now[0]=8.6;engine.play(0)
                self.assertAlmostEqual(len(mix.trigger.call_args.args[0]),1920/1.1,delta=2)
        with tempfile.TemporaryDirectory() as folder:
            engine,model,mix=self.engine(Path(folder),combo=True);now=[0.]
            for item in engine.bank.scfg.combos['c'].items:item.rate=2;item.semitones=12
            with patch.object(engine,'_active_mixers',return_value=[mix]),patch.object(sr.time,'monotonic',side_effect=lambda:now[0]):
                engine.play(0);now[0]=2.6;engine.play(0)
                self.assertAlmostEqual(len(mix.trigger.call_args.args[0]),2400/1.1,delta=2)

    def test_short_tone_keeps_pitch_and_long_cooldown_and_stop_reset(self):
        import sr_roulette as sr
        import numpy as np
        tone=(np.sin(np.arange(2880)*2*np.pi*880/48000)*.2).astype(np.float32)
        result=sr.repeat_stretch(np.stack([tone,tone],axis=1),1.6)
        self.assertEqual(len(result),1800)
        spectrum=np.abs(np.fft.rfft(result[:,0]*np.hanning(len(result))))
        peak=np.argmax(spectrum)*48000/len(result);self.assertAlmostEqual(peak,880,delta=35)
        with tempfile.TemporaryDirectory() as folder:
            engine,model,mix=self.engine(Path(folder));model.set_cooldown(10);now=[0.]
            with patch.object(engine,'_active_mixers',return_value=[mix]),patch.object(sr.time,'monotonic',side_effect=lambda:now[0]):
                engine.play(0);now[0]=10.1;engine.play(0)
                self.assertAlmostEqual(len(mix.trigger.call_args.args[0]),9600/1.1,delta=2)
                engine.stop_all();now[0]=20.2;engine.play(0);self.assertEqual(len(mix.trigger.call_args.args[0]),9600)


if __name__=='__main__':unittest.main()
