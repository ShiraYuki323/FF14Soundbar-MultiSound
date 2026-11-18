"""Native FF14 settings and visual sound-to-skill binding."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal, QUrl,QTimer
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QFont, QIcon, QPixmap, QPolygonF
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QToolButton, QStackedWidget, QScrollArea, QComboBox,
    QDoubleSpinBox, QDialog, QDialogButtonBox, QFormLayout, QSizePolicy, QStyle, QSlider,QSizeGrip,QCheckBox,QLineEdit,QMenu,
    QListWidget, QListWidgetItem,
)
from skillbar_model import (contained_path,key_label,canonical_key,is_combo_reference,reserved_trigger_keys,
                            slot_location,COLUMNS,DISPLAY_ORDER,SLOT_COUNT,SOUND_MODES,slot_sound_label)
from skillbar_presets_ui import PresetActions
from skillbar_advanced_ui import AdvancedActions
from library_management_ui import LibraryManagement
from skillbar_paint import navigation_icon,framed_icon
from window_chrome import WindowHeader
from diagnostics import VERSION

from ui_theme import STYLE, apply_theme, dark_palette, choose_audio_files

MAKER_URL='https://space.bilibili.com/1603158'


def volume_icon():
    pixmap=QPixmap(18,18); pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#b9c6c8'),1.4)); painter.setBrush(Qt.NoBrush)
    painter.drawPolygon(QPolygonF([QPointF(2,7),QPointF(5,7),QPointF(9,3),QPointF(9,15),QPointF(5,11),QPointF(2,11)]))
    painter.drawArc(QRectF(7,5,6,8),-60*16,120*16)
    painter.drawArc(QRectF(7,2,10,14),-55*16,110*16)
    painter.end(); return QIcon(pixmap)


class SlotButton(QToolButton):
    def __init__(self, model, icons, index, parent=None):
        super().__init__(parent)
        self.model, self.icons, self.index = model, icons, index
        self.selected = False
        self.matched = False
        self.remaining=0;self.duration=2.5
        self.setMinimumSize(44, 66)
        self.setMaximumSize(72, 66)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)

    double_clicked=Signal()

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:self.double_clicked.emit();event.accept()
        else:super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        from skillbar_paint import paint_slot,fit_frame
        painter=QPainter(self)
        rect=fit_frame(QRectF(4,8,self.width()-8,self.height()-9))
        slot=self.model.slots[self.index]
        paint_slot(painter,rect,self.icons,slot,selected=self.selected,matched=self.matched,ability=self.model.slot_is_ability(slot),
                   review=getattr(self.model,'review',{}).get(self.index,()),hover=self.underMouse(),remaining=self.remaining,duration=self.duration)


class VolumeSlider(QSlider):
    focus_left=Signal()
    def focusOutEvent(self,event):
        self.focus_left.emit();super().focusOutEvent(event)


class SlotGrid(QWidget):
    clicked = Signal(int)
    double_clicked=Signal(int)

    def __init__(self, model, icons, parent=None,name_resolver=None):
        super().__init__(parent)
        self.name_resolver=name_resolver or slot_sound_label
        self.model, self.icons = model, icons
        self.buttons, self.labels = [None]*SLOT_COUNT, [None]*SLOT_COUNT
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setHorizontalSpacing(5)
        layout.setVerticalSpacing(3)
        for row in range(SLOT_COUNT//COLUMNS):
            number = QLabel(str(SLOT_COUNT//COLUMNS-row)); number.setStyleSheet('color:#d2bf91')
            layout.addWidget(number, row*3, 0)
            for column in range(COLUMNS):
                index = DISPLAY_ORDER[row*COLUMNS+column]
                button = SlotButton(model, icons, index)
                button.double_clicked.connect(lambda i=index:self.double_clicked.emit(i))
                button.clicked.connect(lambda checked=False, i=index: self.clicked.emit(i))
                layout.addWidget(button, row*3, column+1)
                self.buttons[index]=button
                label = QLabel()
                label.setAlignment(Qt.AlignCenter)
                label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
                label.setMinimumWidth(0)
                label.setStyleSheet('font-size:10px;color:#bec3c4');label.setFixedHeight(14)
                layout.addWidget(label, row*3+1, column+1)
                self.labels[index]=label

            layout.setRowMinimumHeight(row*3+2, 5)
        self.refresh()

    def refresh(self, selected=-1, matching=None):
        for index, slot in enumerate(self.model.slots):
            name = self.name_resolver(slot)
            button = self.buttons[index]
            button.selected, button.matched = index == selected, bool(matching and matching in slot.sounds)
            description = f'{slot_location(index)} · {key_label(slot.key) or "未设置按键"} · {name}'
            if self.model.slot_is_ability(slot):description+=' · 能力技（独立冷却）'
            review=getattr(self.model,'review',{}).get(index,())
            if review:description+=' · 待确认：'+'、'.join('键位' if field=='key' else '图标' for field in review)
            button.setToolTip(description); button.setAccessibleName(description); button.update()
            self.labels[index].setText(self.labels[index].fontMetrics().elidedText(name, Qt.ElideRight, 65) if slot.sound else '')
            self.labels[index].setToolTip(name if slot.sound else '')


class SoundBindingDialog(QDialog):
    def __init__(self, window, index, save):
        super().__init__(window)
        self.setWindowTitle(f'{slot_location(index)} · 绑定多个音效')
        self.resize(490, 350)
        self.window = window
        self.save = save
        slot = window.model.slots[index]
        layout = QVBoxLayout(self)
        picker = QHBoxLayout()
        self.available = QComboBox()
        self.available.setAccessibleName('可添加的音效')
        for name, label in window.library_items():
            self.available.addItem(label, name)
            self.available.setItemData(self.available.count() - 1, name, Qt.ToolTipRole)
        picker.addWidget(self.available, 1)
        self.add_button = QPushButton('添加')
        self.add_button.clicked.connect(self.add_sound)
        picker.addWidget(self.add_button)
        layout.addLayout(picker)

        self.sounds = QListWidget()
        self.sounds.setAccessibleName('已绑定的音效列表')
        for name in slot.sounds:
            self.append_sound(name)
        layout.addWidget(self.sounds, 1)

        actions = QHBoxLayout()
        self.up_button = QPushButton('上移')
        self.down_button = QPushButton('下移')
        self.remove_button = QPushButton('移除')
        self.up_button.clicked.connect(lambda: self.move_sound(-1))
        self.down_button.clicked.connect(lambda: self.move_sound(1))
        self.remove_button.clicked.connect(self.remove_sound)
        for button in (self.up_button, self.down_button, self.remove_button):
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(QLabel('播放方式'))
        self.mode = QComboBox()
        self.mode.setAccessibleName('播放方式')
        for value, label in SOUND_MODES.items():
            self.mode.addItem(label, value)
        self.mode.setCurrentIndex(self.mode.findData(slot.sound_mode))
        actions.addWidget(self.mode)
        layout.addLayout(actions)

        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('保存')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(self.save_binding)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.available.currentIndexChanged.connect(self.refresh_actions)
        self.sounds.currentRowChanged.connect(self.refresh_actions)
        self.sounds.setCurrentRow(0)
        self.refresh_actions()

    def references(self):
        return tuple(self.sounds.item(row).data(Qt.UserRole) for row in range(self.sounds.count()))

    def append_sound(self, name):
        label = self.window.sound_label(name)
        if self.window.missing_reference(name):
            label += '（缺失）'
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, name)
        item.setToolTip(name)
        self.sounds.addItem(item)

    def refresh_actions(self):
        row, count = self.sounds.currentRow(), self.sounds.count()
        name = self.available.currentData()
        self.add_button.setEnabled(bool(name) and name not in self.references())
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < count - 1)
        self.remove_button.setEnabled(row >= 0)
        self.mode.setEnabled(count > 1)

    def add_sound(self):
        name = self.available.currentData()
        if name and name not in self.references():
            self.append_sound(name)
            self.sounds.setCurrentRow(self.sounds.count() - 1)
            self.refresh_actions()

    def move_sound(self, step):
        row = self.sounds.currentRow()
        if row >= 0 and 0 <= row + step < self.sounds.count():
            self.sounds.insertItem(row + step, self.sounds.takeItem(row))
            self.sounds.setCurrentRow(row + step)
            self.refresh_actions()

    def remove_sound(self):
        row = self.sounds.currentRow()
        if row >= 0:
            self.sounds.takeItem(row)
            self.refresh_actions()

    def save_binding(self):
        if self.save(self.references(), self.mode.currentData()):
            self.accept()
        else:
            self.feedback.setText(self.window.status.text())


class IconPicker(QDialog):
    chosen = Signal(str)

    def __init__(self, icons, parent=None):
        super().__init__(parent)
        self.setWindowTitle('选择职业与技能图标')
        self.setPalette(dark_palette())
        self.setStyleSheet(STYLE)
        self.resize(730, 540)
        self.icons = icons
        self.job_buttons, self.skill_buttons = {}, []
        root = QVBoxLayout(self)
        self.heading = QLabel('选择职业'); self.heading.setObjectName('Heading')
        root.addWidget(self.heading)
        back = QPushButton('返回职业列表'); back.clicked.connect(self.show_jobs); root.addWidget(back)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); root.addWidget(scroll)
        self.holder = QWidget(); self.layout = QGridLayout(self.holder)
        self.layout.setAlignment(Qt.AlignTop); scroll.setWidget(self.holder)
        self.show_jobs()

    def clear(self):
        while self.layout.count():
            widget = self.layout.takeAt(0).widget()
            if widget: widget.hide(); widget.deleteLater()

    def show_jobs(self):
        self.clear(); self.job_buttons = {}; self.skill_buttons = []
        self.heading.setText('选择职业')
        categories=list(self.icons.jobs)
        if getattr(self.icons,'extras',[]):categories.append({'id':'role','name':'职能技能','image':self.icons.extras[0],'skills':self.icons.extras})
        for index, job in enumerate(categories):
            button = QToolButton()
            button.setText(job['name']); button.setIcon(QIcon(self.icons.pixmap(job['image'])))
            button.setIconSize(QSize(38, 38)); button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setMinimumSize(100, 82)
            button.clicked.connect(lambda checked=False, j=job: self.choose_job(j))
            self.job_buttons[job['id']] = button
            self.layout.addWidget(button, index//6, index%6)

    def choose_job(self, job):
        self.clear(); self.skill_buttons = []
        self.heading.setText(job['name'] + ' · 选择技能')
        for index, name in enumerate(job['skills']):
            button = QToolButton();button.setObjectName('SkillChoice');button.setIcon(framed_icon(self.icons,name))
            button.setIconSize(QSize(60, 60)); button.setFixedSize(72, 72)
            button.setToolTip(Path(name).stem); button.setAccessibleName(job['name'] + '技能 ' + Path(name).stem)
            button.clicked.connect(lambda checked=False, n=name: self._choose(n))
            self.skill_buttons.append(button); self.layout.addWidget(button, index//8, index%8)

    def _choose(self, name):
        self.chosen.emit(name); self.accept()


class SkillbarWindow(QWidget,PresetActions,AdvancedActions,LibraryManagement):
    changed = Signal(str)
    preferences_changed = Signal()
    closed = Signal()
    quit_requested=Signal()
    trigger_pause_requested=Signal()

    def __init__(self, model, sound_root, icons, cfg, engine=None,resources=None,effects=None):
        super().__init__()
        self.setWindowFlags(Qt.Window|Qt.FramelessWindowHint|Qt.WindowMinimizeButtonHint|Qt.WindowMaximizeButtonHint)
        apply_theme()
        self.setObjectName('FF14Root'); self.setWindowTitle('FF14 音效技能栏')
        self.setStyleSheet(STYLE); self.resize(1160, 740); self.setMinimumSize(1040, 720)
        self.model, self.sound_root, self.icons, self.cfg, self.engine = model, Path(sound_root), icons, cfg, engine
        from sounds_config import SoundsConfig
        from sound_library_settings import LibrarySettings
        self.effects=effects if effects is not None else SoundsConfig(model.path.parent/'sounds.json')
        if effects is None:self.effects.load()
        self.library_settings=LibrarySettings(self.effects,self.sound_root)
        self.sound_dialog=self.combo_dialog=None
        self.delete_selection=set();self.wheel_dialog=None
        self.capture_pending=False;self.capture_temp=None;self.region_capture=None;self.shutting_down=False
        self.resources=Path(resources) if resources is not None else Path(__file__).resolve().parent
        self.selected, self.binding_sound = 12, None
        self.pending_volume=None
        self.icon_picker = self.import_dialog = None
        self.screenshot_dialog=None
        self.preferences_writer = None
        self.audition_icon=volume_icon()
        self.player = QMediaPlayer(self); self.output = QAudioOutput(self)
        self.output.setVolume(0.45); self.player.setAudioOutput(self.output)
        self.preview_path = None
        self.player.errorOccurred.connect(lambda error, text: self.status.setText('试听失败：'+text))
        self.player.errorOccurred.connect(lambda *_:self.clear_preview_entry())
        self.player.mediaStatusChanged.connect(self.on_preview_media_status)
        self.setAcceptDrops(True)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        title = WindowHeader(self);self.titlebar=title;line = QHBoxLayout(title)
        line.setContentsMargins(24, 16, 24, 14)
        brand=QLabel('XIV'); brand.setObjectName('Brand'); line.addWidget(brand)
        heading=QLabel('音效技能栏'); heading.setObjectName('WindowTitle'); line.addWidget(heading)
        line.addStretch(); label = QLabel(f'FF14 · 分享版 {VERSION}'); label.setObjectName('Muted'); line.addWidget(label)
        self.maker=QPushButton('黑魔高手');self.maker.setObjectName('MakerLink')
        self.maker.setCursor(Qt.PointingHandCursor);self.maker.setToolTip('在默认浏览器打开 B 站主页\n'+MAKER_URL)
        self.maker.clicked.connect(self.open_maker_profile);line.addWidget(self.maker)
        line.addSpacing(10)
        for attr,text,tip,action in [('minimize_button','—','最小化',lambda:self.showMinimized()),('maximize_button','□','最大化 / 还原',title.toggle_maximized),('close_button','×','退出或留在后台',self.request_close)]:
            button=QPushButton(text);button.setObjectName('WindowClose' if attr=='close_button' else 'WindowControl')
            button.setFixedSize(28,26);button.setToolTip(tip);button.clicked.connect(action);setattr(self,attr,button);line.addWidget(button)
        root.addWidget(title)
        body = QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0); root.addLayout(body, 1)
        nav_frame=QFrame(); nav_frame.setObjectName('SideNav'); nav_frame.setFixedWidth(142)
        nav = QVBoxLayout(nav_frame); nav.setContentsMargins(10,20,10,15); nav.setSpacing(7); body.addWidget(nav_frame)
        self.pages = QStackedWidget(); body.addWidget(self.pages, 1)
        self.bar_page = QWidget(); self.library_page = QWidget(); self.audio_page=QWidget(); self.preferences_page = QWidget()
        from skillbar_tutorial_ui import build_tutorial
        self.tutorial_page=build_tutorial(self)
        self.nav_buttons = []
        for index,(name, page) in enumerate([('技能栏',self.bar_page),('音效库',self.library_page),('声音输出',self.audio_page),('更多设置',self.preferences_page),('使用教程',self.tutorial_page)]):
            button = QPushButton(name); button.setObjectName('NavButton');button.setIcon(navigation_icon(index));button.setIconSize(QSize(16,16));button.setCheckable(True)
            button.clicked.connect(lambda checked=False, p=page: self.change_page(p))
            nav.addWidget(button); self.nav_buttons.append((button, page)); self.pages.addWidget(page)
        nav.addStretch()
        self.status = QLabel(); self.status.setObjectName('Status'); self.status.setWordWrap(True)
        from local_audition import LocalAudition
        self.audition=LocalAudition(self.sound_root,self.effects,self.player,self);self.audition.status.connect(self.status.setText)
        self.audition.failed.connect(self.clear_preview_entry)
        self.audition.status.connect(lambda message:logging.getLogger('ff14').info('Audition: %s',message))
        self._build_bar(); self._build_library(); self._build_preferences()
        footer=QFrame();footer.setObjectName('Footer');footer_line=QHBoxLayout(footer);footer_line.setContentsMargins(0,0,1,0);footer_line.setSpacing(0)
        footer_line.addWidget(self.status,1);self.size_grip=QSizeGrip(self);self.size_grip.setFixedSize(16,16);footer_line.addWidget(self.size_grip,0,Qt.AlignBottom);root.addWidget(footer)
        self.change_page(self.bar_page); self.select_slot(12)
        self.game_audio=None;self._cooling=False
        self.status_timer=QTimer(self);self.status_timer.setInterval(50);self.status_timer.timeout.connect(self.refresh_cooldown);self.status_timer.start()

    def open_maker_profile(self):
        try:
            if sys.platform=='win32':
                os.startfile(MAKER_URL)
            elif not QDesktopServices.openUrl(QUrl(MAKER_URL)):
                raise OSError('Desktop services could not open the URL')
        except OSError as exc:
            logging.getLogger('ff14').warning('Opening maker profile failed: %s',exc)
            self.status.setText('无法打开作者主页。请检查默认浏览器设置，或手动访问：'+MAKER_URL)

    def _build_bar(self):
        from settings_window import KeyBox
        outer=QVBoxLayout(self.bar_page);outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea();scroll.setWidgetResizable(True);outer.addWidget(scroll)
        content=QWidget();scroll.setWidget(content)
        layout=QVBoxLayout(content);layout.setContentsMargins(28,18,28,14);layout.setSpacing(10)
        setup=QHBoxLayout();setup.setSpacing(8)
        self.manual_button=QPushButton('手动设置');self.manual_button.setIcon(navigation_icon(0));self.manual_button.clicked.connect(lambda:self.select_slot(self.selected));setup.addWidget(self.manual_button)
        self.screenshot_button=QPushButton('截图导入');self.screenshot_button.setIcon(navigation_icon(3));self.screenshot_button.clicked.connect(lambda:self.open_screenshot());setup.addWidget(self.screenshot_button)
        self.capture_button=QPushButton('截图并识别');self.capture_button.clicked.connect(self.capture_screen);setup.addWidget(self.capture_button)
        setup.addStretch()
        self.always_on_top=QCheckBox('窗口置顶')
        self.always_on_top.clicked.connect(lambda on:self._set_preference('always_on_top',on))
        setup.addWidget(self.always_on_top)
        self.wheel_only=QCheckBox('只播放轮盘音效')
        self.wheel_only.setToolTip('长按呼出轮盘并选中音效后松手播放。')
        self.wheel_only.clicked.connect(lambda on:self._set_preference('wheel_only',on))
        setup.addWidget(self.wheel_only)
        layout.addLayout(setup)
        layout.addWidget(self.build_preset_controls())
        self.grid=SlotGrid(self.model,self.icons,name_resolver=self.slot_sound_label);self.grid.clicked.connect(self.select_slot);self.grid.double_clicked.connect(self.preview_slot);layout.addWidget(self.grid)
        cdframe=QFrame();cdframe.setObjectName('CooldownStrip');cdline=QHBoxLayout(cdframe);cdline.setContentsMargins(0,12,0,0)
        self.ready_label=QLabel();self.ready_label.setObjectName('Ready');cdline.addWidget(self.ready_label)
        self.bar_pause_button=QPushButton('暂停触发');self.bar_pause_button.setEnabled(False)
        self.bar_pause_button.clicked.connect(lambda:self.trigger_pause_requested.emit())
        cdline.addWidget(self.bar_pause_button);cdline.addStretch()
        self.set_trigger_state('inactive')
        self.repeat_accel=QCheckBox('连续同键自动加速');self.repeat_accel.setChecked(self.cfg.get('repeat_accel_enabled') is True)
        self.repeat_accel.setToolTip('全局开关：首次100%，每次成功连按加10%，上限160%；换键或停顿后恢复。\n判定间隔为5秒，公共冷却较长时至少保留其2倍；冷却内的连按不累计。\n在音效已有速度上叠加，试听不参与。')
        self.repeat_accel.toggled.connect(lambda on:self._set_preference('repeat_accel_enabled',on));cdline.addWidget(self.repeat_accel);cdline.addSpacing(24);cdline.addWidget(QLabel('公共冷却'))
        self.cooldown=QDoubleSpinBox();self.cooldown.setRange(.1,60);self.cooldown.setDecimals(2);self.cooldown.setFixedWidth(80)
        self.cooldown.setValue(self.model.cooldown);self.cooldown.editingFinished.connect(self._change_cooldown);cdline.addWidget(self.cooldown);cdline.addWidget(QLabel('秒'));layout.addWidget(cdframe)
        editor=QFrame();editor.setObjectName('Editor');form=QGridLayout(editor)
        form.setContentsMargins(0,13,0,0);form.setHorizontalSpacing(18);form.setVerticalSpacing(8)
        selected_group=QWidget();selected_row=QHBoxLayout(selected_group);selected_row.setContentsMargins(0,3,6,0);selected_row.setAlignment(Qt.AlignTop);selected_row.setSpacing(10)
        self.selected_icon=QLabel();self.selected_icon.setFixedSize(41,41);selected_row.addWidget(self.selected_icon,0,Qt.AlignTop)
        selected_copy=QVBoxLayout();selected_copy.setSpacing(3)
        self.selected_title=QLabel();self.selected_title.setWordWrap(True);self.selected_title.setObjectName('Heading');selected_copy.addWidget(self.selected_title)
        self.selected_label=QLabel();self.selected_label.setObjectName('Muted');selected_copy.addWidget(self.selected_label)
        selected_copy.addStretch()
        selected_row.addLayout(selected_copy);form.addWidget(selected_group,0,0,3,1)
        self.sound_select=QComboBox();self.sound_select.activated.connect(self._change_sound)
        self.sound_select.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed);self.sound_select.setMinimumWidth(135)
        audio_header=QHBoxLayout();audio_header.addWidget(QLabel('绑定音效'));audio_header.addStretch()
        self.multi_sound_button = QPushButton('多音效…')
        self.multi_sound_button.setObjectName('TextButton')
        self.multi_sound_button.clicked.connect(self.open_sound_binding)
        audio_header.addWidget(self.multi_sound_button)
        self.advanced_button=QPushButton('参数…');self.advanced_button.setObjectName('TextButton');self.advanced_button.clicked.connect(self.open_bound_parameters);audio_header.addWidget(self.advanced_button)
        form.addLayout(audio_header,0,1);form.addWidget(self.sound_select,1,1)
        self.icon_button=QPushButton('选择职业与技能');self.icon_button.clicked.connect(self.open_icon_picker)
        form.addWidget(QLabel('技能图标'),0,2);form.addWidget(self.icon_button,1,2)
        self.key_box=KeyBox('',160);self.key_box.key_changed.connect(self._change_key)
        form.addWidget(QLabel('触发按键'),0,3);form.addWidget(self.key_box,1,3)
        self.volume=QDoubleSpinBox();self.volume.setRange(0,200);self.volume.setSuffix(' %');self.volume.setDecimals(0);self.volume.setFixedWidth(88)
        self.volume.editingFinished.connect(self._change_volume_spin)
        volume_line=QHBoxLayout();volume_line.setSpacing(7);volume_line.addWidget(QLabel('音量'))
        self.volume_slider=VolumeSlider(Qt.Horizontal);self.volume_slider.setRange(0,200);self.volume_slider.valueChanged.connect(self._change_volume_slider)
        self.volume_slider.sliderReleased.connect(self.flush_volume);self.volume_slider.focus_left.connect(self.flush_volume)
        volume_line.addWidget(self.volume_slider,1);volume_line.addWidget(self.volume);form.addLayout(volume_line,2,1)
        clear_icon=QPushButton('清空图标');clear_icon.setObjectName('TextButton');clear_icon.clicked.connect(lambda:self._apply(lambda:self.model.update_slot(self.selected,icon=None),'icon'));form.addWidget(clear_icon,2,2)
        self.audition_button=QPushButton('试听音效');self.audition_button.setObjectName('PrimaryButton');self.audition_button.setIcon(self.audition_icon);self.audition_button.clicked.connect(self.preview_selected);form.addWidget(self.audition_button,2,3)
        ability_row=QHBoxLayout()
        self.ability_toggle=QCheckBox('能力技 · 独立冷却')
        self.ability_toggle.setToolTip('每个能力技固定防连按 1 秒，不占用公共冷却。')
        self.ability_toggle.clicked.connect(self._change_ability);ability_row.addWidget(self.ability_toggle)
        self.ability_source=QLabel();self.ability_source.setObjectName('Muted');ability_row.addWidget(self.ability_source)
        self.ability_auto=QPushButton('恢复自动');self.ability_auto.setObjectName('TextButton')
        self.ability_auto.clicked.connect(lambda:self._change_ability(None));ability_row.addWidget(self.ability_auto)
        ability_row.addStretch()
        self.temporary_gcd_button=QPushButton('临时 GCD…')
        self.temporary_gcd_button.clicked.connect(self.edit_temporary_gcd)
        ability_row.addWidget(self.temporary_gcd_button)
        form.addLayout(ability_row,3,1,1,3)
        form.setColumnStretch(1,1);form.setColumnStretch(2,1);form.setColumnStretch(3,1)
        layout.addWidget(editor);layout.addStretch(1)

    def _change_volume_slider(self,value):
        self.pending_volume=(self.selected,value/100)
        self.volume.blockSignals(True);self.volume.setValue(value);self.volume.blockSignals(False)
        if not self.volume_slider.isSliderDown():self.flush_volume()

    def _change_volume_spin(self):
        self.pending_volume=(self.selected,self.volume.value()/100);self.flush_volume()

    def flush_volume(self):
        if self.pending_volume is None:return True
        index,value=self.pending_volume;self.pending_volume=None
        try:
            if value!=self.model.slots[index].volume:self.model.update_slot(index,volume=value)
        except (OSError,ValueError) as exc:
            self.status.setText('未保存音量：'+str(exc));success=False
        else:self.changed.emit('volume');success=True
        if index==self.selected:
            self.volume.blockSignals(True);self.volume.setValue(self.model.slots[index].volume*100);self.volume.blockSignals(False)
            self.volume_slider.blockSignals(True);self.volume_slider.setValue(round(self.model.slots[index].volume*100));self.volume_slider.blockSignals(False)
        self.refresh_presets();return success

    def refresh_cooldown(self):
        if not self.isVisible():return
        remaining=self.game_audio.remaining() if self.game_audio else 0
        public=(remaining,getattr(self.game_audio,'duration',self.model.cooldown))
        states=[self.game_audio.ability_cooldown(index) if self.game_audio and self.model.slot_is_ability(slot) else public
                for index,slot in enumerate(self.model.slots)]
        cooling=bool(remaining or any(seconds for seconds,_ in states))
        if cooling or self._cooling:
            for grid in (self.grid,self.binding_grid):
                for button,(seconds,duration) in zip(grid.buttons,states):
                    if (button.remaining,button.duration)!=(seconds,duration):
                        button.remaining=seconds;button.duration=duration;button.update()
        self._cooling=cooling

    def set_trigger_state(self,state):
        text,color={
            'inactive':('监听未启用','#a5abae'),
            'editing':('设置中','#a5abae'),
            'paused':('已暂停','#f0a59b'),
            'active':('触发中','#b7e3be'),
            'wheel_only':('仅轮盘触发','#b7e3be'),
        }[state]
        self.ready_label.setText('●  '+text)
        self.ready_label.setStyleSheet('color:'+color)

    def preview_slot(self,index):
        self.stop_preview()
        self.audition_slot(index)

    def preview_selected(self):
        self.audition_slot(self.selected)

    def audition_slot(self, index):
        slot = self.model.slots[index]
        name = slot.sound
        if slot.extra_sounds:
            name = next((name for name in slot.sounds if not self.missing_reference(name)), slot.sound)
        self.preview_entry(name, slot.volume)

    def _build_library(self):
        root = QVBoxLayout(self.library_page)
        root.setContentsMargins(28,25,28,17); root.setSpacing(16)
        header = QHBoxLayout(); label = QLabel('音效库'); label.setObjectName('Heading'); header.addWidget(label)
        header.addStretch();self.bulk_delete=QPushButton('删除选中（0）');self.bulk_delete.clicked.connect(lambda:self.delete_audio(sorted(self.delete_selection)));header.addWidget(self.bulk_delete)
        undo_delete=QPushButton('撤销删除');undo_delete.clicked.connect(self.undo_audio_delete);header.addWidget(undo_delete)
        self.new_combo_button=QPushButton('新建组合');self.new_combo_button.clicked.connect(lambda:self.open_combo_editor());header.addWidget(self.new_combo_button)
        add = QPushButton('导入音效…'); add.clicked.connect(lambda: self.open_import()); header.addWidget(add); root.addLayout(header)
        filters=QHBoxLayout()
        from sound_library_order import SORT_OPTIONS, SoundLibraryOrder
        self.library_order=SoundLibraryOrder(self.sound_root,self)
        self.library_order.durations_changed.connect(self.refresh_duration_order)
        self.sound_search=QLineEdit();self.sound_search.setPlaceholderText('搜索音效名称')
        self.sound_search.setAccessibleName('搜索音效名称');self.sound_search.setClearButtonEnabled(True)
        self.sound_search.textChanged.connect(self.refresh_library);filters.addWidget(self.sound_search,1)
        self.only_unbound=QCheckBox('仅看未绑定');self.only_unbound.toggled.connect(self.refresh_library)
        filters.addWidget(self.only_unbound)
        filters.addWidget(QLabel('排序'))
        self.library_sort=QComboBox()
        self.library_sort.setAccessibleName('音效排序')
        for label,value in SORT_OPTIONS:
            self.library_sort.addItem(label,value)
        self.restore_library_sort()
        self.library_sort.activated.connect(lambda index:self._set_preference('library_sort',self.library_sort.itemData(index)))
        filters.addWidget(self.library_sort);root.addLayout(filters)
        self.binding_panel = QFrame(); self.binding_panel.setObjectName('Binding'); panel = QVBoxLayout(self.binding_panel)
        top = QHBoxLayout(); self.binding_title = QLabel(); self.binding_title.setObjectName('Heading'); top.addWidget(self.binding_title)
        top.addStretch(); self.finish_binding = QPushButton('完成'); self.finish_binding.clicked.connect(self.close_binding); top.addWidget(self.finish_binding); panel.addLayout(top)
        self.binding_grid = SlotGrid(self.model, self.icons,name_resolver=self.slot_sound_label); self.binding_grid.clicked.connect(self._bind_slot); panel.addWidget(self.binding_grid)
        foot = QHBoxLayout(); self.binding_status = QLabel('选择一个技能格。'); foot.addWidget(self.binding_status, 1)
        self.append_binding = QCheckBox('追加到已有绑定')
        foot.addWidget(self.append_binding)
        self.undo_button = QPushButton('撤销上次绑定'); self.undo_button.clicked.connect(self._undo); foot.addWidget(self.undo_button); panel.addLayout(foot)
        root.addWidget(self.binding_panel); self.binding_panel.hide()
        columns=QHBoxLayout()
        for text,stretch in [('绑定技能 / 按键',1),('音效 · 点击试听',1),('操作',0)]:
            label=QLabel(text); label.setObjectName('Muted'); label.setStyleSheet('font-size:11px')
            if not stretch:label.setFixedWidth(94)
            columns.addWidget(label,stretch)
        root.addLayout(columns)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        self.library_holder = QWidget(); self.library_layout = QVBoxLayout(self.library_holder); self.library_layout.setContentsMargins(0,0,6,0); self.library_layout.setSpacing(0); self.library_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.library_holder); root.addWidget(scroll, 1)
        self.bind_buttons={};self.library_preview_buttons={};self.refresh_library()

    def _build_preferences(self):
        from settings_window import KeyBox, MicPage
        root = QVBoxLayout(self.preferences_page)
        root.setContentsMargins(28,25,28,17); root.setSpacing(20)
        heading = QLabel('更多设置'); heading.setObjectName('Heading'); root.addWidget(heading)
        row = QHBoxLayout(); row.addWidget(QLabel('长按呼出技能栏'))
        self.summon_box = KeyBox(self.cfg.get('hotkey','y'),190)
        self.summon_box.key_changed.connect(lambda value: self._set_preference('hotkey', value)); row.addWidget(self.summon_box)
        row.addWidget(QLabel('轻按动作')); self.tap_action = QComboBox()
        for text, value in [('重播上一个音效','repeat_last'),('播放下一个音效','next'),('不执行动作','none')]: self.tap_action.addItem(text,value)
        self.tap_action.setCurrentIndex(max(0,self.tap_action.findData(self.cfg.get('tap_action','repeat_last'))))
        self.tap_action.activated.connect(lambda index: self._set_preference('tap_action',self.tap_action.itemData(index)))
        row.addWidget(self.tap_action); row.addStretch(); root.addLayout(row)
        wheel_row=QHBoxLayout();wheel_row.addWidget(QLabel('轮盘鼠标定位'));self.pointer_mode=QComboBox()
        self.pointer_mode.addItem('跟随鼠标','cursor');self.pointer_mode.addItem('锁鼠标兼容','relative')
        self.pointer_mode.setToolTip('游戏锁定鼠标时可选兼容模式。')
        self.pointer_mode.setCurrentIndex(max(0,self.pointer_mode.findData(self.cfg.get('wheel_pointer_mode','cursor'))))
        self.pointer_mode.activated.connect(lambda i:self._set_preference('wheel_pointer_mode',self.pointer_mode.itemData(i)));wheel_row.addWidget(self.pointer_mode)
        arrange=QPushButton('安排轮盘音效…');arrange.clicked.connect(self.open_wheel_order);wheel_row.addWidget(arrange);wheel_row.addStretch();root.addLayout(wheel_row)
        input_row=QHBoxLayout()
        input_row.addWidget(QLabel('暂停快捷键'))
        self.pause_key_box=KeyBox(self.cfg.get('pause_key',''),190)
        self.pause_key_box.key_changed.connect(lambda key:self._set_preference('pause_key',key))
        input_row.addWidget(self.pause_key_box)
        self.restore_trigger_settings()
        self.restore_topmost()
        self.pause_button=QPushButton('暂停触发');self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(lambda:self.trigger_pause_requested.emit());input_row.addWidget(self.pause_button)
        input_row.addStretch();root.addLayout(input_row)
        export=QPushButton('导出诊断日志…');export.clicked.connect(self.export_logs);root.addWidget(export);root.addStretch()
        audio_root=QVBoxLayout(self.audio_page); audio_root.setContentsMargins(28,25,28,17)
        heading=QLabel('声音输出'); heading.setObjectName('Heading'); audio_root.addWidget(heading)
        self.mic_page = MicPage(self.cfg, self.engine)
        self.mic_page.changed.connect(self.preferences_changed.emit)
        from cable_install_ui import CableInstallPanel
        from virtual_cable import CablePackage
        self.cable_panel=CableInstallPanel(CablePackage(self.resources,self.model.path.parent),on_refresh=lambda:self.mic_page.refresh_devices(),on_select=self.select_cable)
        audio_root.addWidget(self.cable_panel);audio_root.addWidget(self.mic_page, 1)

    def select_cable(self,name):
        self._set_preference('cable_device',name)
        self.mic_page.refresh_devices()
        return self.cfg.get('cable_device')==name

    def _set_preference(self, name, value):
        try:
            if name == 'hotkey':
                if not value or value==self.cfg.get('pause_key') or any(slot.key == value for slot in self.model.slots):
                    raise ValueError('呼出键不能为空，也不能与暂停键或技能键重复。')
            if name=='pause_key' and value:
                from sr_roulette import norm_spec
                value=canonical_key(value)
                reserved={norm_spec(self.cfg.get(key,'')) for key in ('hotkey','repeat_last_key','cycle_key')}
                if value in reserved or value in self.model.used_keys():
                    raise ValueError('暂停键不能与呼出键、播放快捷键或套装中的技能键重复。')
            candidate = {**self.cfg, name:value}
            if self.preferences_writer: self.preferences_writer(candidate)
            self.cfg.update(candidate)
            if name=='repeat_accel_enabled':self.changed.emit('acceleration')
            elif name=='wheel_pointer_mode':self.changed.emit('wheel')
            elif name=='always_on_top':self.restore_topmost()
            elif name in ('wheel_only','pause_key'):
                self.restore_trigger_settings()
                self.changed.emit('input')
            elif name=='library_sort':
                self.restore_library_sort()
                self.refresh_library()
            else:self.preferences_changed.emit()
        except (OSError, ValueError) as exc:
            self.summon_box.set_key(self.cfg.get('hotkey','y'))
            self.tap_action.setCurrentIndex(max(0,self.tap_action.findData(self.cfg.get('tap_action','repeat_last'))))
            self.restore_repeat_switch()
            self.restore_pointer_mode()
            self.restore_trigger_settings()
            self.restore_topmost()
            self.restore_library_sort()
            self.status.setText(str(exc))

    def restore_trigger_settings(self):
        wheel_only=self.cfg.get('wheel_only',False)
        self.wheel_only.setChecked(wheel_only)
        self.tap_action.setEnabled(not wheel_only)
        self.pause_key_box.set_key(self.cfg.get('pause_key',''))

    def restore_topmost(self):
        enabled = self.cfg.get('always_on_top') is True
        self.always_on_top.setChecked(enabled)
        flag = Qt.WindowStaysOnTopHint
        if bool(self.windowFlags() & flag) != enabled:
            visible, state = self.isVisible(), self.windowState()
            self.setWindowFlag(flag, enabled)
            self.setWindowState(state)
            if visible:
                self.show()

    def restore_library_sort(self):
        index=self.library_sort.findData(self.cfg.get('library_sort','name'))
        self.library_sort.setCurrentIndex(max(0,index))

    def refresh_duration_order(self):
        if self.library_sort.currentData() in ('duration_asc','duration_desc'):
            self.refresh_library()

    def restore_repeat_switch(self):
        self.repeat_accel.blockSignals(True);self.repeat_accel.setChecked(self.cfg.get('repeat_accel_enabled') is True);self.repeat_accel.blockSignals(False)

    def restore_pointer_mode(self):
        self.pointer_mode.setCurrentIndex(max(0,self.pointer_mode.findData(self.cfg.get('wheel_pointer_mode','cursor'))))

    def open_wheel_order(self):
        if self.wheel_dialog is not None:self.wheel_dialog.raise_();return
        from wheel_settings_ui import WheelOrderDialog
        self.stop_preview();dialog=WheelOrderDialog(self);self.wheel_dialog=dialog
        def release(_):self.wheel_dialog=None;dialog.deleteLater()
        dialog.finished.connect(release);dialog.open()

    def restore_preferences(self):
        from settings_window import MicPage
        self.restore_repeat_switch()
        self.restore_pointer_mode()
        self.restore_trigger_settings()
        self.restore_topmost()
        self.restore_library_sort()
        self.summon_box.set_key(self.cfg.get('hotkey','y'))
        self.tap_action.setCurrentIndex(max(0,self.tap_action.findData(self.cfg.get('tap_action','repeat_last'))))
        old=self.mic_page; old._timer.stop()
        self.mic_page=MicPage(self.cfg,self.engine)
        self.mic_page.changed.connect(self.preferences_changed.emit)
        self.audio_page.layout().replaceWidget(old,self.mic_page)
        old.hide(); old.deleteLater()
        if self.engine and not self.cfg.get('mic_enabled',False):self.engine.release_capture()

    def _change_cooldown(self):
        self._apply(lambda: self.model.set_cooldown(self.cooldown.value()), 'cooldown')
        self.cooldown.setValue(self.model.cooldown)

    def _change_key(self, value):
        if value and value in reserved_trigger_keys(self.cfg):
            self.status.setText('这个按键已用于呼出轮盘或暂停触发。'); self.key_box.set_key(self.model.slots[self.selected].key); return
        self._apply(lambda: self.model.update_slot(self.selected, key=value), 'key')

    def _change_sound(self, index):
        self._apply(lambda: self.model.bind(self.selected,self.sound_select.itemData(index)), 'sound')

    def slot_sound_label(self, slot):
        return slot_sound_label(slot, self.effects)

    def open_sound_binding(self):
        index = self.selected

        def save_binding(names, mode):
            slot = self.model.slots[index]
            if names == slot.sounds and (len(names) < 2 or mode == slot.sound_mode):
                return True
            return self._apply(lambda: self.model.bind_sounds(index, names, mode), 'sound')

        dialog = SoundBindingDialog(self, index, save_binding)
        dialog.exec()
        dialog.deleteLater()

    def open_bound_parameters(self):
        slot = self.model.slots[self.selected]
        if not slot.extra_sounds:
            self.open_sound_parameters()
            return
        menu = QMenu(self.advanced_button)
        for name in slot.sounds:
            action = menu.addAction(self.sound_label(name))
            action.setData(name)
        action = menu.exec(self.advanced_button.mapToGlobal(self.advanced_button.rect().bottomLeft()))
        if action is not None:
            self.open_sound_parameters(action.data())
        menu.deleteLater()

    def _change_ability(self,enabled):
        if not self._apply(lambda:self.model.update_slot(self.selected,ability=enabled),'ability'):
            self.refresh_editor()

    def edit_temporary_gcd(self):
        index = self.selected
        slot = self.model.slots[index]
        dialog = QDialog(self)
        dialog.setWindowTitle(f'{slot_location(index)} · 临时 GCD')
        form = QFormLayout(dialog)
        enabled = QCheckBox('按下此格绑定键时启用')
        enabled.setChecked(slot.temporary_gcd is not None)
        form.addRow(enabled)
        gcd = QDoubleSpinBox()
        gcd.setRange(.1, 60)
        gcd.setSuffix(' 秒')
        gcd.setValue(slot.temporary_gcd if slot.temporary_gcd is not None else self.model.cooldown)
        duration = QDoubleSpinBox()
        duration.setRange(.1, 600)
        duration.setSuffix(' 秒')
        duration.setValue(slot.temporary_duration)
        for field in (gcd, duration):
            field.setEnabled(enabled.isChecked())
            enabled.toggled.connect(field.setEnabled)
        form.addRow('临时公共冷却', gcd)
        form.addRow('持续时间', duration)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('保存')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.Accepted:
            self._apply(lambda: self.model.update_slot(index,
                        temporary_gcd=gcd.value() if enabled.isChecked() else None,
                        temporary_duration=duration.value()), 'temporary_gcd')
        dialog.deleteLater()

    def _apply(self, action, reason):
        if not self.flush_volume():return False
        try:
            action()
        except (OSError, ValueError) as exc:
            self.status.setText('未保存：'+str(exc)); self.refresh(); return False
        self.refresh(); self.changed.emit(reason); return True

    def change_page(self, page):
        if not self.flush_volume():return
        self.stop_preview()
        self.pages.setCurrentWidget(page)
        for button, candidate in self.nav_buttons: button.setChecked(candidate is page)
        if page is self.library_page: self.refresh_library()

    def show_library(self):
        self.change_page(self.library_page)

    def select_slot(self, index):
        if not self.flush_volume():return
        self.selected = index; self.refresh_editor(); self.grid.refresh(selected=index)

    def refresh_editor(self):
        slot = self.model.slots[self.selected]
        self.selected_title.setText(f'{slot_location(self.selected)} · {key_label(slot.key) or "未设键"}')
        missing = sum(self.missing_reference(name) for name in slot.sounds)
        self.selected_label.setText((f'{missing} 个音效缺失' if slot.extra_sounds else '音效缺失') if missing else '')
        self.selected_label.setVisible(bool(missing))
        art=self.icons.pixmap(slot.icon)
        if not art.isNull():self.selected_icon.setPixmap(art.scaled(41,41,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        else:self.selected_icon.clear();self.selected_icon.setText('＋')
        self.key_box.set_key(slot.key);self.volume.setValue(slot.volume*100)
        self.volume_slider.blockSignals(True);self.volume_slider.setValue(round(slot.volume*100));self.volume_slider.blockSignals(False)
        self.icon_button.setIcon(QIcon(self.icons.pixmap(slot.icon)))
        self.icon_button.setText('更换技能图标' if slot.icon else '选择职业与技能')
        self.ability_toggle.setChecked(self.model.slot_is_ability(slot))
        self.temporary_gcd_button.setText('临时 GCD…' if slot.temporary_gcd is None
                                         else f'临时 GCD {slot.temporary_gcd:g} 秒…')
        self.ability_auto.setVisible(slot.ability is not None)
        self.ability_source.setText('手动设置' if slot.ability is not None else
                                    '已按图标识别' if slot.icon in self.icons.action_types else '图标类型未识别')
        self.sound_select.blockSignals(True)
        self.sound_select.clear()
        self.sound_select.setEnabled(not slot.extra_sounds)
        if slot.extra_sounds:
            self.sound_select.addItem(self.slot_sound_label(slot))
            self.sound_select.setToolTip('点「多音效…」编辑列表和播放方式。')
        else:
            self.sound_select.setToolTip('')
            self.sound_select.addItem('未设置音效', None)
            for name, label in self.library_items():
                self.sound_select.addItem(label, name)
            if slot.sound and self.sound_select.findData(slot.sound) < 0:
                self.sound_select.addItem(self.sound_label(slot.sound) + '（缺失）', slot.sound)
            self.sound_select.setCurrentIndex(max(0, self.sound_select.findData(slot.sound)))
        self.sound_select.blockSignals(False)
        self.audition_button.setToolTip('试听列表中的首个可用音效。' if slot.extra_sounds else '')

    def refresh(self):
        self.refresh_presets();self.cooldown.setValue(self.model.cooldown)
        self.grid.refresh(selected=self.selected); self.refresh_editor(); self.refresh_library()

    def sound_files(self):
        return sorted((p for p in self.sound_root.rglob('*') if p.is_file() and p.resolve().is_relative_to(self.sound_root.resolve()) and p.suffix.lower() in ('.wav','.mp3','.ogg','.flac','.m4a') and not any(part.startswith('.') for part in p.relative_to(self.sound_root).parts)),key=lambda p:str(p).lower())

    def bound_indices(self, sound):
        return [i for i,slot in enumerate(self.model.slots) if sound in slot.sounds]

    def refresh_library(self):
        while self.library_layout.count():
            widget = self.library_layout.takeAt(0).widget()
            if widget: widget.hide(); widget.deleteLater()
        self.bind_buttons={};self.library_preview_buttons={}
        existing={p.relative_to(self.sound_root).as_posix() for p in self.sound_files()};self.delete_selection.intersection_update(existing)
        self.bulk_delete.setText(f'删除选中（{len(self.delete_selection)}）')
        query=self.sound_search.text().strip().casefold()
        items=[(name,label) for name,label in self.library_items()
               if query in label.casefold() and (not self.only_unbound.isChecked() or not self.bound_indices(name))]
        for name,label,duration in self.library_order.sorted_items(items,self.library_sort.currentData()):
            bound=self.bound_indices(name)
            row = QFrame(); row.setObjectName('SoundRow'); line = QHBoxLayout(row); line.setContentsMargins(8,10,8,10); line.setSpacing(13)
            if not is_combo_reference(name):
                check=QCheckBox();check.setAccessibleName('选择 '+label);check.setChecked(name in self.delete_selection);check.toggled.connect(lambda on,n=name:self.set_delete_selected(n,on));line.addWidget(check)
            bindings_holder=QWidget(); bindings_holder.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
            icons = QGridLayout(bindings_holder); icons.setContentsMargins(0,0,0,0); icons.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
            for position,index in enumerate(bound):
                chip = QToolButton(); chip.setObjectName('BoundSkill'); chip.setText(key_label(self.model.slots[index].key) or '无按键')
                chip.setIcon(QIcon(self.icons.pixmap(self.model.slots[index].icon))); chip.setIconSize(QSize(30,30)); chip.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                chip.setToolTip(slot_location(index))
                chip.clicked.connect(lambda checked=False,i=index: self._edit_bound(i)); icons.addWidget(chip,position//4,position%4)
            if not bound:
                empty_label = QLabel('未绑定'); empty_label.setObjectName('Muted'); icons.addWidget(empty_label,0,0)
            line.addWidget(bindings_holder, 1)
            play=QPushButton();play.setFixedWidth(42)
            play.clicked.connect(lambda checked=False,n=name:self.preview_entry(n));line.addWidget(play)
            self.library_preview_buttons[name]=play
            title=QLabel(self.fontMetrics().elidedText(label,Qt.ElideRight,210))
            title.setToolTip(label);title.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
            title.setMinimumWidth(90);line.addWidget(title,1)
            if duration is not None:
                time_label=QLabel(f'{duration:.2f} 秒');time_label.setObjectName('Muted')
                line.addWidget(time_label)
            actions=QToolButton();actions.setText('⋯');actions.setAccessibleName(label+'的更多操作')
            menu=QMenu(actions);actions.setMenu(menu);actions.setPopupMode(QToolButton.InstantPopup)
            menu.addAction('编辑组合' if is_combo_reference(name) else '参数',lambda checked=False,n=name:self.open_sound_parameters(n))
            if is_combo_reference(name):
                menu.addAction('删除',lambda checked=False,n=name:self.delete_combo(n))
            else:
                menu.addAction('删除',lambda checked=False,n=name:self.delete_audio([n]))
            line.addWidget(actions)
            bind = QPushButton('正在绑定' if self.binding_sound==name else '绑定'); bind.setObjectName('BindButton'); bind.setFixedWidth(94); bind.setCheckable(True); bind.setChecked(self.binding_sound==name)
            bind.clicked.connect(lambda checked=False,n=name: self.start_binding(n)); line.addWidget(bind)
            self.bind_buttons[name] = bind; self.library_layout.addWidget(row)
        self.sync_library_preview()
        if not self.bind_buttons:
            self.library_layout.addWidget(QLabel('没有符合条件的音效' if query or self.only_unbound.isChecked() else '音效库为空'))
        if self.binding_sound:
            self.binding_grid.refresh(matching=self.binding_sound)
        self.undo_button.setEnabled(self.model.last_binding is not None)

    def sync_library_preview(self):
        for name,button in getattr(self,'library_preview_buttons',{}).items():
            active=name==self.preview_path
            button.setText('■' if active else '▶')
            action='停止试听' if active else '试听'
            button.setAccessibleName(f'{action} {self.sound_label(name)}')
            button.setToolTip(action)

    def clear_preview_entry(self):
        self.preview_path=None
        self.sync_library_preview()

    def on_preview_media_status(self,status):
        if status in (QMediaPlayer.EndOfMedia,QMediaPlayer.InvalidMedia):
            self.clear_preview_entry()

    def _edit_bound(self,index):
        self.change_page(self.bar_page); self.select_slot(index)

    def preview_sound(self,path):
        self.preview_entry(Path(path).relative_to(self.sound_root).as_posix())

    def start_binding(self, sound):
        self.stop_preview(); self.binding_sound=sound; self.model.last_binding=None
        self.binding_title.setText('音效：'+self.sound_label(sound))
        self.binding_status.setText('点击技能格立即绑定。'); self.binding_panel.show(); self.refresh_library()

    def close_binding(self):
        self.binding_sound=None; self.binding_panel.hide(); self.model.last_binding=None; self.refresh_library()

    def _bind_slot(self,index):
        if not self.binding_sound: return
        slot = self.model.slots[index]
        append = self.append_binding.isChecked()
        names = slot.sounds if append else ()
        if self.binding_sound in names or slot.sounds == (self.binding_sound,):
            self.binding_status.setText('这个技能已经绑定此音效。')
            return
        if self._apply(lambda: self.model.bind_sounds(index, (*names, self.binding_sound), slot.sound_mode), 'sound'):
            key = key_label(slot.key) or '无按键格'
            detail = '，已追加到列表' if append and names else f'，替换「{self.slot_sound_label(slot)}」' if slot.sounds else ''
            self.binding_status.setText(f'已绑定到 {key}{detail}。')

    def _undo(self):
        if self._apply(self.model.undo,'sound'): self.binding_status.setText('已撤销上次绑定。')

    def open_icon_picker(self):
        target=self.selected
        self.icon_picker=IconPicker(self.icons,self)
        self.icon_picker.chosen.connect(lambda name:self._apply(lambda:self.model.update_slot(target,icon=name),'icon'))
        self.icon_picker.open()

    def open_import(self, paths=None):
        from sound_import_ui import SoundImportDialog, FILE_FILTER
        if self.import_dialog is not None:
            return
        if paths is None: paths=choose_audio_files(self,'导入音效',FILE_FILTER)
        if not paths: return
        dialog=SoundImportDialog(self.sound_root,paths,self); self.import_dialog=dialog
        dialog.library_changed.connect(lambda count:(self.refresh(),self.changed.emit('sound')))
        def release(result):
            self.import_dialog=None; dialog.deleteLater()
        dialog.finished.connect(release); dialog.open()

    def open_screenshot(self,path=None):
        from screenshot_ui import ScreenshotImportDialog
        if self.screenshot_dialog is not None:return
        dialog=ScreenshotImportDialog(self.model,self.icons,reserved_trigger_keys(self.cfg),self)
        self.screenshot_dialog=dialog
        def applied():
            self.refresh();self.changed.emit('key')
            self.status.setText('截图已导入；按图标识别能力技。带问号的格子可手动补正，音效和音量保持原设置。')
        def release(result):
            self.screenshot_dialog=None;dialog.deleteLater()
        dialog.applied.connect(applied);dialog.finished.connect(release)
        if path is not None:dialog.load_path(path)
        dialog.open()

    def dragEnterEvent(self,event):
        if any(url.isLocalFile() for url in event.mimeData().urls()): event.acceptProposedAction()

    def dropEvent(self,event):
        paths=[Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths: self.open_import(paths); event.acceptProposedAction()

    def capture_screen(self):
        from screen_capture_ui import begin_capture
        begin_capture(self)

    def ask_close_action(self):
        from PySide6.QtWidgets import QMessageBox
        dialog=QMessageBox(self);dialog.setWindowTitle('关闭程序');dialog.setText('完全退出，还是继续在后台响应技能按键？')
        quit_button=dialog.addButton('完全退出',QMessageBox.DestructiveRole)
        background=dialog.addButton('留在后台',QMessageBox.AcceptRole)
        cancel=dialog.addButton('取消',QMessageBox.RejectRole);dialog.setDefaultButton(background);dialog.exec()
        return 'quit' if dialog.clickedButton() is quit_button else 'background' if dialog.clickedButton() is background else 'cancel'

    def request_close(self):
        action=self.ask_close_action()
        if action=='cancel':return
        if self.close() and action=='quit':self.quit_requested.emit()

    def closeEvent(self,event):
        if not self.flush_volume():event.ignore();return
        if self.screenshot_dialog is not None and self.screenshot_dialog.worker is not None:
            self.status.setText('请先完成或取消截图识别。');event.ignore();return
        if self.import_dialog is not None and self.import_dialog.is_importing():
            self.status.setText('请先完成或取消当前音效导入。'); event.ignore(); return
        self.audition.stop(wait=True); self.mic_page._timer.stop()
        if self.engine and not self.cfg.get('mic_enabled',False):self.engine.release_capture()
        self.closed.emit(); event.accept()
