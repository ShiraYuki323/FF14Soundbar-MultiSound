"""Library deletion confirmation and user-requested diagnostic export."""
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QMessageBox,QFileDialog,QDialog
from sound_deletion import SoundTrash
from diagnostics import export_diagnostics

class LibraryManagement:
    def set_delete_selected(self,name,on):
        if on:self.delete_selection.add(name)
        else:self.delete_selection.discard(name)
        self.bulk_delete.setText(f'删除选中（{len(self.delete_selection)}）')
    def confirm_delete_audio(self,names):
        dialog=QMessageBox(self);dialog.setWindowTitle('删除音效')
        rows=[]
        for name in names:
            current = len(self.bound_indices(name))
            presets = sum(
                any(slot.get('sound') == name or name in slot.get('extra_sounds', ()) for slot in entry['slots'])
                for entry in self.model.presets.values()
            )
            combos=sum(any(item.sound==name for item in combo.items) for combo in self.effects.combos.values())
            rows.append(f'{self.sound_label(name)}：当前{current}格 / {presets}套装 / {combos}组合')
        dialog.setText(f'将 {len(names)} 个音效移入本地回收区？');dialog.setDetailedText('\n'.join(rows))
        dialog.setInformativeText('绑定引用会保留并成为缺失音效，可通过“撤销删除”恢复。\n'+'\n'.join(rows[:5]))
        remove=dialog.addButton('删除音效',QMessageBox.DestructiveRole);cancel=dialog.addButton('取消',QMessageBox.RejectRole);dialog.setDefaultButton(cancel);dialog.exec()
        return dialog.clickedButton() is remove
    def delete_audio(self,names):
        names=list(names)
        if not names:self.status.setText('请先勾选要删除的音效。');return
        if not self.confirm_delete_audio(names):return
        self.stop_preview()
        try:SoundTrash(self.sound_root).delete(names)
        except (OSError,ValueError) as exc:self.status.setText('未删除：'+str(exc));logging.getLogger('ff14').exception('Audio delete failed');return
        self.delete_selection.difference_update(names)
        if self.binding_sound in names:self.binding_sound=None;self.binding_panel.hide()
        self.refresh();self.changed.emit('sound');self.status.setText(f'已删除{len(names)}个音效，可撤销。');logging.getLogger('ff14').info('Deleted %d audio files',len(names))
    def undo_audio_delete(self):
        try:SoundTrash(self.sound_root).undo()
        except (OSError,ValueError) as exc:self.status.setText('未恢复：'+str(exc));return
        self.refresh();self.changed.emit('sound');self.status.setText('已恢复上次删除的音效。')
    def export_logs(self):
        documents=QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        dialog=QFileDialog(self,'导出诊断日志',documents,'ZIP 压缩包 (*.zip)')
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setDefaultSuffix('zip')
        dialog.selectFile(datetime.now().strftime('FF14诊断日志_%Y%m%d_%H%M%S.zip'))
        try:
            if dialog.exec()!=QDialog.Accepted:
                return
            paths=dialog.selectedFiles()
            if not paths:
                return
            destination=Path(paths[0])
            try:
                export_diagnostics(self.model.path.parent,destination)
            except (OSError, ValueError) as exc:
                logging.getLogger('ff14').exception('Diagnostic export failed')
                self.status.setText('日志导出失败')
                QMessageBox.warning(self,'日志导出失败',f'{exc}\n\n保存位置 {destination}')
                return
            self.status.setText(f'已导出 {destination.name}')
            self.status.setToolTip(str(destination))
        finally:
            dialog.deleteLater()
