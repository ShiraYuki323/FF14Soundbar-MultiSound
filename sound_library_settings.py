"""Atomic native edits of shared library settings, preserving legacy wheels."""
from dataclasses import asdict
from pathlib import Path
import copy,math,uuid
from sounds_config import SoundSetting,ComboDef,ComboItem,PITCH_MODES,SPEED_MODES
from skillbar_model import sound_reference,contained_path,is_combo_reference


def validate_setting(setting):
    for key,value in asdict(setting).items():
        if isinstance(value,(int,float)) and not math.isfinite(value):raise ValueError('音频参数必须为有限数值。')
    if setting.pitch_mode not in PITCH_MODES or setting.speed_mode not in SPEED_MODES:raise ValueError('变调或速度模式无效。')
    return setting.clamped()


class LibrarySettings:
    def __init__(self,effects,sound_root):self.effects=effects;self.root=Path(sound_root)

    def _commit(self,candidate):
        candidate.save_strict()
        # Keep the object used by the runtime bank; publish only after replace.
        self.effects.__dict__.update(candidate.__dict__)

    def save_sound(self,name,setting):
        name=sound_reference(name)
        if not name or is_combo_reference(name):raise ValueError('请选择普通音效，组合使用组合编辑器。')
        contained_path(self.root,name)
        cleaned=validate_setting(setting);candidate=copy.deepcopy(self.effects)
        candidate.items[name]=cleaned;self._commit(candidate)

    def new_draft(self):return ComboDef(cid='native_'+uuid.uuid4().hex,name='新组合')

    def save_combo(self,combo,master=None):
        sound_reference('combo::'+combo.cid)
        if not str(combo.name).strip() or len(combo.name.strip())>80:raise ValueError('组合名称应为1到80字。')
        if not 1<=len(combo.items)<=24:raise ValueError('组合需要1到24个成员。')
        for value in [*asdict(combo).values(),*(v for item in combo.items for v in asdict(item).values())]:
            if isinstance(value,(int,float)) and not math.isfinite(value):raise ValueError('组合参数必须为有限数值。')
        for item in combo.items:
            name=sound_reference(item.sound)
            if not name or is_combo_reference(name):raise ValueError('组合成员必须是音效库内的音频文件。')
            contained_path(self.root,name)
        candidate=copy.deepcopy(self.effects);cleaned=copy.deepcopy(combo).clamped();cleaned.name=cleaned.name.strip()
        if any(c.cid!=cleaned.cid and c.name.casefold()==cleaned.name.casefold() for c in candidate.combos.values()):raise ValueError('组合名称重复，请换一个名字。')
        candidate.combos[cleaned.cid]=cleaned
        if master is not None:candidate.items['combo::'+cleaned.cid]=validate_setting(master)
        self._commit(candidate)

    def delete_combo(self,identity):
        if identity not in self.effects.combos:raise ValueError('组合不存在。')
        candidate=copy.deepcopy(self.effects);del candidate.combos[identity];key='combo::'+identity
        for wheel in candidate.wheels:
            wheel.order=[value for value in wheel.order if value!=key]
            wheel.outer_slots=[None if value==key else value for value in wheel.outer_slots]
            wheel.items.pop(key,None)
        self._commit(candidate)
