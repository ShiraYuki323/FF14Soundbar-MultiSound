"""Screenshot selection, cancellable offline recognition and visual-only review."""
from dataclasses import replace
from functools import partial
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt,QRectF,QThread,Signal
from PySide6.QtGui import QImage,QImageReader,QPainter,QPen,QColor,QPixmap
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QMenu,QPushButton,QFileDialog

from screenshot_import import analyze_screenshot,RecognitionCancelled
from skillbar_model import (SkillSlot,canonical_key,key_label,reserved_key_set,slot_location,
                            DISPLAY_ORDER,LEGACY_SLOTS,SLOT_COUNT,COLUMNS)
from skillbar_ui import SlotGrid,IconPicker
from ui_theme import STYLE,dark_palette


REVIEW_BADGE='font-size:12px;font-weight:bold;border-radius:3px;'
PENDING_BADGE=REVIEW_BADGE+'color:#fff1c9;background:#693b1b;border:1px solid #edac61;'
CONFIRMED_BADGE=REVIEW_BADGE+'color:#c7eed6;background:#243e33;border:1px solid #57806a;'


class ScreenshotCanvas(QWidget):
    region_changed=Signal(object)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.image=QImage();self.region=None;self.cells=[];self.anchor=None
        self.setMinimumHeight(190);self.setCursor(Qt.CrossCursor)

    def target(self):
        if self.image.isNull():return QRectF()
        scale=min(self.width()/self.image.width(),self.height()/self.image.height())
        w=self.image.width()*scale;h=self.image.height()*scale
        return QRectF((self.width()-w)/2,(self.height()-h)/2,w,h)

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#141c21'))
        target=self.target()
        if target.isEmpty():
            painter.setPen(QColor('#a5b3b9'));painter.drawText(self.rect(),Qt.AlignCenter,'选择游戏截图 · 支持 PNG / JPG / BMP');return
        painter.drawImage(target,self.image)
        scale=target.width()/self.image.width()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#dbc58d"),1.5))
        for x,y,w,h in self.cells:
            painter.drawRect(QRectF(target.x()+x*scale,target.y()+y*scale,w*scale,h*scale))
        if self.region:
            x,y,w,h=self.region;painter.setPen(QPen(QColor('#80d7dc'),2,Qt.DashLine))
            painter.drawRect(QRectF(target.x()+x*scale,target.y()+y*scale,w*scale,h*scale))

    def image_point(self,point):
        target=self.target()
        if target.isEmpty():return None
        scale=self.image.width()/target.width()
        return (min(self.image.width(),max(0,(point.x()-target.x())*scale)),
                min(self.image.height(),max(0,(point.y()-target.y())*scale)))

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.target().contains(event.position()):
            self.anchor=self.image_point(event.position())

    def mouseMoveEvent(self,event):
        if self.anchor:
            end=self.image_point(event.position());x,y=self.anchor
            self.region=(round(min(x,end[0])),round(min(y,end[1])),round(abs(x-end[0])),round(abs(y-end[1])))
            self.update()

    def mouseReleaseEvent(self,event):
        if self.anchor:
            self.mouseMoveEvent(event);self.anchor=None
            if self.region and min(self.region[2:])>10:self.region_changed.emit(self.region)
            else:self.region=None
            self.update()


class RecognitionWorker(QThread):
    ready=Signal(object)
    failed=Signal(str)
    progress=Signal(str)

    def __init__(self,path,icons,region,parent=None,analyzer=analyze_screenshot):
        super().__init__(parent);self.path=path;self.icons=icons;self.region=region;self.analyzer=analyzer

    def run(self):
        try:
            result=self.analyzer(self.path,self.icons,self.region,self.isInterruptionRequested,self.progress.emit)
            if not self.isInterruptionRequested():self.ready.emit(result)
        except RecognitionCancelled:pass
        except Exception as exc:self.failed.emit('识别失败：'+str(exc))


class ScreenshotImportDialog(QDialog):
    applied=Signal()

    def __init__(self,model,icons,reserved_key='y',parent=None):
        super().__init__(parent)
        from settings_window import KeyBox
        self.model,self.icons,self.reserved_keys=model,icons,reserved_key_set(reserved_key)
        self.path=None;self.worker=None;self.close_pending=False;self.visuals=[];self.selected=0;self.picker=None
        self.visual_by_slot={}
        self.preview=SimpleNamespace(slots=[SkillSlot() for _ in range(SLOT_COUNT)],review={},slot_is_ability=model.slot_is_ability)
        self.setWindowTitle('截图导入 · 确认技能与按键');self.setModal(True)
        self.setPalette(dark_palette());self.setStyleSheet(STYLE);self.resize(1040,840);self.setMinimumSize(980,680)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,20,24,18);layout.setSpacing(10)
        heading=QLabel('截图识别');heading.setObjectName('Heading');layout.addWidget(heading)
        toolbar=QHBoxLayout()
        self.choose_button=QPushButton('选择截图…');self.choose_button.clicked.connect(self.choose_image);toolbar.addWidget(self.choose_button)
        self.auto_button=QPushButton('清空');self.auto_button.clicked.connect(self.reset_region);toolbar.addWidget(self.auto_button)
        self.auto_button.setToolTip('清空框选和本次识别结果')
        toolbar.addStretch();self.start_button=QPushButton('开始识别');self.start_button.setEnabled(False);self.start_button.clicked.connect(self.start);toolbar.addWidget(self.start_button)
        layout.addLayout(toolbar)
        self.canvas=ScreenshotCanvas();self.canvas.region_changed.connect(self.region_changed);layout.addWidget(self.canvas,1)
        self.canvas.setToolTip('可拖动框选最下面三排技能栏。')
        review_row=QHBoxLayout()
        self.summary=QLabel();review_row.addWidget(self.summary,1)
        self.next_review_button=QPushButton('下一个待确认')
        self.next_review_button.setEnabled(False)
        self.next_review_button.clicked.connect(self.select_next_review)
        review_row.addWidget(self.next_review_button)
        layout.addLayout(review_row)
        self.grid=SlotGrid(self.preview,icons,name_resolver=lambda _: '');self.grid.clicked.connect(self.select_slot);self.grid.setEnabled(False);layout.addWidget(self.grid)
        for label in self.grid.labels:label.setFixedHeight(20)
        editor=QHBoxLayout();self.location=QLabel('选择格子补正');editor.addWidget(self.location)
        self.key_box=KeyBox('',160);self.key_box.key_changed.connect(self.change_key);editor.addWidget(self.key_box)
        self.icon_button=QPushButton('选择职业与技能');self.icon_button.clicked.connect(self.choose_icon);editor.addWidget(self.icon_button)
        self.clear_icon_button=QPushButton('图标留空');self.clear_icon_button.clicked.connect(lambda:self.change_icon(None));editor.addWidget(self.clear_icon_button)
        self.fill_row_button=QPushButton('填充整排')
        menu=QMenu(self.fill_row_button)
        for label,prefix in [('1 到 =',''),('Ctrl＋1 到 =','ctrl+'),('Alt＋1 到 =','alt+'),('Shift＋1 到 =','shift+')]:
            menu.addAction(label,partial(self.fill_row,prefix))
        self.fill_row_button.setMenu(menu);self.fill_row_button.hide();editor.addWidget(self.fill_row_button)
        editor.addStretch();layout.addLayout(editor)
        review_keys=QHBoxLayout()
        self.key_image_label=QLabel('截图中的技能')
        self.key_image_label.setObjectName('Muted')
        self.key_image_label.hide()
        review_keys.addWidget(self.key_image_label)
        self.key_image=QLabel();self.key_image.setAccessibleName('截图中的技能和按键');self.key_image.hide()
        review_keys.addWidget(self.key_image)
        self.key_options_label=QLabel('点击确认候选')
        self.key_options_label.setObjectName('Muted')
        self.key_options_label.hide()
        review_keys.addWidget(self.key_options_label)
        self.key_options=[]
        for _ in range(2):
            button=QPushButton()
            button.clicked.connect(lambda checked=False,b=button:self.change_key(b.property('key')))
            button.hide();review_keys.addWidget(button);self.key_options.append(button)
        review_keys.addStretch();layout.addLayout(review_keys)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        footer=QHBoxLayout();footer.addStretch();self.apply_button=QPushButton('确认导入');self.apply_button.setEnabled(False);self.apply_button.clicked.connect(self.apply_result)
        self.cancel_button=QPushButton('取消');self.cancel_button.clicked.connect(self.reject);footer.addWidget(self.cancel_button);footer.addWidget(self.apply_button);layout.addLayout(footer)
        self.set_editor_enabled(False)

    def set_editor_enabled(self,on):
        for widget in (self.key_box,self.icon_button,self.clear_icon_button):widget.setEnabled(on)

    def choose_image(self):
        path,_=QFileDialog.getOpenFileName(self,'选择技能栏截图','','截图 (*.png *.jpg *.jpeg *.bmp)')
        if path:self.load_path(Path(path))

    def load_path(self,path):
        reader=QImageReader(str(path));size=reader.size()
        if size.width()<=0 or size.height()<=0 or size.width()*size.height()>32_000_000:
            self.status.setText('无法读取截图，或图片超过 3200 万像素。');return False
        image=reader.read()
        if image.isNull():self.status.setText('截图已损坏或格式不受支持。');return False
        self.path=Path(path);self.canvas.image=image;self.canvas.region=None;self.canvas.cells=[]
        self.clear_result();self.start_button.setEnabled(True);self.canvas.update()
        self.status.setText('已选择 '+self.path.name+'，可以开始识别。');return True

    def clear_result(self):
        self.visuals=[];self.visual_by_slot={};self.preview.slots=[SkillSlot() for _ in range(SLOT_COUNT)];self.preview.review={}
        self.location.setText('选择格子补正')
        self.key_box.set_key('')
        self.apply_button.setText('确认导入')
        self.refresh_grid();self.grid.setEnabled(False);self.apply_button.setEnabled(False);self.set_editor_enabled(False)
        self.summary.setText('等待识别。')
        self.show_key_review(None)
        self.fill_row_button.hide()

    def reset_region(self):
        self.canvas.region=None;self.canvas.cells=[]
        self.canvas.update();self.clear_result()
        self.status.setText('将从整张截图识别技能栏。')

    def region_changed(self,region):
        self.canvas.cells=[]
        self.clear_result()
        self.status.setText('框选完成，请点击「开始识别」。')

    def start(self):
        if self.worker or self.path is None:return
        self.clear_result()
        self.close_pending=False
        self.worker=RecognitionWorker(self.path,self.icons,self.canvas.region,self)
        self.worker.ready.connect(self.set_analysis)
        self.worker.failed.connect(self.status.setText)
        import logging
        self.worker.failed.connect(lambda message:logging.getLogger('ff14').error('Recognition: %s',message))
        self.worker.progress.connect(self.status.setText);self.worker.finished.connect(self.worker_finished)
        for control in (self.choose_button,self.auto_button,self.start_button,self.canvas,self.grid):
            control.setEnabled(False)
        self.cancel_button.setText('取消识别');self.worker.start()

    def worker_finished(self):
        worker=self.worker;self.worker=None;worker.deleteLater()
        for control in (self.choose_button,self.auto_button,self.start_button,self.canvas):
            control.setEnabled(True)
        self.grid.setEnabled(bool(self.visuals))
        self.cancel_button.setText('取消')
        if self.close_pending:super().reject()

    def set_analysis(self,result):
        if self.close_pending:return
        count=len(result.visuals)
        if count not in (LEGACY_SLOTS,SLOT_COUNT):
            self.status.setText('格子数量错误，请重新识别。');return
        self.visuals=[replace(value) for value in result.visuals]
        self.visual_by_slot=dict(zip(DISPLAY_ORDER[-count:],self.visuals))
        retained_keys={slot.key for i,slot in enumerate(self.model.slots) if i not in self.visual_by_slot and slot.key}
        for visual in self.visuals:
            if visual.key and canonical_key(visual.key) in self.reserved_keys|retained_keys:
                visual.key='';visual.review=tuple(dict.fromkeys((*visual.review,'key')))
            if visual.icon and visual.icon not in self.icons.files:
                visual.icon=None;visual.review=tuple(dict.fromkeys((*visual.review,'icon')))
        self.selected=next((i for i,v in self.visual_by_slot.items() if v.review),next(iter(self.visual_by_slot)))
        self.canvas.cells=result.cells;self.canvas.update();self.sync_preview()
        self.grid.setEnabled(True)
        self.apply_button.setText(f'确认导入 {count//COLUMNS} 排')
        self.set_editor_enabled(True);self.select_slot(self.selected)
        self.status.setText(result.warning or ('' if self.apply_button.isEnabled() else '没有可导入的图标或键位，请重新识别或手动补录。'))

    def show_key_review(self,visual):
        pending=visual is not None and 'key' in visual.review
        rect=visual.source_rect if pending else None
        show_image=bool(rect and min(rect[2:])>0 and not self.canvas.image.isNull())
        self.key_image_label.setVisible(show_image)
        self.key_image.setVisible(show_image)
        if show_image:
            fragment=self.canvas.image.copy(*rect)
            self.key_image.setPixmap(QPixmap.fromImage(fragment).scaledToHeight(70,Qt.SmoothTransformation))
        options=visual.key_candidates if pending else ()
        self.key_options_label.setVisible(bool(options))
        for i,button in enumerate(self.key_options):
            button.setVisible(i<len(options))
            if i<len(options):
                button.setProperty('key',options[i])
                button.setText(key_label(options[i]))

    def fill_row(self,prefix):
        row=DISPLAY_ORDER.index(self.selected)//COLUMNS
        indices=DISPLAY_ORDER[row*COLUMNS:(row+1)*COLUMNS]
        if not all(i in self.visual_by_slot for i in indices):
            return
        keys=[prefix+key for key in '1234567890-=']
        used=self.reserved_keys | {slot.key for i,slot in enumerate(self.preview.slots) if i not in indices and slot.key}
        if used.intersection(keys):
            self.status.setText('这组键位与其他排、轮盘键或暂停键冲突。')
            return
        for index,key in zip(indices,keys):
            visual=self.visual_by_slot[index]
            visual.key=key
            visual.review=tuple(field for field in visual.review if field!='key')
        self.sync_preview()
        self.select_slot(self.selected)
        self.status.setText('当前排键位已填充。')

    def sync_preview(self):
        self.apply_button.setEnabled(any(visual.icon or visual.key for visual in self.visuals))
        self.preview.slots=[replace(slot,sound=None) for slot in self.model.slots]
        for index,visual in self.visual_by_slot.items():
            self.preview.slots[index]=self.preview.slots[index].with_changes(key=visual.key,icon=visual.icon)
        self.preview.review={i:v.review for i,v in self.visual_by_slot.items() if v.review}
        self.refresh_grid()
        count=f'{len(self.visuals)//COLUMNS} 排'
        self.summary.setText(
            f'{count} · 键位待确认 {sum("key" in v.review for v in self.visuals)} 格 · '
            f'图标待确认 {sum("icon" in v.review for v in self.visuals)} 格 · '
            f'能力技 {sum(self.model.slot_is_ability(self.preview.slots[i]) for i in self.visual_by_slot)} 格'
        )

    def refresh_grid(self):
        self.grid.refresh(selected=self.selected if self.visuals else -1)
        self.next_review_button.setEnabled(any(i!=self.selected and v.review for i,v in self.visual_by_slot.items()))
        for index,label in enumerate(self.grid.labels):
            self.grid.buttons[index].setEnabled(index in self.visual_by_slot)
            if not self.visuals:
                label.setStyleSheet('');label.setAccessibleName('')
                continue
            visual=self.visual_by_slot.get(index)
            if visual is None:
                label.setText('保留');label.setStyleSheet('color:#a5abae')
                label.setAccessibleName('保留原设置');label.setToolTip('保留原设置')
                continue
            if 'key' in visual.review:
                text='待确认';detail='键位待确认，请选择这格录入键位'
            elif 'icon' in visual.review:
                text='图标待核';detail='图标待确认；键位已确认：'+(key_label(visual.key) or '留空')
            else:
                text='已确认';detail='键位已确认：'+(key_label(visual.key) or '留空')
            if 'key' in visual.review and 'icon' in visual.review:detail+='；图标也待确认'
            label.setText(text);label.setToolTip(detail);label.setAccessibleName(detail)
            style=PENDING_BADGE if visual.review else CONFIRMED_BADGE
            if label.styleSheet()!=style:label.setStyleSheet(style)

    def select_slot(self,index):
        if index not in self.visual_by_slot:return
        self.selected=index;self.key_box.set_key(self.visual_by_slot[index].key)
        self.location.setText(slot_location(index))
        self.show_key_review(self.visual_by_slot[index])
        row=DISPLAY_ORDER.index(index)//COLUMNS
        self.fill_row_button.setVisible(all(i in self.visual_by_slot for i in DISPLAY_ORDER[row*COLUMNS:(row+1)*COLUMNS]))
        self.refresh_grid()

    def select_next_review(self):
        indices=tuple(self.visual_by_slot)
        if not indices:return
        current=indices.index(self.selected)
        for index in indices[current+1:]+indices[:current]:
            if self.visual_by_slot[index].review:
                self.select_slot(index)
                return

    def change_key(self,key):
        if not self.visuals:return
        try:
            key=canonical_key(key)
            if key and key in self.reserved_keys:raise ValueError('这个按键已用于呼出轮盘或暂停触发。')
            if key and any(i!=self.selected and slot.key==key for i,slot in enumerate(self.preview.slots)):raise ValueError('这个按键已在其他格子中使用。')
        except ValueError as exc:
            self.status.setText(str(exc));self.key_box.set_key(self.visual_by_slot[self.selected].key);return
        visual=self.visual_by_slot[self.selected];visual.key=key;visual.review=tuple(v for v in visual.review if v!='key')
        self.sync_preview();self.select_slot(self.selected);self.status.setText('键位已补正：'+(key_label(key) or '留空'))

    def choose_icon(self):
        if not self.visuals:return
        target=self.selected;self.picker=IconPicker(self.icons,self)
        self.picker.chosen.connect(lambda name:self.change_icon(name,target));self.picker.open()

    def change_icon(self,name,index=None):
        if not self.visuals:return
        index=self.selected if index is None else index
        if name is not None and name not in self.icons.files:return
        visual=self.visual_by_slot.get(index)
        if visual is None:return
        visual.icon=name;visual.review=tuple(v for v in visual.review if v!='icon')
        self.sync_preview();self.status.setText('图标已补正。' if name else '此格图标将留空。')

    def apply_result(self):
        if self.worker or not any(visual.icon or visual.key for visual in self.visuals):return
        try:self.model.apply_visuals(self.visuals,self.reserved_keys)
        except (ValueError,OSError) as exc:self.status.setText('未保存：'+str(exc));return
        self.applied.emit();self.accept()

    def reject(self):
        if self.worker:
            self.close_pending=True;self.worker.requestInterruption();self.status.setText('正在取消识别…');self.cancel_button.setEnabled(False)
        else:super().reject()

    def closeEvent(self,event):
        if self.worker:self.reject();event.ignore()
        else:super().closeEvent(event)
