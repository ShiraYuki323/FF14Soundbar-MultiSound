"""Optional original VB-CABLE installer, explicit user actions and honest status."""
from PySide6.QtCore import QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton
from virtual_cable import detect_cable,start_install,InstallerCancelled,InstallerUntracked,OFFICIAL_URL,LICENSE_URL,SUPPORT_URL


def qt_audio_names():
    return ([device.description() for device in QMediaDevices.audioOutputs()],
            [device.description() for device in QMediaDevices.audioInputs()])


class CableInstallPanel(QFrame):
    def __init__(self,package,parent=None,*,device_provider=qt_audio_names,start_fn=start_install,on_refresh=None,on_select=None):
        super().__init__(parent)
        self.setObjectName('CableInstaller');self.package=package;self.device_provider=device_provider;self.start_fn=start_fn
        self.on_refresh=on_refresh;self.on_select=on_select;self.process=None;self.tracking_lost=False;self.prepared=None
        self.bundle_ok=self.package.available();self.device_status=detect_cable([],[])
        layout=QVBoxLayout(self);layout.setContentsMargins(14,12,14,12);layout.setSpacing(8)
        title=QLabel('虚拟声卡安装 · VB-CABLE');title.setObjectName('Heading');layout.addWidget(title)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();row.setSpacing(8)
        self.install_button=QPushButton('安装虚拟声卡…');self.install_button.setObjectName('PrimaryButton');self.install_button.clicked.connect(self.install_clicked);row.addWidget(self.install_button)
        self.refresh_button=QPushButton('重新检测');self.refresh_button.clicked.connect(lambda:self.refresh_status(True));row.addWidget(self.refresh_button)
        self.use_button=QPushButton('选用此声卡');self.use_button.clicked.connect(self.use_cable);row.addWidget(self.use_button);row.addStretch()
        layout.addLayout(row)
        self.feedback=QLabel();self.feedback.setWordWrap(True);self.feedback.setObjectName('CableFeedback');self.feedback.hide();layout.addWidget(self.feedback)
        help_text=QLabel('Windows 会请求管理员授权。在官方安装器点击 Install Driver，完成后重启电脑。\n本程序选 CABLE Input，游戏／语音软件的麦克风选 CABLE Output；系统默认设备保留自己的耳机和麦克风。')
        help_text.setObjectName('InstallerNote');help_text.setWordWrap(True);layout.addWidget(help_text)
        credits=QHBoxLayout();credits.setSpacing(10)
        credit=QLabel('来自 VB-Audio · Donationware，欢迎捐赠支持');credit.setObjectName('InstallerNote');credits.addWidget(credit);credits.addStretch()
        for text,url in [('官网',OFFICIAL_URL),('授权说明',LICENSE_URL),('支持作者',SUPPORT_URL)]:
            button=QPushButton(text);button.setObjectName('TextButton');button.clicked.connect(lambda checked=False,u=url:QDesktopServices.openUrl(QUrl(u)));credits.addWidget(button)
        layout.addLayout(credits)
        self.timer=QTimer(self);self.timer.setInterval(800);self.timer.timeout.connect(self.poll_installer)
        self.devices=QMediaDevices(self)
        self.devices.audioInputsChanged.connect(lambda:self.refresh_status(True));self.devices.audioOutputsChanged.connect(lambda:self.refresh_status(True))
        self.refresh_status()

    def say(self,text):self.feedback.setText(text);self.feedback.setVisible(bool(text))

    def refresh_status(self,refresh_devices=False):
        self.device_status=detect_cable(*self.device_provider())
        status=self.device_status
        if status.ready:
            text='已检测到 VB-CABLE 的标准收发端点，可在本程序选用。'
        elif status.present:
            text='只检测到部分 VB-CABLE 端点，可能尚未就绪。请先重启电脑并重新检测，再检查设备是否启用。'
        else:text='未检测到 VB-CABLE。已有其他虚拟声卡时也可继续使用现有设备。'
        if not self.bundle_ok:text+=' 如需安装 VB-CABLE，请访问官网。'
        self.status.setText(text)
        busy=self.process is not None or self.tracking_lost
        self.install_button.setEnabled(self.bundle_ok and not status.ready and not busy)
        self.install_button.setText('安装器运行中…' if busy else '已检测到 VB-CABLE' if status.ready else '打开官方安装器…' if status.present else '安装虚拟声卡…')
        self.use_button.setEnabled(status.ready and not busy and self.on_select is not None)
        if refresh_devices and self.on_refresh:self.on_refresh()

    def install_clicked(self):
        self.refresh_status()
        if not self.install_button.isEnabled():return
        self.install_button.setEnabled(False)
        try:
            self.prepared=self.package.prepare()
            self.process=self.start_fn(self.prepared)
            if self.process is None:raise InstallerUntracked('已请求启动安装器，但无法跟踪状态；请完成官方安装并重启电脑。')
            self.say('官方安装器已打开。请在安装器中点击 Install Driver；安装完成后按官方要求重启，再回来重新检测。')
            self.timer.start()
        except InstallerCancelled as exc:self.say(str(exc))
        except InstallerUntracked as exc:self.tracking_lost=True;self.say(str(exc))
        except (OSError,ValueError,RuntimeError) as exc:self.say('未能启动安装器：'+str(exc))
        self.refresh_status()

    def poll_installer(self):
        if self.process is None:return
        try:code=self.process.poll()
        except OSError as exc:
            self.tracking_lost=True;self.process.close();self.process=None;self.timer.stop()
            self.say('无法继续确认安装器状态：'+str(exc)+'；请完成官方安装后重启。');self.refresh_status();return
        if code is None:return
        self.process.close();self.process=None;self.timer.stop()
        self.say('官方安装器已关闭。若已完成 Install Driver，请先重启电脑，再点击重新检测。设备未出现时不能视为安装成功。'
                 +(f' 安装器退出码：{code}。' if code else ''))
        self.refresh_status(True)

    def use_cable(self):
        self.refresh_status()
        if not self.use_button.isEnabled():return
        if self.on_select(self.device_status.playback):
            self.say('已在本程序选用 CABLE Input。需要发送时请勾选下方开关，并在语音软件选择 CABLE Output。')
        else:self.say('未能保存声卡选择，请查看下方设备列表和窗口底部提示。')

    def shutdown(self):
        self.timer.stop()
        if self.process is not None:self.process.close();self.process=None
