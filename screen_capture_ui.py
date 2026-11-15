"""User-initiated region capture. Offscreen never reads the real desktop."""
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt,QRect,QTimer
from PySide6.QtGui import QCursor,QPainter,QColor,QPen
from PySide6.QtWidgets import QApplication,QDialog

class RegionCapture(QDialog):
    def __init__(self,image,geometry,parent=None):
        super().__init__(parent,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint)
        self.image=image;self.region=QRect();self.anchor=None;self.setGeometry(geometry);self.setCursor(Qt.CrossCursor)
    def paintEvent(self,event):
        p=QPainter(self);p.drawImage(self.rect(),self.image);p.fillRect(self.rect(),QColor(0,0,0,75))
        if not self.region.isEmpty():
            p.save();p.setClipRect(self.region);p.drawImage(self.rect(),self.image);p.restore();p.setPen(QPen(QColor('#ecd69a'),2));p.drawRect(self.region)
        p.setPen(QColor('white'));p.drawText(self.rect().adjusted(20,20,-20,-20),Qt.AlignTop|Qt.AlignHCenter,'拖动框选技能栏，松手识别 · Esc 取消')
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:self.anchor=event.position().toPoint()
        elif event.button()==Qt.RightButton:self.reject()
    def mouseMoveEvent(self,event):
        if self.anchor is not None:self.region=QRect(self.anchor,event.position().toPoint()).normalized().intersected(self.rect());self.update()
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.anchor is not None:
            self.mouseMoveEvent(event);self.anchor=None
            if self.region.width()>=12 and self.region.height()>=12:self.accept()
    def cropped_image(self):
        sx=self.image.width()/self.width();sy=self.image.height()/self.height();r=self.region
        return self.image.copy(QRect(round(r.x()*sx),round(r.y()*sy),round(r.width()*sx),round(r.height()*sy)))

def begin_capture(window,provider=None):
    if window.screenshot_dialog is not None or window.capture_pending:return
    app=QApplication.instance()
    if provider is None and app.platformName()=='offscreen':window.status.setText('离屏检查禁止截取真实桌面。');return
    screen=app.screenAt(QCursor.pos()) or app.primaryScreen();window.capture_pending=True;window.hide()
    def capture():
        if window.shutting_down:return
        try:
            image,geometry=provider() if provider else (screen.grabWindow(0).toImage(),screen.geometry())
            if image.isNull():raise ValueError('无法读取屏幕，请改用游戏截图导入。')
            selector=RegionCapture(image,geometry,window);window.region_capture=selector
            def finished(result):
                window.region_capture=None;window.capture_pending=False
                if window.shutting_down:selector.deleteLater();return
                window.show();window.raise_();window.activateWindow()
                if result==QDialog.Accepted:
                    if window.capture_temp:window.capture_temp.cleanup()
                    window.capture_temp=tempfile.TemporaryDirectory(prefix='ff14-capture-')
                    path=Path(window.capture_temp.name)/'技能栏截图.png'
                    if selector.cropped_image().save(str(path)):
                        window.open_screenshot(path)
                        if window.screenshot_dialog and window.screenshot_dialog.path:window.screenshot_dialog.start()
                    else:window.status.setText('截图保存失败，请重试。')
                selector.deleteLater()
            selector.finished.connect(finished);selector.open()
        except Exception as exc:window.capture_pending=False;window.show();window.status.setText('截图失败：'+str(exc))
    QTimer.singleShot(300,capture)
