"""Dispose test-owned windows while QApplication is still alive."""
import gc
from PySide6.QtCore import QCoreApplication, QEvent


def close_test_windows(app):
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    gc.collect()
