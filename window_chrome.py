"""A native draggable header so the app does not gain a second OS title bar."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame


class WindowHeader(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName('Title');self.drag_offset=None

    def toggle_maximized(self):
        window=self.window()
        if window.isMaximized():window.showNormal()
        else:window.showMaximized()

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            handle=self.window().windowHandle()
            if handle and handle.startSystemMove():return
            if not self.window().isMaximized():self.drag_offset=event.globalPosition().toPoint()-self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self,event):
        if self.drag_offset is not None and event.buttons()&Qt.LeftButton:
            self.window().move(event.globalPosition().toPoint()-self.drag_offset)

    def mouseReleaseEvent(self,event):self.drag_offset=None

    def mouseDoubleClickEvent(self,event):
        self.drag_offset=None
        if event.button()==Qt.LeftButton:self.toggle_maximized()
