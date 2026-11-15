"""Draft-based native editors; all audition goes through the local renderer."""
import copy
from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QPushButton,QDoubleSpinBox,QComboBox,QDialogButtonBox,QFileDialog)
from sounds_config import PITCH_MODE_LABEL,SPEED_MODE_LABEL
from offline_audio import read_setting
from settings_window import ComboEditorDialog
from ui_theme import STYLE,dark_palette


def spin(value,low,high,suffix='',decimals=1):
    box=QDoubleSpinBox();box.setRange(low,high);box.setDecimals(decimals);box.setSuffix(suffix);box.setValue(value)
    return box


class SoundParametersDialog(QDialog):
    saved=Signal()

    def __init__(self,service,name,audition,parent=None):
        super().__init__(parent);self.service=service;self.name=name;self.audition=audition
        self.draft=read_setting(service.effects,name)
        self.setWindowTitle('音效参数 · '+Path(name).stem);self.setPalette(dark_palette());self.setStyleSheet(STYLE);self.resize(540,590)
        root=QVBoxLayout(self);root.setContentsMargins(24,20,24,20);root.setSpacing(12)
        title=QLabel(Path(name).stem);title.setObjectName('Heading');root.addWidget(title)
        hint=QLabel('音效库共用：保存后会影响所有使用此音效的技能格和套装。\n每格音量仍在技能栏中单独设置。');hint.setWordWrap(True);hint.setObjectName('Muted');root.addWidget(hint)
        form=QFormLayout();form.setSpacing(12);root.addLayout(form)
        st=self.draft
        self.volume=spin(st.volume*100,0,200,' %',0);form.addRow('音效音量',self.volume)
        self.speed_fixed=spin(st.speed_fixed*100,50,200,' %',0);form.addRow('基础播放速度',self.speed_fixed)
        self.pitch_mode=QComboBox()
        for value,label in PITCH_MODE_LABEL.items():self.pitch_mode.addItem(label,value)
        self.pitch_mode.setCurrentIndex(self.pitch_mode.findData(st.pitch_mode));form.addRow('变调方式',self.pitch_mode)
        self.pitch_fixed=spin(st.pitch_fixed,-24,24,' 半音');form.addRow('固定变调',self.pitch_fixed)
        self.pitch_step=spin(st.pitch_step,0,12,' 半音');form.addRow('连击步长 / 随机范围 ±',self.pitch_step)
        self.pitch_limit=spin(st.pitch_limit,0,24,' 半音');form.addRow('连击变调上限',self.pitch_limit)
        self.speed_mode=QComboBox()
        for value,label in SPEED_MODE_LABEL.items():self.speed_mode.addItem(label,value)
        self.speed_mode.setCurrentIndex(self.speed_mode.findData(st.speed_mode));form.addRow('连击速度',self.speed_mode)
        self.speed_step=spin(st.speed_step*100,0,40,' %',0);form.addRow('每次速度步长',self.speed_step)
        self.speed_limit=spin(st.speed_limit*100,0,80,' %',0);form.addRow('速度累计上限',self.speed_limit)
        self.window_ms=spin(st.pitch_window_ms/1000,0,30,' 秒',2);form.addRow('连击判定间隔',self.window_ms)
        hint=QLabel('只有成功播放才计入连击。判定间隔应大于公共冷却；试听从第一次播放开始，不累计连击。');hint.setWordWrap(True);hint.setObjectName('Muted');root.addWidget(hint)
        self.feedback=QLabel();self.feedback.setWordWrap(True);root.addWidget(self.feedback)
        bottom=QHBoxLayout();preview=QPushButton('本地试听');preview.clicked.connect(self.preview);bottom.addWidget(preview)
        stop=QPushButton('停止');stop.clicked.connect(audition.stop);bottom.addWidget(stop);bottom.addStretch()
        buttons=QDialogButtonBox();buttons.addButton('取消',QDialogButtonBox.RejectRole);save=buttons.addButton('保存',QDialogButtonBox.AcceptRole);save.setObjectName('PrimaryButton')
        buttons.rejected.connect(self.reject);buttons.accepted.connect(self.save_changes);bottom.addWidget(buttons);root.addLayout(bottom)
        audition.status.connect(self.feedback.setText);self.finished.connect(lambda _:audition.stop())
        self.pitch_mode.currentIndexChanged.connect(self.sync_modes);self.speed_mode.currentIndexChanged.connect(self.sync_modes);self.sync_modes()

    def sync_modes(self):
        mode=self.pitch_mode.currentData();self.pitch_fixed.setEnabled(mode=='fixed');self.pitch_step.setEnabled(mode in ('up','down','random'));self.pitch_limit.setEnabled(mode in ('up','down'))
        active=self.speed_mode.currentData()!='none';self.speed_step.setEnabled(active);self.speed_limit.setEnabled(active)
        self.window_ms.setEnabled(active or mode in ('up','down'))

    def values(self):
        st=copy.deepcopy(self.draft)
        for name in ('volume','speed_fixed','speed_step','speed_limit'):setattr(st,name,getattr(self,name).value()/100)
        for name in ('pitch_fixed','pitch_step','pitch_limit'):setattr(st,name,getattr(self,name).value())
        st.pitch_mode=self.pitch_mode.currentData();st.speed_mode=self.speed_mode.currentData();st.pitch_window_ms=round(self.window_ms.value()*1000)
        return st

    def preview(self):self.audition.request({'kind':'sound','name':self.name,'setting':self.values()})

    def save_changes(self):
        try:self.service.save_sound(self.name,self.values())
        except (OSError,ValueError) as exc:self.feedback.setText('未保存：'+str(exc));return
        self.saved.emit();self.accept()


class LocalPreviewProxy:
    def __init__(self,audition,effects):self.audition=audition;self.effects=effects
    def play_preview(self,item):
        self.audition.request({'kind':'item','item':item},self.effects);return True
    def play_combo(self,combo,from_row=None):
        self.audition.request({'kind':'combo','combo':combo,'from_row':from_row},self.effects);return True


class NativeComboDialog(ComboEditorDialog):
    saved=Signal()

    def __init__(self,service,audition,identity=None,parent=None):
        self.service=service;self.audition=audition
        draft=copy.deepcopy(service.effects)
        combo=copy.deepcopy(draft.combos[identity]) if identity is not None else service.new_draft()
        draft.combos[combo.cid]=combo
        super().__init__(draft,combo,LocalPreviewProxy(audition,draft),parent,sound_root=service.root)
        self.native_theme=True;self.timeline.bar_color=QColor('#b1a581')
        self.setWindowTitle('组合音效 · '+combo.name);self.setPalette(dark_palette());self.setStyleSheet(STYLE)
        self.key_combo.hide()
        for label in self.findChildren(QLabel):
            if label.text()=='专属热键':label.hide()
            if label.text()=='sounds 目录（双击加入）':label.setText('音效库 · 双击加入')
        for buttons in self.findChildren(QDialogButtonBox):buttons.hide()
        root=self.layout()
        hint=QLabel('音效库共用 · 保存后影响所有套装；快捷键在绑定的技能格中设置。试听接龙/累积时会播放完整一轮。');hint.setWordWrap(True);hint.setObjectName('Muted');root.insertWidget(0,hint)
        self.master_volume=spin(draft.combo_setting(combo.cid).volume*100,0,200,' %',0)
        line=QHBoxLayout();line.addWidget(QLabel('组合音量'));line.addWidget(self.master_volume)
        stop=QPushButton('停止试听 / 取消导出');stop.clicked.connect(audition.stop);line.addWidget(stop);line.addStretch()
        self.feedback=QLabel('修改尚未保存。');self.feedback.setWordWrap(True);root.addWidget(self.feedback)
        buttons=QDialogButtonBox();buttons.addButton('取消',QDialogButtonBox.RejectRole);save=buttons.addButton('保存组合',QDialogButtonBox.AcceptRole);save.setObjectName('PrimaryButton')
        buttons.accepted.connect(self.save_changes);buttons.rejected.connect(self.reject);line.addWidget(buttons);root.addLayout(line)
        self.master_volume.valueChanged.connect(lambda v:setattr(self.scfg.combo_setting(self.cdef.cid),'volume',v/100))
        audition.status.connect(self.feedback.setText);self.finished.connect(lambda _:audition.stop())

    def _commit(self):
        # Legacy editor mutations apply only to the isolated draft.
        self.changed.emit()

    def save_changes(self):
        self.cdef.name=self.ed_name.text().strip()
        try:self.service.save_combo(self.cdef,self.scfg.combo_setting(self.cdef.cid))
        except (OSError,ValueError) as exc:self.feedback.setText('未保存：'+str(exc));return
        self.saved.emit();self.accept()

    def _export_wav(self):
        dialog=QFileDialog(self,'导出组合 WAV');dialog.setOption(QFileDialog.DontUseNativeDialog,True)
        dialog.setAcceptMode(QFileDialog.AcceptSave);dialog.setNameFilter('WAV 音频 (*.wav)');dialog.setDefaultSuffix('wav')
        dialog.setDirectory(str(self.service.effects.path.parent));dialog.selectFile('组合音效.wav')
        if dialog.exec() and dialog.selectedFiles():
            self.audition.request({'kind':'combo','combo':self.cdef,'export':dialog.selectedFiles()[0]},self.scfg)
