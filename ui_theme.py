"""Shared FF14 palette, including Qt popup windows and detached item views."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QFileDialog
from pathlib import Path

THEME_VERSION=3


STYLE = '''
QWidget { color:#e8e7e2; font-family:"Microsoft YaHei UI"; font-size:12px; }
QWidget#FF14Root { background:#202326; border:1px solid #5c6062; }
QFrame#Title { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #383c3f,stop:1 #292d30); border-bottom:1px solid #121517; border-top:1px solid #747879; }
QLabel#Brand { color:#cbbb94; font-family:Georgia; font-size:22px; padding-right:14px; border-right:1px solid #60615b; }
QLabel#WindowTitle { font-size:18px; color:#e8e7e2; }
QLabel#Eyebrow { color:#a5abae; font-size:10px; }
QFrame#SideNav { background:#222629; border-right:1px solid #3b4043; }
QPushButton#NavButton { text-align:left; background:transparent; border:1px solid transparent; padding:10px 10px; color:#adb3b5; }
QPushButton#NavButton:hover { background:#30383c; }
QPushButton#NavButton:checked { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #494941,stop:1 #343a3c); border-color:#626257; border-left:2px solid #d9c898; color:#f0e5cb; }
QFrame#Binding { background:#252e32; border:1px solid #92917d; border-radius:6px; }
QFrame#CableInstaller { background:#272e32; border:1px solid #68716a; border-radius:5px; }
QLabel#InstallerNote { color:#a9b4b4; font-size:10px; }
QLabel#CableFeedback { color:#decfa7; font-size:11px; }
QFrame#Editor { background:transparent; border-top:1px solid #43494b; }
QLabel#Heading { color:#e5e1d5; font-size:16px; }
QLabel#Muted { color:#a5abae; }
QLabel#BarHint { color:#a5abae; font-size:11px; }
QLabel#PresetState { color:#cbbb94; font-size:10px; }
QLabel#Ready { color:#b6c2ae; font-size:11px; }
QFrame#CooldownStrip { background:transparent; border-top:1px solid #3b4245; }
QLabel#Status { color:#99a5aa; background:#1c2023; border-top:1px solid #3e4649; padding:9px 18px; font-size:10px; }
QPushButton { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #41494c,stop:1 #30373a); border:1px solid #687174; border-radius:4px; padding:7px 12px; min-height:18px; }
QPushButton:hover { background:#4a5557; border-color:#b9ac87; }
QPushButton:checked { background:#55594d; border-color:#c3b68d; color:#f2e6c7; }
QPushButton:disabled { color:#849399; border-color:#465156; background:#283238; }
QPushButton#PrimaryButton { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #55584e,stop:1 #3a403b); border-color:#94917d; color:#f2ead4; }
QPushButton#PrimaryButton:hover { background:#5a6053; border-color:#d8c99d; }
QPushButton#PrimaryButton:disabled { background:#303632; border-color:#4e5850; color:#869187; }
QPushButton#TextButton { background:transparent; border:0; color:#bcae85; padding:2px 0; font-size:11px; text-align:left; }
QPushButton#TextButton:hover { color:#f2dfac; }
QPushButton#MakerLink { color:#e7d8ae; background:transparent; border:1px solid transparent; padding:3px 6px; text-decoration:underline; }
QPushButton#MakerLink:hover,QPushButton#MakerLink:focus { background:#454947; border-color:#9a8c68; color:#fff2c9; }
QToolButton#SkillChoice { background:transparent; border:1px solid transparent; padding:4px; }
QToolButton#SkillChoice:hover { border-color:#cbbb94; background:#343a3c; }
QSlider::groove:horizontal { height:4px; background:#151a1c; border:1px solid #485154; border-radius:2px; }
QSlider::sub-page:horizontal { background:#a99e7b; border-radius:2px; }
QSlider::handle:horizontal { background:#d4c59d; border:1px solid #e9dfc5; width:10px; margin:-4px 0; border-radius:5px; }
QPushButton#KeyClear { padding:0; min-height:0; min-width:0; background:#273238; color:#cbbb94; font-size:14px; }
QPushButton#WindowControl,QPushButton#WindowClose { padding:0; min-height:0; background:transparent; border:0; font-size:15px; color:#bec5c3; }
QPushButton#WindowControl:hover { background:#4b5355; color:#fff1d4; }
QPushButton#WindowClose:hover { background:#8c4540; color:#ffffff; }
QFrame#Footer { background:#1c2023; }
QToolButton { background:#2c373c; border:1px solid #58676d; border-radius:4px; color:#e2e2d5; padding:3px; }
QToolButton:hover { border-color:#c9bb95; background:#414c4d; }
QToolButton#BoundSkill { background:transparent; border:0; padding:4px 3px; font-size:11px; }
QToolButton#BoundSkill:hover { background:#343f44; }
QFrame#SoundRow { background:transparent; border-bottom:1px solid #3c484e; }
QPushButton#AuditionButton { background:transparent; border:1px solid transparent; text-align:left; padding:9px 6px; font-size:13px; min-height:28px; }
QPushButton#AuditionButton:hover { background:#343f44; border-color:#596a70; }
QPushButton#BindButton { font-size:11px; padding:6px 8px; }
QComboBox,QDoubleSpinBox,QSpinBox,QLineEdit,QTextEdit,QPlainTextEdit { background:#1a1f22; color:#e8e7e2; border:1px solid #50595c; border-radius:3px; padding:6px; selection-background-color:#55594d; selection-color:#fff0d0; }
QComboBox { padding-right:28px; combobox-popup:0; }
QAbstractSpinBox QLineEdit { border:0; padding:0; background:transparent; }
QComboBox::drop-down { width:24px; border-left:1px solid #4f5d63; border-top-right-radius:3px; border-bottom-right-radius:3px; }
QComboBox::down-arrow { image:url("@UI_DIR@/chevron-down.xpm"); width:9px; height:5px; }
QSpinBox::up-button,QDoubleSpinBox::up-button { subcontrol-origin:border; subcontrol-position:top right; width:18px; background:#2a353b; border-left:1px solid #4f5d63; }
QSpinBox::down-button,QDoubleSpinBox::down-button { subcontrol-origin:border; subcontrol-position:bottom right; width:18px; background:#2a353b; border-left:1px solid #4f5d63; }
QSpinBox::up-arrow,QDoubleSpinBox::up-arrow { image:url("@UI_DIR@/chevron-up.xpm"); width:9px; height:5px; }
QSpinBox::down-arrow,QDoubleSpinBox::down-arrow { image:url("@UI_DIR@/chevron-down.xpm"); width:9px; height:5px; }
QComboBox QAbstractItemView { background:#1b2429; alternate-background-color:#232e33; color:#e8e7e2; border:1px solid #69767b; selection-background-color:#55594d; selection-color:#fff0d0; outline:0; padding:3px; }
QComboBox QAbstractItemView::item { min-height:27px; padding:4px 7px; }
QAbstractItemView,QListView,QTreeView,QTableView,QTableWidget { background:#1b2429; alternate-background-color:#232e33; color:#e8e7e2; border:1px solid #4b5a61; selection-background-color:#4d554b; selection-color:#fff0d0; gridline-color:#465157; }
QAbstractItemView::item:selected { background:#4d554b; color:#fff0d0; }
QHeaderView::section { background:#394348; color:#dbd7c7; border:0; border-right:1px solid #4d5a60; padding:7px; }
QTableCornerButton::section { background:#394348; border:0; }
QScrollArea,QScrollArea>QWidget>QWidget { background:transparent; border:0; }
QDialog,QFileDialog,QMessageBox { background:#252c30; color:#e8e7e2; }
QMenu { background:#252e33; color:#e8e7e2; border:1px solid #68777c; padding:5px; }
QMenu::item { padding:7px 24px 7px 14px; border-radius:3px; }
QMenu::item:selected { background:#55594d; color:#fff0d0; }
QMenu::item:disabled { color:#819096; }
QMenu::separator { height:1px; background:#4c595f; margin:5px 8px; }
QToolTip { background:#263137; color:#eee4c8; border:1px solid #8f927d; padding:6px; }
QProgressBar { background:#1b2529; color:#dce0d5; border:1px solid #536167; border-radius:3px; text-align:center; }
QProgressBar::chunk { background:#8c876c; }
QScrollBar:vertical { background:#1d262b; width:11px; margin:0; }
QScrollBar::handle:vertical { background:#647176; border-radius:4px; min-height:28px; margin:2px; }
QScrollBar::handle:vertical:hover { background:#8c9694; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QScrollBar:horizontal { background:#1d262b; height:11px; margin:0; }
QScrollBar::handle:horizontal { background:#647176; border-radius:4px; min-width:28px; margin:2px; }
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width:0; }
QCheckBox,QRadioButton,QLabel { background:transparent; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #687477; border-radius:3px; background:#1a1f22; }
QCheckBox::indicator:hover { border-color:#d2c49c; }
QCheckBox::indicator:checked { background:#b9ac87; border-color:#d8cba7; image:url("@UI_DIR@/check.xpm"); }
QCheckBox::indicator:disabled { background:#283238; border-color:#465156; }
'''.replace('@UI_DIR@',(Path(__file__).resolve().parent/'assets'/'ui').as_posix())


def dark_palette():
    palette=QPalette()
    colors={
        QPalette.Window:'#252c30',QPalette.WindowText:'#e8e7e2',
        QPalette.Base:'#1b2429',QPalette.AlternateBase:'#232e33',QPalette.Text:'#e8e7e2',
        QPalette.Button:'#3a454a',QPalette.ButtonText:'#e8e7e2',
        QPalette.Highlight:'#55594d',QPalette.HighlightedText:'#fff0d0',
        QPalette.ToolTipBase:'#263137',QPalette.ToolTipText:'#eee4c8',
        QPalette.Light:'#718084',QPalette.Midlight:'#535f64',QPalette.Mid:'#3c494f',
        QPalette.Dark:'#151d21',QPalette.Shadow:'#11171a',QPalette.Link:'#d5c69e',
        QPalette.PlaceholderText:'#8f9da3',
    }
    for role,color in colors.items():palette.setColor(role,QColor(color))
    for role in (QPalette.Text,QPalette.WindowText,QPalette.ButtonText):
        palette.setColor(QPalette.Disabled,role,QColor('#849399'))
    return palette


def apply_theme(app=None):
    app=app or QApplication.instance()
    if app is not None:
        app.setStyle('Fusion')
        app.setPalette(dark_palette())
        app.setStyleSheet(STYLE)


def choose_audio_files(parent,caption,file_filter):
    paths,_=QFileDialog.getOpenFileNames(parent,caption,'',file_filter)
    return paths
