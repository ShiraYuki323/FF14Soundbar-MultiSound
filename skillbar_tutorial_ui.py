"""Short in-app guide to the normal soundbar setup and gameplay flow."""
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget


SECTIONS = (
    ('01  导入或设置技能栏',
     '在「技能栏」点击「截图并识别」，或用「截图导入」打开已有截图。'
     '可框选完整的两排或三排技能栏后开始识别。'
     '点待确认格可对照截图中的技能图标和按键，选择候选键位或手动补录。'),
    ('02  绑定并试听音效',
     '在「音效库」点 ▶ 试听，点「绑定」后选择一个或多个技能格。'
     '也可以选中技能格，在「绑定音效」下拉框里选择，双击技能格可试听。用「导入音效」添加自己的文件。'
     '音效库可按名称、导入时间或时长排序。'),
    ('03  游戏内触发',
     '程序在前台和后台都支持按键触发。录入快捷键、输入文字或打开设置对话框时会暂时停止触发。'
     '普通技能共用公共冷却，默认 2.5 秒。青色「能」标记能力技，各格单独防连按 1 秒。'
     '选中技能格可设置「临时 GCD」，按下绑定键触发，计时结束后恢复。'
     '长按轮盘键后移动鼠标选择，滚轮切页，松手播放。呼出键、轻按动作和暂停键都可以在「更多设置」调整。'),
    ('04  暂停与保存套装',
     '在「技能栏」开启「窗口置顶」，可把主窗口保持在其他普通窗口上方。'
     '开启「只播放轮盘音效」，可仅通过轮盘选中并松手播放。首页、托盘和暂停快捷键都能暂停或恢复。'
     '调整好键位、图标和音效后点「保存套装」，也可以「另存为」给其他职业使用。'),
    ('05  把音效送进语音',
     '只想自己听时，选择耳机作为本地输出。使用 VB-CABLE 时，在「声音输出」选择 CABLE Input，'
     '在游戏或语音软件中选择 CABLE Output 作为麦克风。如需同时说话，在「声音输出」里开启麦克风并选择真实设备。'),
)


def build_tutorial(parent):
    page = QScrollArea(parent)
    page.setWidgetResizable(True)
    content = QWidget()
    page.setWidget(content)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(28, 25, 28, 24)
    layout.setSpacing(9)
    heading = QLabel('使用教程')
    heading.setObjectName('WindowTitle')
    layout.addWidget(heading)
    for title, instructions in SECTIONS:
        layout.addSpacing(8)
        label = QLabel(title)
        label.setObjectName('Heading')
        layout.addWidget(label)
        text = QLabel(instructions)
        text.setWordWrap(True)
        layout.addWidget(text)
    layout.addStretch()
    return page
