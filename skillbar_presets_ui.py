"""Named preset controls and explicit protection of unsaved working edits."""
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QPushButton,QComboBox,QMenu,QMessageBox,QInputDialog
from skillbar_model import contained_path,reserved_trigger_keys


class PresetActions:
    def build_preset_controls(self):
        holder=QWidget();line=QHBoxLayout(holder);line.setContentsMargins(0,0,0,0);line.setSpacing(8)
        label=QLabel('当前套装');label.setObjectName('Muted');line.addWidget(label)
        self.preset_combo=QComboBox();self.preset_combo.setMinimumWidth(170);self.preset_combo.setMaximumWidth(250)
        self.preset_combo.activated.connect(lambda index:self.switch_preset(self.preset_combo.itemData(index)))
        line.addWidget(self.preset_combo,1)
        self.save_preset_button=QPushButton('保存套装');self.save_preset_button.setObjectName('PrimaryButton')
        self.save_preset_button.clicked.connect(self.save_current_preset);line.addWidget(self.save_preset_button)
        self.save_as_button=QPushButton('另存为…');self.save_as_button.clicked.connect(lambda:self.name_preset('copy'));line.addWidget(self.save_as_button)
        self.preset_manage=QPushButton('管理');menu=QMenu(self.preset_manage)
        menu.addAction('新建空白套装…',lambda:self.name_preset('new'))
        menu.addAction('重命名当前套装…',lambda:self.name_preset('rename'))
        self.delete_preset_action=menu.addAction('删除当前套装…',self.delete_current_preset)
        self.preset_manage.setMenu(menu);line.addWidget(self.preset_manage)
        line.addStretch();self.preset_state=QLabel();self.preset_state.setObjectName('PresetState');line.addWidget(self.preset_state)
        self.refresh_presets();return holder

    def refresh_presets(self):
        if not hasattr(self,'preset_combo'):return
        self.preset_combo.blockSignals(True);self.preset_combo.clear()
        for identity,entry in self.model.presets.items():
            text=entry['name']+('  *' if identity==self.model.active_preset and self.model.dirty else '')
            self.preset_combo.addItem(text,identity)
        self.preset_combo.setCurrentIndex(self.preset_combo.findData(self.model.active_preset));self.preset_combo.blockSignals(False)
        self.preset_state.setText('● 有未保存修改' if self.model.dirty else '● 已保存' if self.model.presets_persisted else '● 待首次保存')
        self.preset_state.setToolTip('修改已保留在工作副本；点击保存套装更新快照。' if self.model.dirty else '当前配置与保存的套装一致。')
        self.save_preset_button.setEnabled(self.model.dirty or not self.model.presets_persisted)
        self.delete_preset_action.setEnabled(len(self.model.presets)>1)

    def ask_unsaved(self):
        dialog=QMessageBox(self);dialog.setWindowTitle('保存当前套装？')
        dialog.setText('「'+self.model.preset_name+'」有尚未保存到套装的修改。')
        dialog.setInformativeText('保存后切换，或放弃这些修改并继续。取消会留在当前套装。')
        save=dialog.addButton('保存并继续',QMessageBox.AcceptRole)
        discard=dialog.addButton('放弃修改',QMessageBox.DestructiveRole)
        dialog.addButton('取消',QMessageBox.RejectRole);dialog.setDefaultButton(save);dialog.exec()
        return 'save' if dialog.clickedButton() is save else 'discard' if dialog.clickedButton() is discard else 'cancel'

    def resolve_unsaved(self):
        if not self.flush_volume():return False
        if not self.model.dirty:return True
        answer=self.ask_unsaved()
        if answer=='cancel':self.refresh_presets();return False
        if answer=='save':
            try:self.model.save_preset()
            except (OSError,ValueError) as exc:self.status.setText('未保存：'+str(exc));self.refresh_presets();return False
        return True

    def save_current_preset(self):
        if self._apply(self.model.save_preset,'preset_save'):self.status.setText('已保存套装：'+self.model.preset_name)

    def finish_preset_change(self):
        self.stop_preview();self.close_binding();self.refresh();self.changed.emit('preset')
        missing={slot.sound for slot in self.model.slots if slot.sound and self.missing_reference(slot.sound)}
        text='已切换套装：'+self.model.preset_name
        if missing:text+=f' · {len(missing)} 个音效文件缺失，绑定已保留，可重新导入。'
        self.status.setText(text)

    def switch_preset(self,identity):
        if identity==self.model.active_preset:return
        if not self.resolve_unsaved():return
        try:self.model.activate_preset(identity,reserved_trigger_keys(self.cfg))
        except (OSError,ValueError) as exc:self.status.setText('未切换：'+str(exc));self.refresh_presets();return
        self.finish_preset_change()

    def name_preset(self,mode):
        if not self.flush_volume():return
        title={'copy':'另存为套装','new':'新建空白套装','rename':'重命名套装'}[mode]
        name,ok=QInputDialog.getText(self,title,'套装名称（最多40字）：',text=self.model.preset_name if mode=='rename' else '')
        if not ok:return
        # Validate names before any save/discard decision has side effects.
        try:
            name=self.model._preset_name(name)
            if any(entry['name'].casefold()==name.casefold() and (mode!='rename' or identity!=self.model.active_preset) for identity,entry in self.model.presets.items()):
                raise ValueError('套装名称重复，请使用其他名称。')
        except ValueError as exc:self.status.setText(str(exc));return
        if mode=='new' and not self.resolve_unsaved():return
        try:
            if mode=='copy':self.model.save_as(name)
            elif mode=='new':self.model.new_preset(name,reserved_trigger_keys(self.cfg))
            else:self.model.rename_preset(self.model.active_preset,name)
        except (OSError,ValueError) as exc:self.status.setText('未保存：'+str(exc));self.refresh_presets();return
        if mode=='new':self.finish_preset_change()
        else:self.refresh();self.status.setText('已'+('另存为：' if mode=='copy' else '重命名为：')+self.model.preset_name)

    def delete_current_preset(self):
        if len(self.model.presets)==1:return
        dialog=QMessageBox(self);dialog.setWindowTitle('删除套装')
        dialog.setText('删除「'+self.model.preset_name+'」？音效文件会保留。')
        delete=dialog.addButton('删除套装',QMessageBox.DestructiveRole);cancel=dialog.addButton('取消',QMessageBox.RejectRole)
        dialog.setDefaultButton(cancel);dialog.exec()
        if dialog.clickedButton() is not delete or not self.resolve_unsaved():return
        try:self.model.delete_preset(self.model.active_preset,reserved_trigger_keys(self.cfg))
        except (OSError,ValueError) as exc:self.status.setText('未删除：'+str(exc));return
        self.finish_preset_change()
