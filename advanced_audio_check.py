"""Offline packaged smoke check, with generated tones and private data only."""
import json,tempfile,wave
from pathlib import Path
import numpy as np
from sounds_config import ComboItem
from offline_audio import OfflineRenderer,write_wave_atomic


def run_check(output,resources,*,render=False):
    from ff14_app import NativeApplication
    from PySide6.QtWidgets import QApplication
    from skillbar_overlay import SkillbarOverlay
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance();images=[]
    def save(widget,name):
        if not render:return
        app.processEvents();app.processEvents();widget.grab().save(str(output/(name+'.png')));images.append(name+'.png')
    with tempfile.TemporaryDirectory(prefix='advanced-',dir=output) as folder:
        root=Path(folder);sounds=root/'sounds';sounds.mkdir()
        samples=np.sin(np.arange(9600,dtype=np.float32)*2*np.pi*440/48000)*.15
        write_wave_atomic(sounds/'示例音效.wav',np.stack([samples,samples],axis=1))
        native=NativeApplication(root,resources,enable_input=False,enable_audio=False);window=native.window
        try:
            job=next((job for job in native.icons.jobs if job.get('id')=='blackmage'),None)
            if job and job.get('skills'):
                for index in range(24):native.model.update_slot(index,icon=job['skills'][index%len(job['skills'])])
            window.open_sound_parameters('示例音效.wav');dialog=window.sound_dialog
            dialog.speed_fixed.setValue(125);dialog.pitch_mode.setCurrentIndex(dialog.pitch_mode.findData('fixed'));dialog.pitch_fixed.setValue(4)
            save(dialog,'01-音效参数');dialog.save_changes()
            window.open_combo_editor();dialog=window.combo_dialog;dialog.ed_name.setText('示例接龙')
            dialog.lst_sounds.setCurrentRow(0);dialog._add_current_sound();dialog._add_current_sound()
            dialog.cmb_mode.setCurrentIndex(dialog.cmb_mode.findData('step'));dialog.table.selectRow(0)
            save(dialog,'02-组合编辑');dialog.save_changes()
            key=next('combo::'+cid for cid in native.effects.combos);window.start_binding(key);window.binding_grid.buttons[12].click();window.show_library()
            window.repeat_accel.setChecked(True)
            save(window,'03-组合可视化绑定');window.close_binding();window.select_slot(12);window.change_page(window.bar_page);save(window,'04-技能栏')
            overlay=SkillbarOverlay(native.model,native.icons,None);overlay.selected=12;overlay.show();save(overlay,'05-呼出技能栏');overlay.close();overlay.deleteLater()
            renderer=OfflineRenderer(sounds,native.effects)
            ordinary=renderer.sound('示例音效.wav');combo=renderer.combo(native.effects.combo_of(key),full=True,randomize=False)
            import sr_roulette as sr
            slowest=sr.stretch_any(renderer.load('示例音效.wav'),.1,min_rate=.1)
            assert len(slowest)==96000
            short_repeat=sr.repeat_stretch(renderer.load('示例音效.wav')[:1920],1.1)
            assert len(short_repeat)==1745
            # Real engine transformations with an injected memory-only output.
            # No start(), rebuild(), sink, source, microphone or media play.
            from skillbar_runtime import CooldownAudio
            class MemoryOutput:
                def __init__(self):self.frames=[]
                def trigger(self,clip,*args,**kwargs):self.frames.append(len(clip));return True
            memory=MemoryOutput();engine=sr.AudioEngine(native.bank,native.cfg)
            engine._active_mixers=lambda:[memory]
            clock=[0.0];audio=CooldownAudio(engine,native.model,clock=lambda:clock[0])
            assert audio.play(12);clock[0]=1.;assert not audio.play(12)
            clock[0]=2.6;assert audio.play(12)
            assert memory.frames==[9600,8727],memory.frames
            engine.stop_all();engine.deleteLater()
            destination=output/'离线组合样本.wav';write_wave_atomic(destination,combo)
            with wave.open(str(destination)) as audio:frames=audio.getnframes()
            assert native.bank.is_combo(12) and frames==19200
            report={'platform':app.platformName(),'input_started':native.poller is not None,'audio_started':native.engine is not None,
                'preview_started':False,'ordinary_processed_frames':len(ordinary),'minimum_speed_frames':len(slowest),'combo_export_frames':frames,
                'combo_binding_verified':native.model.slots[12].sound==key,'saved_settings':native.effects.setting('示例音效.wav').speed_fixed,'images':images}
            report['repeat_acceleration']={'global_switch_saved':native.cfg['repeat_accel_enabled'],'processed_frames':memory.frames,'short_clip_frames':len(short_repeat),'cooldown_rejection_verified':True,'output':'memory-only'}
            (output/'advanced-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report
        finally:
            native.shutdown();window.close();window.deleteLater();app.processEvents()
