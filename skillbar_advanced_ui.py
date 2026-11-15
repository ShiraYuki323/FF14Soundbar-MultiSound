"""Native library actions shared by the skill editor and library page."""
from PySide6.QtWidgets import QMessageBox
from skillbar_model import sound_label,is_combo_reference,contained_path


class AdvancedActions:
    def sound_label(self,name):return sound_label(name,self.effects)

    def library_items(self):
        return [(p.relative_to(self.sound_root).as_posix(),p.stem) for p in self.sound_files()]+[
            ('combo::'+c.cid,'◆ '+c.name) for c in self.effects.combos.values()]

    def missing_reference(self,name):
        if is_combo_reference(name):return self.effects.combo_of(name) is None
        path=contained_path(self.sound_root,name);return path is None or not path.is_file()

    def stop_preview(self):
        self.clear_preview_entry()
        if hasattr(self,'audition'):self.audition.stop()
        else:self.player.stop()

    def preview_entry(self,name,gain_scale=1):
        if not name or self.missing_reference(name):
            self.status.setText('此音效缺失，请重新导入或选择其他音效。');return
        if self.preview_path==name:
            self.stop_preview();return
        self.preview_path=name
        if is_combo_reference(name):job={'kind':'combo','combo':self.effects.combo_of(name),'gain_scale':gain_scale}
        else:job={'kind':'sound','name':name,'gain_scale':gain_scale}
        self.audition.request(job)
        self.sync_library_preview()

    def library_saved(self):
        self.stop_preview();self.refresh();self.changed.emit('library');self.status.setText('已保存音效库参数；所有使用此音效的套装均已更新。')

    def open_sound_parameters(self,name=None):
        name=name or self.model.slots[self.selected].sound
        if not name:self.status.setText('请先绑定一个音效。');return
        if is_combo_reference(name):
            if not self.missing_reference(name):self.open_combo_editor(name[7:])
            else:self.status.setText('组合已删除，请重新选择绑定。')
            return
        if self.sound_dialog is not None:self.sound_dialog.raise_();return
        from advanced_audio_ui import SoundParametersDialog
        self.stop_preview();dialog=SoundParametersDialog(self.library_settings,name,self.audition,self);self.sound_dialog=dialog
        dialog.saved.connect(self.library_saved)
        def release(_):self.sound_dialog=None;dialog.deleteLater()
        dialog.finished.connect(release);dialog.open()

    def open_combo_editor(self,identity=None):
        if self.combo_dialog is not None:self.combo_dialog.raise_();return
        from advanced_audio_ui import NativeComboDialog
        self.stop_preview();dialog=NativeComboDialog(self.library_settings,self.audition,identity,self);self.combo_dialog=dialog
        dialog.saved.connect(self.library_saved)
        def release(_):self.combo_dialog=None;dialog.deleteLater()
        dialog.finished.connect(release);dialog.open()

    def delete_combo(self,name):
        identity=name[7:];dialog=QMessageBox(self);dialog.setWindowTitle('删除组合')
        dialog.setText('删除「'+self.sound_label(name)+'」？');dialog.setInformativeText('原音效文件保留。已有技能格与套装会显示组合缺失，直到重新绑定。')
        remove=dialog.addButton('删除组合',QMessageBox.DestructiveRole);cancel=dialog.addButton('取消',QMessageBox.RejectRole);dialog.setDefaultButton(cancel);dialog.exec()
        if dialog.clickedButton() is not remove:return
        try:self.library_settings.delete_combo(identity)
        except (ValueError,OSError) as exc:self.status.setText('未删除：'+str(exc));return
        self.library_saved()
