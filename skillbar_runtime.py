"""Adapt skill slots to the original mixer and non-blocking input state machine."""
from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import sr_roulette as sr
from skillbar_model import contained_path,is_combo_reference,sound_label,SLOT_COUNT


class SkillbarBank(sr.SoundBank):
    def __init__(self, model, sound_root, effects):
        # SoundBank.__init__ reloads the old wheel. This adapter owns its own indices.
        sr.QObject.__init__(self)
        self.model, self.sound_root, self.scfg = model, Path(sound_root), effects
        self.slots = SLOT_COUNT
        self.reload()

    def reload(self):
        self.items=[]
        for slot in self.model.slots:
            if is_combo_reference(slot.sound):
                combo=self.scfg.combo_of(slot.sound)
                entry=sr.ComboEntry(combo) if combo else None
                if entry is not None:entry.gain_scale=slot.volume
                self.items.append(entry)
            else:self.items.append(contained_path(self.sound_root,slot.sound))

    def setting_at(self, index):
        if not 0 <= index < self.slots or not self.model.slots[index].sound:
            return None
        slot = self.model.slots[index]
        base = self.scfg.setting(slot.sound)
        return replace(base, volume=base.volume * slot.volume)

    def full_at(self, index):
        return self.model.slots[index].sound or '' if 0 <= index < self.slots else ''

    def name_at(self, index):
        return sound_label(self.full_at(index),self.scfg)

    def index_of_name(self, name):
        return next((i for i, slot in enumerate(self.model.slots) if slot.sound == name), -1)


ABILITY_DEBOUNCE_SECONDS = 1.0


class CooldownAudio:
    def __init__(self, engine, model, clock=time.monotonic):
        self.engine, self.model, self.clock = engine, model, clock
        self.until = 0.0
        self.duration = 0.0
        self._cycle = -1
        self._ability_timers = {}
        self._temporary_timers = {}
        self._temporary_slot = None

    def __getattr__(self, name):
        return getattr(self.engine, name)

    def remaining(self):
        return max(0.0, self.until - self.clock())

    def ability_cooldown(self,index):
        slot=self.model.slots[index]
        timer=self._ability_timers.get(index)
        if timer and timer[0]==(slot.key,slot.icon):
            return max(0.0,timer[1]-self.clock()),timer[2]
        return 0.0,ABILITY_DEBOUNCE_SECONDS

    def reset_preset_state(self):
        self._cycle=-1
        self._ability_timers.clear()
        self._temporary_timers.clear()
        self._temporary_slot = None

    def _active_temporary_slot(self, index, now):
        slot = self.model.slots[index]
        timer = self._temporary_timers.get(index)
        identity = (slot.key, slot.icon, slot.temporary_gcd, slot.temporary_duration)
        return slot if timer and timer[0] == identity and now < timer[1] else None

    def effective_gcd(self, now):
        if self._temporary_slot is not None:
            slot = self._active_temporary_slot(self._temporary_slot, now)
            if slot is not None:
                return slot.temporary_gcd
        return self.model.cooldown

    def press_skill(self, index):
        slot = self.model.slots[index]
        if slot.temporary_gcd is not None:
            now = self.clock()
            if self._active_temporary_slot(index, now) is None:
                identity = (slot.key, slot.icon, slot.temporary_gcd, slot.temporary_duration)
                self._temporary_timers[index] = (identity, now + slot.temporary_duration)
                self._temporary_slot = index
        return self.play(index)

    def play(self, index):
        if not isinstance(index, int) or not 0 <= index < SLOT_COUNT:
            return False
        slot=self.model.slots[index]
        ability=self.model.slot_is_ability(slot)
        if not slot.sound or (self.ability_cooldown(index)[0] if ability else self.remaining()):return False
        if not self.engine.play(index):
            return False
        now=self.clock()
        duration=ABILITY_DEBOUNCE_SECONDS if ability else self.effective_gcd(now)
        until=now+duration
        if ability:
            self._ability_timers[index]=((slot.key,slot.icon),until,duration)
        else:
            self.duration=duration
            self.until=until
        return True

    def play_repeat_last(self):
        return self.play(self.engine.last_idx)

    def play_next(self):
        for step in range(1, SLOT_COUNT+1):
            index = (self._cycle + step) % SLOT_COUNT
            if self.model.slots[index].sound and self.play(index):
                self._cycle = index
                return True
        return False


class SkillbarInputPoller(sr.InputPoller):
    def __init__(self, cfg, wheel, audio, model):
        self.model = model
        self._hard_pause=False
        self._frame_blocked=False
        self._was_blocked=False
        self.trigger_state=None
        self.on_trigger_state_changed=None
        self._summon_suppressed = False
        super().__init__(cfg, wheel, audio)

    def _input_blocked(self):
        return self._frame_blocked

    def run_tap_action(self):
        if self.cfg.get('wheel_only'):
            return False
        return super().run_tap_action()

    def set_user_pause(self,on):
        if not on:self._hard_pause=False
        super().set_user_pause(on)

    def toggle_trigger_pause(self):
        if self.user_paused:
            self.set_user_pause(False)
        else:
            self._hard_pause=True
            self.audio.stop_all()
            self.set_user_pause(True)

    def _down(self, name):
        if name == self.hotkey_name and self._summon_suppressed:
            return False
        return self._exact_down(name)

    def _exact_down(self, name):
        if not super()._down(name):
            return False
        parts = sr.spec_parts(name)
        for mod in ('ctrl', 'alt', 'shift'):
            if sr.is_down(sr.vk_of(mod)) != (mod in parts):
                return False
        return True

    def rebuild_bindings(self):
        seen = {sr.norm_spec(self.cfg.get('hotkey', 'y'))}
        self.pause_key=sr.norm_spec(self.cfg.get('pause_key',''))
        if self.pause_key:seen.add(self.pause_key)
        self._pause_base=sr.spec_parts(self.pause_key)[-1] if self.pause_key else ''
        self._pause_down=bool(self._pause_base and super()._down(self._pause_base))
        bindings = []
        if not self.cfg.get('wheel_only'):
            for option, action in [('repeat_last_key', self.audio.play_repeat_last), ('cycle_key', self.audio.play_next)]:
                key = sr.norm_spec(self.cfg.get(option, ''))
                if key and key not in seen:
                    seen.add(key)
                    bindings.append((key, action))
            for index, slot in enumerate(self.model.slots):
                if slot.key and (slot.sound or slot.temporary_gcd is not None) and slot.key not in seen:
                    seen.add(slot.key)
                    play = self.audio.press_skill if slot.temporary_gcd is not None else self.audio.play
                    bindings.append((slot.key, lambda i=index, action=play: action(i)))
        self._extra = bindings
        self._extra_prev = {key: self._down(key) for key, _ in bindings}
        self._physical_prev = {sr.spec_parts(key)[-1]: super(SkillbarInputPoller, self)._down(sr.spec_parts(key)[-1]) for key, _ in bindings}
        if super()._down(sr.spec_parts(self.hotkey_name)[-1]):
            self._summon_suppressed = True
            self._prev = False

    def tick(self):
        editing=super()._input_blocked()
        pause_down=bool(self._pause_base and super()._down(self._pause_base))
        if pause_down and not self._pause_down and not editing and self._exact_down(self.pause_key):
            self.toggle_trigger_pause()
        self._pause_down=pause_down
        blocked=editing or self._hard_pause
        # Synchronize one frame on return so a key held across focus/pause cannot replay.
        self._frame_blocked=blocked or self._was_blocked
        self._was_blocked=blocked
        summon_base = sr.spec_parts(self.hotkey_name)[-1]
        summon_physical = super()._down(summon_base)
        if summon_physical and (self._frame_blocked or not self._exact_down(self.hotkey_name)):
            self._summon_suppressed = True
        if self._summon_suppressed:
            # Discard the entire gesture, including its eventual release.
            # A modifier transition is not a release of the invocation key.
            self._prev = False
            self._held_to_wheel = True
            if self.wheel.active:self.wheel.hide_wheel()
        physical = {base: super(SkillbarInputPoller, self)._down(base) for base in self._physical_prev}
        for key, _ in self._extra:
            base = sr.spec_parts(key)[-1]
            if physical.get(base) and self._physical_prev.get(base):
                # Changing only Ctrl/Alt/Shift while the base key stays held
                # must not manufacture another skill press.
                self._extra_prev[key] = True
        super().tick()
        if self.user_paused:
            state='paused'
        elif editing:
            state='editing'
        else:
            state='wheel_only' if self.cfg.get('wheel_only') else 'active'
        if self.trigger_state!=state:
            self.trigger_state=state
            if self.on_trigger_state_changed:self.on_trigger_state_changed(state)
        self._physical_prev = physical
        if not summon_physical:self._summon_suppressed = False
