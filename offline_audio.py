"""Bounded local-only waveform rendering, using the original DSP and schedule."""
from pathlib import Path
import copy,os,random,tempfile,wave
import numpy as np
from audio_import import ImportCancelled
from audio_import_qt import decode_audio
from skillbar_model import contained_path
from sounds_config import SoundSetting,PITCH_FIXED,PITCH_RANDOM
import sr_roulette as sr


def check_cancel(cancelled):
    if cancelled():raise ImportCancelled('已取消音频处理。')


def read_setting(effects,name):
    return copy.deepcopy(effects.items.get(effects.canon(name),SoundSetting())) if effects is not None else SoundSetting()


class OfflineRenderer:
    def __init__(self,root,effects,cancelled=lambda:False,fade_ms=6):
        self.root=Path(root);self.effects=effects;self.cancelled=cancelled;self.fade_ms=fade_ms;self.cache={};self.bytes=0

    def load(self,name):
        check_cancel(self.cancelled)
        if name in self.cache:return self.cache[name]
        path=contained_path(self.root,name)
        if path is None or not path.is_file():return None
        data=decode_audio(path,self.cancelled).samples.copy()
        if self.bytes+data.nbytes>192*1024*1024:raise ValueError('组合成员过长，请先截取较短片段。')
        data-=data.mean(axis=0,keepdims=True)
        count=min(max(16,round(48000*self.fade_ms/1000)),len(data)//2)
        if count:
            ramp=np.linspace(0,1,count,dtype=np.float32)[:,None];data[:count]*=ramp;data[-count:]*=ramp[::-1]
        self.cache[name]=data;self.bytes+=data.nbytes;return data

    def sound(self,name,setting=None,gain_scale=1):
        clip=self.load(name)
        if clip is None:raise ValueError('音效文件缺失，请重新导入。')
        setting=(setting or read_setting(self.effects,name)).clamped()
        clip=sr.stretch_any(clip,setting.speed_fixed)
        semi=setting.pitch_fixed if setting.pitch_mode==PITCH_FIXED else random.randint(-round(setting.pitch_step),round(setting.pitch_step)) if setting.pitch_mode==PITCH_RANDOM else 0
        if semi:clip=sr.pitch_shift(clip,semi)
        check_cancel(self.cancelled)
        return clip*setting.volume*gain_scale

    def item(self,item,rate=None,semi=None):
        clip=self.load(item.sound)
        if clip is None:return None
        clip=sr.trim_clip(clip,item.clip_start_ms,item.clip_len_ms)
        if clip is None:return None
        clip=sr.stretch_any(clip,item.rate if rate is None else rate)
        amount=item.semitones if semi is None else semi
        if amount:clip=sr.pitch_shift(clip,amount)
        check_cancel(self.cancelled);return clip

    def combo(self,definition,*,full=False,from_row=None,randomize=True,master=None,gain_scale=1):
        check_cancel(self.cancelled);c=copy.deepcopy(definition).clamped();items=c.items
        if not items:raise ValueError('组合还没有成员。')
        if from_row is not None:order=list(range(max(0,from_row),len(items)))
        elif full and c.steps_per_trigger():order=list(range(len(items)))
        elif not randomize and c.mode=='rand':
            order=random.Random(0).sample(range(len(items)),min(c.count,len(items)))
            if not c.shuffle:order.sort()
        else:order=c.play_order(0)
        semi,rate=sr.AudioEngine.combo_random(c) if randomize else (c.semitones,c.rate)
        clips={};durations={};total_bytes=0
        for i in order:
            item=items[i];r=item.rate*rate;s=item.semitones+semi
            if randomize:
                r*=1+random.uniform(-item.rand_rate,item.rand_rate);s+=random.uniform(-item.rand_semi,item.rand_semi)
            clip=self.item(item,r,s)
            durations[i]=len(clip)/48000 if clip is not None else 0
            if clip is not None:
                total_bytes+=clip.nbytes
                if total_bytes>192*1024*1024:raise ValueError('组合音频过长，请减少成员或裁剪片段。')
                clips[i]=clip
        plan=sr.combo_plan(items,order,durations,48000)
        total=min(48000*300,max((delay+len(clips[i]) for i,delay in plan if i in clips),default=0))
        if not total:raise ValueError('组合中没有能播放的成员，可能文件缺失或被裁空。')
        output=np.zeros((total,2),np.float32)
        setting=master or read_setting(self.effects,'combo::'+c.cid)
        for i,delay in plan:
            check_cancel(self.cancelled)
            if i not in clips or delay>=total:continue
            clip=clips[i][:total-delay]
            output[delay:delay+len(clip)]+=clip*items[i].gain*setting.volume*gain_scale
        return output


def write_wave_atomic(path,samples,cancelled=lambda:False):
    path=Path(path);check_cancel(cancelled)
    if path.suffix.lower()!='.wav':raise ValueError('请选择 .wav 文件。')
    if samples.ndim!=2 or samples.shape[1]!=2 or not len(samples) or not np.isfinite(samples).all():raise ValueError('音频处理结果无效。')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.audio-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w+b') as output:
            with wave.open(output,'wb') as destination:
                destination.setnchannels(2);destination.setsampwidth(2);destination.setframerate(48000)
                destination.writeframes((np.clip(samples,-1,1)*32767).astype('<i2').tobytes())
            output.flush();os.fsync(output.fileno())
        check_cancel(cancelled);os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)
