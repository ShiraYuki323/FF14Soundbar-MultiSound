"""Independent skill slots, with transactional user-data persistence."""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import copy
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath

COLUMNS = 12
LEGACY_SLOTS = 2 * COLUMNS
SLOT_COUNT = 3 * COLUMNS
# The new row is shown above both original rows so existing slot IDs stay stable.
DISPLAY_ORDER = tuple(range(LEGACY_SLOTS, SLOT_COUNT)) + tuple(range(LEGACY_SLOTS))
SOUND_MODES = {'cycle': '列表循环', 'random': '随机播放'}


def slot_location(index):
    row = ('中排', '下排', '上排')[index // COLUMNS]
    return f'{row}第 {index % COLUMNS + 1} 格'


def relative_name(value: str | None) -> str | None:
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise ValueError('文件路径必须是相对路径。')
    text = value.replace('\\', '/')
    path = PurePosixPath(text)
    if path.is_absolute() or ':' in text or '\x00' in text or any(p in ('..', '.') for p in text.split('/')):
        raise ValueError('文件必须位于音效库或图标库内。')
    return path.as_posix()


def canonical_key(value: str) -> str:
    if not value.strip():
        return ''
    parts = value.strip().lower().split('+')
    mods = ('ctrl', 'alt', 'shift')
    bases = [part for part in parts if part not in mods]
    if len(parts) != len(set(parts)) or len(bases) != 1 or not re.fullmatch(
        r'[a-z0-9=\-]|f(?:[1-9]|1[0-9]|2[0-4])|space|tab|enter|esc|capslock|comma|period|slash|semicolon|quote|mouse_(?:left|right|middle|4|5)', bases[0]
    ):
        raise ValueError('请输入单键或 Ctrl / Alt / Shift 组合键。')
    return '+'.join([mod for mod in mods if mod in parts] + bases)

def reserved_key_set(keys):
    if isinstance(keys,str):keys=(keys,)
    return {canonical_key(key) for key in keys if key}

def reserved_trigger_keys(cfg):
    return reserved_key_set((cfg.get('hotkey','y'),cfg.get('pause_key','')))


def is_combo_reference(value):return isinstance(value,str) and value.startswith('combo::')


def sound_reference(value):
    if is_combo_reference(value):
        if not re.fullmatch(r'combo::[A-Za-z0-9_-]{1,64}',value):raise ValueError('组合音效引用无效。')
        return value
    return relative_name(value)


def sound_label(value,effects=None):
    if not value:return '未设音效'
    if is_combo_reference(value):
        combo=effects.combo_of(value) if effects is not None else None
        return '◆ '+combo.name if combo else '◆ 组合缺失' if effects is not None else '◆ 组合音效'
    return Path(value).stem


def slot_sound_label(slot, effects=None):
    if slot.extra_sounds:
        return f'{len(slot.sounds)} 个音效 · {SOUND_MODES[slot.sound_mode]}'
    return sound_label(slot.sound, effects)


def key_label(key: str, compact=False) -> str:
    mouse={'mouse_left':'M1','mouse_right':'M2','mouse_middle':'M3','mouse_4':'M4','mouse_5':'M5'}
    if compact:
        for prefix, short in [('ctrl+', 'c'), ('alt+', 'a'), ('shift+', 's')]:
            if key.startswith(prefix) and '+' not in key[len(prefix):]:
                base=key[len(prefix):]
                return short + mouse.get(base,base.upper())
    names={**mouse,'ctrl':'Ctrl','alt':'Alt','shift':'Shift'}
    return '+'.join(names.get(p,p.upper()) for p in key.split('+'))


@dataclass(frozen=True)
class SkillSlot:
    key: str = ''
    icon: str | None = None
    sound: str | None = None
    volume: float = 1.0
    ability: bool | None = None  # None follows the identified icon.
    temporary_gcd: float | None = None
    temporary_duration: float = 15.0
    extra_sounds: tuple[str, ...] = ()
    sound_mode: str = 'cycle'

    @property
    def sounds(self):
        return (self.sound, *self.extra_sounds) if self.sound else ()

    def with_changes(self, **changes):
        if 'icon' in changes and changes['icon'] != self.icon:
            changes.setdefault('ability',None)
            changes.setdefault('temporary_gcd', None)
        if 'sound' in changes:
            changes.setdefault('extra_sounds', ())
            changes.setdefault('sound_mode', 'cycle')
        return replace(self,**changes)


class SkillbarConfig:
    def __init__(self, path: Path, *, ability_icons=()):
        self.path = Path(path)
        self.ability_icons=frozenset(ability_icons)
        keys = list('1234567890') + ['-', '=']
        self.slots = [SkillSlot(key=key) for key in [*('ctrl+' + k for k in keys), *keys]]
        self.slots.extend(SkillSlot() for _ in range(COLUMNS))
        self.cooldown = 2.5
        self.last_binding = None
        self.review = {}
        data={}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('version') not in (1, 2):
                    raise ValueError('不支持的技能栏配置版本或格子数量。')
                slots = self._slots_from_state(data)
                self.slots, self.cooldown = self._validate(slots, data.get('cooldown', 2.5))
                self.review = self._validate_review(data.get('review', {}))
            except (TypeError, KeyError, AttributeError, json.JSONDecodeError) as exc:
                raise ValueError('技能栏配置损坏，请保留文件并从备份恢复。') from exc
        if 'presets' in data:
            self.presets,self.active_preset=self._validate_presets(data['presets'],data.get('active_preset'))
        else:
            self.active_preset='default'
            self.presets={'default':{'name':'套装 01',**self._state_payload(self.slots,self.cooldown,self.review)}}
        self.presets_persisted='presets' in data

    def slot_is_ability(self,slot):
        return slot.ability if slot.ability is not None else slot.icon in self.ability_icons

    @staticmethod
    def _validate(slots, cooldown):
        cooldown = float(cooldown)
        if not math.isfinite(cooldown) or not 0.1 <= cooldown <= 60:
            raise ValueError('公共冷却应在 0.1 到 60 秒之间。')
        cleaned = []
        for slot in slots:
            volume = float(slot.volume)
            if not math.isfinite(volume) or not 0 <= volume <= 2:
                raise ValueError('音量应在 0% 到 200% 之间。')
            if slot.ability is not None and type(slot.ability) is not bool:
                raise ValueError('能力技开关必须是开启、关闭或自动。')
            gcd = None if slot.temporary_gcd is None else float(slot.temporary_gcd)
            duration = float(slot.temporary_duration)
            if gcd is not None and (not math.isfinite(gcd) or not .1 <= gcd <= 60):
                raise ValueError('临时 GCD 应在 0.1 到 60 秒之间。')
            if not math.isfinite(duration) or not .1 <= duration <= 600:
                raise ValueError('持续时间应在 0.1 到 600 秒之间。')
            sound = sound_reference(slot.sound)
            if not isinstance(slot.extra_sounds, (list, tuple)):
                raise ValueError('绑定音效列表格式错误。')
            extra_sounds = tuple(sound_reference(value) for value in slot.extra_sounds)
            if extra_sounds and (not sound or None in extra_sounds or
                                 len(set((sound, *extra_sounds))) != len(extra_sounds) + 1):
                raise ValueError('绑定音效列表不能含空项或重复项。')
            if not isinstance(slot.sound_mode, str) or slot.sound_mode not in SOUND_MODES:
                raise ValueError('绑定音效的播放方式无效。')
            cleaned.append(replace(slot, key=canonical_key(slot.key), icon=relative_name(slot.icon),
                                   sound=sound, volume=volume, temporary_gcd=gcd,
                                   temporary_duration=duration if gcd is not None else 15.0,
                                   extra_sounds=extra_sounds, sound_mode=slot.sound_mode if extra_sounds else 'cycle'))
        keys = [slot.key for slot in cleaned if slot.key]
        if len(keys) != len(set(keys)):
            raise ValueError('该按键已绑定其他技能，请先修改或清空。')
        return cleaned, cooldown

    @staticmethod
    def _validate_review(review):
        if not isinstance(review,dict):raise ValueError('待确认标记格式错误。')
        cleaned={}
        for index,fields in review.items():
            index=int(index)
            if not 0<=index<SLOT_COUNT or not isinstance(fields,(list,tuple)) or any(field not in ('key','icon') for field in fields):
                raise ValueError('待确认标记无效。')
            if fields:cleaned[index]=tuple(dict.fromkeys(fields))
        return cleaned

    @staticmethod
    def _state_payload(slots,cooldown,review):
        serialized=[asdict(slot) for slot in slots]
        overrides={}
        temporary_gcds={}
        for index,value in enumerate(serialized):
            if not value['extra_sounds']:
                del value['extra_sounds'], value['sound_mode']
            ability=value.pop('ability')
            if ability is not None:overrides[str(index)]=ability
            gcd=value.pop('temporary_gcd')
            duration=value.pop('temporary_duration')
            if gcd is not None:
                temporary_gcds[str(index)]={'gcd':gcd,'duration':duration}
        payload={'cooldown':cooldown,'slots':serialized}
        if overrides:payload['ability_overrides']=overrides
        if temporary_gcds:payload['temporary_gcds']=temporary_gcds
        if review:payload['review']=review
        return payload

    @staticmethod
    def _slots_from_state(state):
        if not isinstance(state.get('slots'),list) or len(state['slots']) not in (LEGACY_SLOTS,SLOT_COUNT):
            raise ValueError('技能栏配置的格子数量无效。')
        slots=[SkillSlot(**value) for value in state['slots']]
        overrides=state.get('ability_overrides',{})
        if not isinstance(overrides,dict):raise ValueError('能力技设置格式错误。')
        indices={str(i) for i in range(len(slots))}
        for index,enabled in overrides.items():
            if index not in indices or type(enabled) is not bool:
                raise ValueError('能力技设置无效。')
            i=int(index);slots[i]=replace(slots[i],ability=enabled)
        effects=state.get('temporary_gcds',{})
        if not isinstance(effects,dict):
            raise ValueError('临时 GCD 设置格式错误。')
        for index,effect in effects.items():
            if index not in indices or not isinstance(effect,dict) or not {'gcd','duration'} <= effect.keys():
                raise ValueError('临时 GCD 设置无效。')
            i=int(index)
            slots[i]=replace(slots[i],temporary_gcd=effect['gcd'],temporary_duration=effect['duration'])
        slots.extend(SkillSlot() for _ in range(SLOT_COUNT-len(slots)))
        return slots

    @staticmethod
    def _preset_name(name):
        if not isinstance(name,str):raise ValueError('套装名称无效。')
        name=name.strip()
        if not name or len(name)>40 or any(ord(c)<32 for c in name):raise ValueError('套装名称应为1到40个字符，不能含换行。')
        return name

    @classmethod
    def _validate_presets(cls,presets,active):
        if not isinstance(presets,dict) or not 1<=len(presets)<=100 or not isinstance(active,str) or active not in presets:
            raise ValueError('套装配置无效，请保留配置并恢复备份。')
        cleaned={};names=set()
        for identity,value in presets.items():
            if not isinstance(identity,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',identity) or not isinstance(value,dict):
                raise ValueError('套装标识无效。')
            name=cls._preset_name(value.get('name'))
            if name.casefold() in names:raise ValueError('套装名称重复，请使用其他名称。')
            names.add(name.casefold())
            slots,cd=cls._validate(cls._slots_from_state(value),value.get('cooldown',2.5))
            review=cls._validate_review(value.get('review',{}))
            cleaned[identity]={'name':name,**cls._state_payload(slots,cd,review)}
        return cleaned,active

    @property
    def preset_name(self):return self.presets[self.active_preset]['name']

    def used_keys(self):
        return {slot.key for slot in self.slots if slot.key} | {
            slot['key'] for preset in self.presets.values() for slot in preset['slots'] if slot['key']
        }

    @property
    def dirty(self):
        saved={k:v for k,v in self.presets[self.active_preset].items() if k!='name'}
        return self._state_payload(self.slots,self.cooldown,self.review)!=saved

    def _commit(self, slots, cooldown, review=None, *,presets=None,active_preset=None):
        slots, cooldown = self._validate(slots, cooldown)
        review=self._validate_review(self.review if review is None else review)
        presets,active=self._validate_presets(self.presets if presets is None else presets,self.active_preset if active_preset is None else active_preset)
        payload = {'version': 2,**self._state_payload(slots,cooldown,review),'presets':presets,'active_preset':active}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=self.path.name + '.', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
        self.slots, self.cooldown = slots, cooldown
        self.review=review
        self.presets,self.active_preset=presets,active
        self.presets_persisted=True

    def save_preset(self):
        presets=copy.deepcopy(self.presets)
        presets[self.active_preset]={'name':self.preset_name,**self._state_payload(self.slots,self.cooldown,self.review)}
        self._commit(self.slots,self.cooldown,presets=presets)

    def _add_preset(self,name,slots,cooldown,review):
        if len(self.presets)>=100:raise ValueError('最多保存100个套装，请先删除不需要的套装。')
        name=self._preset_name(name);identity=uuid.uuid4().hex;presets=copy.deepcopy(self.presets)
        presets[identity]={'name':name,**self._state_payload(slots,cooldown,review)}
        self._commit(slots,cooldown,review,presets=presets,active_preset=identity)
        self.last_binding=None
        return identity

    def save_as(self,name):
        return self._add_preset(name,self.slots,self.cooldown,self.review)

    def new_preset(self,name,reserved_key=''):
        keys=list('1234567890-=')
        reserved=reserved_key_set(reserved_key)
        slots=[SkillSlot(key=k if k not in reserved else '') for k in [*('ctrl+'+k for k in keys),*keys]]
        slots.extend(SkillSlot() for _ in range(COLUMNS))
        return self._add_preset(name,slots,2.5,{})

    def _preset_state(self,identity,reserved_key=''):
        if identity not in self.presets:raise ValueError('套装不存在。')
        entry=self.presets[identity];slots=self._slots_from_state(entry)
        reserved=reserved_key_set(reserved_key)
        if any(slot.key in reserved for slot in slots):raise ValueError('此套装含有呼出键或暂停键，请先修改冲突的快捷键。')
        return slots,entry['cooldown'],self._validate_review(entry.get('review',{}))

    def activate_preset(self,identity,reserved_key=''):
        slots,cd,review=self._preset_state(identity,reserved_key)
        self._commit(slots,cd,review,active_preset=identity);self.last_binding=None

    def rename_preset(self,identity,name):
        if identity not in self.presets:raise ValueError('套装不存在。')
        presets=copy.deepcopy(self.presets);presets[identity]['name']=self._preset_name(name)
        self._commit(self.slots,self.cooldown,presets=presets)

    def delete_preset(self,identity,reserved_key=''):
        if identity not in self.presets:raise ValueError('套装不存在。')
        if len(self.presets)==1:raise ValueError('至少保留一个套装。')
        presets=copy.deepcopy(self.presets);del presets[identity]
        if identity==self.active_preset:
            active=next(iter(presets));slots,cd,review=self._preset_state(active,reserved_key)
        else:active=self.active_preset;slots,cd,review=self.slots,self.cooldown,self.review
        self._commit(slots,cd,review,presets=presets,active_preset=active);self.last_binding=None

    def apply_visuals(self, visuals, reserved_key=''):
        if len(visuals) not in (LEGACY_SLOTS,SLOT_COUNT):
            raise ValueError('截图必须包含两排或三排，每排 12 格。')
        slots=list(self.slots)
        review=dict(self.review)
        for index,value in zip(DISPLAY_ORDER[-len(visuals):],visuals):
            slots[index]=slots[index].with_changes(key=value.key,icon=value.icon)
            if value.review:
                review[index]=value.review
            else:
                review.pop(index,None)
        reserved=reserved_key_set(reserved_key)
        if any(canonical_key(slot.key) in reserved for slot in slots):
            raise ValueError('截图中的按键与呼出键或暂停键冲突，请先修改。')
        self._commit(slots,self.cooldown,review)

    def update_slot(self, index: int, **changes):
        if not 0 <= index < SLOT_COUNT:
            raise ValueError('技能格位置无效。')
        slots = list(self.slots)
        slots[index] = slots[index].with_changes(**changes)
        review=dict(self.review)
        if index in review:
            fields=tuple(field for field in review[index] if field not in changes)
            if fields:review[index]=fields
            else:review.pop(index)
        self._commit(slots, self.cooldown, review)

    def bind(self, index: int, sound: str | None):
        self.bind_sounds(index, (sound,) if sound is not None else ())

    def bind_sounds(self, index, sounds, mode='cycle'):
        if not 0 <= index < SLOT_COUNT:
            raise ValueError('技能格位置无效。')
        if not isinstance(sounds, (list, tuple)):
            raise ValueError('绑定音效列表格式错误。')
        before = self.slots[index]
        self.update_slot(index, sound=sounds[0] if sounds else None, extra_sounds=sounds[1:], sound_mode=mode)
        self.last_binding = (index, before, self.slots[index])

    def undo(self) -> bool:
        if self.last_binding is None:
            return False
        index, before, after = self.last_binding
        slot = self.slots[index]
        if (slot.sounds, slot.sound_mode) != (after.sounds, after.sound_mode):
            self.last_binding = None
            return False
        self.update_slot(index, sound=before.sound, extra_sounds=before.extra_sounds, sound_mode=before.sound_mode)
        self.last_binding = None
        return True

    def set_cooldown(self, seconds):
        self._commit(self.slots, seconds)


def contained_path(root: Path, name: str | None) -> Path | None:
    name = relative_name(name)
    if name is None:
        return None
    root = Path(root).resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError('文件不能位于资源目录以外。')
    return candidate
