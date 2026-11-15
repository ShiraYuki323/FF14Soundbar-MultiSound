"""Draft ordering of existing skill slots, without changing their key bindings."""
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QPushButton,QDialogButtonBox
from wheel_geometry import validate_order,DEFAULT_ORDER,PAGE_SIZE
from skillbar_model import key_label,slot_location
from ui_theme import STYLE,dark_palette


class WheelOrderDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.setWindowTitle('安排轮盘音效');self.setPalette(dark_palette());self.setStyleSheet(STYLE);self.resize(540,610)
        try:self.order=validate_order(window.cfg.get('wheel_order',DEFAULT_ORDER))
        except ValueError:self.order=list(DEFAULT_ORDER)
        root=QVBoxLayout(self);root.setSpacing(12)
        self.list=QListWidget();self.list.setIconSize(QSize(32,32));root.addWidget(self.list,1)
        self.list.setToolTip('轮盘顺序由所有套装共用。')
        buttons=QHBoxLayout()
        for text,action in [('上移',lambda:self.move_row(-1)),('下移',lambda:self.move_row(1)),('恢复技能栏顺序',self.restore)]:
            button=QPushButton(text);button.clicked.connect(action);buttons.addWidget(button)
        root.addLayout(buttons);self.feedback=QLabel();self.feedback.setWordWrap(True);root.addWidget(self.feedback)
        bb=QDialogButtonBox();bb.addButton('取消',QDialogButtonBox.RejectRole);bb.addButton('保存顺序',QDialogButtonBox.AcceptRole)
        bb.rejected.connect(self.reject);bb.accepted.connect(self.save_changes);root.addWidget(bb);self.refresh()

    def refresh(self,selected=0):
        self.list.clear();directions=['上','右上','右','右下','下','左下','左','左上']
        for position,index in enumerate(self.order):
            slot=self.window.model.slots[index];name=self.window.sound_label(slot.sound)
            item=QListWidgetItem(QIcon(self.window.icons.pixmap(slot.icon)),f'第{position//PAGE_SIZE+1}页 · {directions[position%PAGE_SIZE]}　{key_label(slot.key) or "未设键"}　{name}')
            item.setToolTip(f'{slot_location(index)} · {name}');self.list.addItem(item)
        self.list.setCurrentRow(selected)

    def move_row(self,delta):
        row=self.list.currentRow();target=row+delta
        if 0<=row<len(self.order) and 0<=target<len(self.order):self.order[row],self.order[target]=self.order[target],self.order[row];self.refresh(target)

    def restore(self):self.order=list(DEFAULT_ORDER);self.refresh()

    def save_changes(self):
        try:
            order=validate_order(self.order);candidate={**self.window.cfg,'wheel_order':order}
            if self.window.preferences_writer:self.window.preferences_writer(candidate)
        except (ValueError,OSError) as exc:self.feedback.setText('未保存：'+str(exc));return
        self.window.cfg.update(candidate);self.window.changed.emit('wheel');self.accept()
