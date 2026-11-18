"""FF14 native entry, using SR Voiceover Roulette's original audio engine."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction,QFontDatabase,QIcon
from PySide6.QtWidgets import QApplication,QAbstractSpinBox,QLineEdit,QMenu,QSystemTrayIcon,QMessageBox,QStyle
import sr_roulette as sr
from app_paths import prepare_user_data,ensure_empty_sound_config,user_data_dir,_atomic_bytes
from sounds_config import SoundsConfig
from skillbar_model import SkillbarConfig,canonical_key
from skillbar_runtime import SkillbarBank,CooldownAudio,SkillbarInputPoller,SkillbarAudioEngine
from skillbar_icons import IconCatalog
from skillbar_ui import SkillbarWindow
from skillbar_overlay import SkillbarController
from ui_theme import apply_theme,THEME_VERSION
from wheel_geometry import validate_order,DEFAULT_ORDER,LEGACY_ORDER


def application_icon(resources):
    icon = QIcon(str(Path(resources)/'assets'/'app.ico'))
    return icon if not icon.isNull() else QApplication.style().standardIcon(QStyle.SP_MediaVolume)


class NativeApplication:
    def __init__(self,data_dir,resource_dir,*,enable_input=True,enable_audio=True):
        self.data=Path(data_dir); self.data.mkdir(parents=True,exist_ok=True)
        ensure_empty_sound_config(self.data)
        self.cfg=dict(sr.DEFAULT_CONFIG,wheel_only=False,always_on_top=False,pause_key='ctrl+shift+f12',library_sort='name')
        path=self.data/'config.json';values={}
        if path.exists():
            values=json.loads(path.read_text(encoding='utf-8'))
            self.cfg.update({key:value for key,value in values.items() if key in self.cfg})
        order=self.cfg.get('wheel_order',DEFAULT_ORDER)
        if values.get('wheel_order_version',0)<2 and order==list(range(len(LEGACY_ORDER))):
            order=LEGACY_ORDER
        try:self.cfg['wheel_order']=validate_order(order)
        except ValueError:self.cfg['wheel_order']=list(DEFAULT_ORDER)
        self.cfg['wheel_order_version']=3
        self.icons=IconCatalog(Path(resource_dir)/'assets'/'ff14')
        self.model=SkillbarConfig(self.data/'ff14_soundbar.json',ability_icons=self.icons.ability_icons)
        self.cfg['wheel_only']=self.cfg['wheel_only'] is True
        self.cfg['always_on_top']=self.cfg['always_on_top'] is True
        value=self.cfg['pause_key']
        try:pause_key=canonical_key(value) if isinstance(value,str) else ''
        except ValueError:pause_key=''
        conflicts=self.model.used_keys() | {sr.norm_spec(self.cfg.get(name,'')) for name in ('hotkey','repeat_last_key','cycle_key')}
        self.cfg['pause_key']='' if pause_key in conflicts else pause_key
        self._saved_cfg=dict(self.cfg)
        self.effects=SoundsConfig(self.data/'sounds.json'); self.effects.load()
        self.bank=SkillbarBank(self.model,self.data/'sounds',self.effects)
        self.engine=SkillbarAudioEngine(self.bank,self.cfg) if enable_audio else None
        self.audio=CooldownAudio(self.engine,self.model) if self.engine else None
        self.raw=self.poller=self.controller=self.tray=self.watch=self.tray_pause=None
        self.window=SkillbarWindow(self.model,self.data/'sounds',self.icons,self.cfg,self.engine,resources=resource_dir,effects=self.effects)
        self.window.quit_requested.connect(QApplication.instance().quit)
        self.window.trigger_pause_requested.connect(self.toggle_trigger_pause)
        self.window.game_audio=self.audio
        self.window.preferences_writer=self.save_preferences
        self.window.changed.connect(self.on_changed)
        self.window.preferences_changed.connect(self.on_preferences)
        if self.engine:self.engine.start()
        if enable_input and self.audio:
            self.raw=sr.RawMouse(); ok=self.raw.start(QApplication.instance())
            self.controller=SkillbarController(self.cfg,self.bank,self.raw,self.audio,self.model,self.icons)
            self.poller=SkillbarInputPoller(self.cfg,self.controller,self.audio,self.model)
            self.poller.paused=self.settings_active
            self.poller.on_pause_changed=self.on_pause
            self.poller.on_trigger_state_changed=self.window.set_trigger_state
            self.window.pause_button.setEnabled(True)
            self.window.bar_pause_button.setEnabled(True)
            self.window.closed.connect(self.poller.rebuild_bindings)
            self.poller.start()
            if not ok:self.window.status.setText('鼠标原始输入注册失败，按键仍可触发；长按选择暂不可用。')
        if self.engine:
            self.watch=QTimer(self.window); self.watch.setInterval(3000)
            self.watch.timeout.connect(self.engine.restart_sink); self.watch.start()
        if enable_input or enable_audio:self.create_tray()

    def settings_active(self):
        if self.window.capture_pending:
            return True
        active = (QApplication.activePopupWidget() or QApplication.activeModalWidget()
                  or QApplication.activeWindow())
        if active is self.window:
            # Key capture also uses a read-only QLineEdit.
            return isinstance(QApplication.focusWidget(), (QLineEdit, QAbstractSpinBox))
        while active is not None:
            active = active.parentWidget()
            if active is self.window:
                return True
        return False

    def on_pause(self,on):
        if self.controller:self.controller.widget.paused=bool(on)
        text='恢复触发' if on else '暂停触发'
        self.window.pause_button.setText(text)
        self.window.bar_pause_button.setText(text)
        if on:self.window.set_trigger_state('paused')
        if self.tray_pause:self.tray_pause.setText(text)
        if self.tray:self.tray.setToolTip('FF14 音效技能栏' + (' · 已暂停' if on else ''))

    def toggle_trigger_pause(self):
        if self.poller:self.poller.toggle_trigger_pause()

    def save_preferences(self,candidate):
        _atomic_bytes(self.data/'config.json',json.dumps(candidate,ensure_ascii=False,indent=2).encode('utf-8'))
        self._saved_cfg=dict(candidate)

    def on_preferences(self):
        try:
            if self.cfg!=self._saved_cfg:self.save_preferences(self.cfg)
            if self.poller:
                self.poller.set_hotkey(self.cfg['hotkey']); self.poller.rebuild_bindings()
            if self.engine:self.engine.apply_audio_cfg()
        except (OSError,ValueError) as exc:
            self.cfg.clear(); self.cfg.update(self._saved_cfg)
            self.window.restore_preferences()
            self.window.status.setText('设置未生效，已恢复保存值：'+str(exc))

    def on_changed(self,reason):
        logging.getLogger('ff14').info('Configuration changed: %s',reason)
        if self.engine and reason in ('acceleration','sound','key','preset'):
            reset=getattr(self.engine,'reset_repeat_acceleration',None)
            if callable(reset):reset()
        if reason in ('sound','preset'):
            if reason=='preset' and self.engine:self.engine.stop_all()
            self.bank.reload()
            if self.engine:self.engine.load(stop_playing=reason=='preset')
        if reason in ('library','volume'):self.bank.reload()
        if reason in ('library','preset') and self.engine:
            for name in ('_combo_cache','_combo_last','_combo_step','_stretch_cache'):
                value=getattr(self.engine,name,None)
                if hasattr(value,'clear'):value.clear()
            reset=getattr(self.engine,'reset_pitch',None)
            if callable(reset):reset()
        if self.poller and reason in ('sound','key','icon','preset','input','temporary_gcd'):
            self.poller.rebuild_bindings()
        if reason=='preset' and self.engine:self.engine.reset_slot_playback()
        if reason=='preset' and self.audio:self.audio.reset_preset_state()
        if self.controller:self.controller.widget.update()

    def create_tray(self):
        self.tray=QSystemTrayIcon(application_icon(self.window.resources),self.window)
        self.tray.setToolTip('FF14 音效技能栏')
        menu=QMenu(self.window)
        settings=QAction('设置…',menu); settings.triggered.connect(self.show_settings); menu.addAction(settings)
        if self.poller:
            self.tray_pause=QAction('暂停触发',menu);self.tray_pause.triggered.connect(self.toggle_trigger_pause);menu.addAction(self.tray_pause)
        stop=QAction('停止当前音效',menu); stop.triggered.connect(lambda:self.engine and self.engine.stop_all()); menu.addAction(stop)
        exit_action=QAction('退出',menu); exit_action.triggered.connect(QApplication.instance().quit); menu.addAction(exit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason:self.show_settings() if reason==QSystemTrayIcon.DoubleClick else None)
        self.tray.show()
        if self.engine:self.engine.problem.connect(lambda text:self.tray.showMessage('声音输出',text,QSystemTrayIcon.Warning))

    def show_settings(self):
        self.window.show(); self.window.raise_(); self.window.activateWindow()

    def shutdown(self):
        import logging
        logging.getLogger('ff14').info('Application shutting down')
        self.window.shutting_down=True
        self.window.audition.shutdown()
        if self.window.region_capture:self.window.region_capture.reject()
        self.window.cable_panel.shutdown();self.window.status_timer.stop()
        dialog=self.window.screenshot_dialog
        if dialog is not None and dialog.worker is not None:
            dialog.close_pending=True;dialog.worker.requestInterruption();dialog.worker.wait()
        if self.window.capture_temp:self.window.capture_temp.cleanup();self.window.capture_temp=None
        if self.poller:self.poller._timer.stop()
        if self.watch:self.watch.stop()
        if self.controller:self.controller.hide_wheel()
        if self.engine:
            self.engine.stop_all(); self.engine.release_capture(); self.engine.stop_outputs()
        if self.tray:self.tray.hide()
        self.window.player.stop()


def main(argv=None,release=False):
    parser=argparse.ArgumentParser(description='FF14 音效技能栏')
    parser.add_argument('--data-dir',type=Path)
    parser.set_defaults(no_input=False,no_audio=False,check=False,check_image=None,check_cable=False,check_advanced=None,check_wheel=None,report=None,render=None)
    if not release:
        parser.add_argument('--no-input',action='store_true',help='只编辑，不启动游戏按键监听')
        parser.add_argument('--no-audio',action='store_true',help='不启动播放和麦克风链路')
        parser.add_argument('--check',action='store_true',help='无音频、无按键自检后退出')
        parser.add_argument('--check-image',type=Path,help='离线分析指定截图并写入自检报告，不修改技能栏')
        parser.add_argument('--check-cable',action='store_true',help='仅解压并校验内置声卡包，不运行安装器；需指定隔离data-dir')
        parser.add_argument('--check-advanced',type=Path,help='使用临时数据验证高级编辑、组合绑定及离线WAV处理，结果写入指定目录')
        parser.add_argument('--check-wheel',type=Path,help='使用模拟鼠标与临时数据检查分页轮盘，不启动真实输入、滚轮钩子或音频')
        parser.add_argument('--report',type=Path)
        parser.add_argument('--render',type=Path,help='自检时导出设置窗口图片')
    args=parser.parse_args(argv)
    if args.check_cable and args.data_dir is None:parser.error('--check-cable 需要指定 --data-dir 隔离测试目录。')
    if args.check_advanced and args.data_dir is None:parser.error('--check-advanced 需要指定 --data-dir 隔离测试目录。')
    if args.check_wheel and args.data_dir is None:parser.error('--check-wheel 需要指定 --data-dir 隔离测试目录。')
    if args.check_image or args.check_cable or args.check_advanced or args.check_wheel:args.check=True
    if args.check:os.environ['QT_QPA_PLATFORM']='offscreen'
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName('FF14 音效技能栏'); app.setStyle('Fusion')
    apply_theme(app)
    app.setWindowIcon(application_icon(Path(__file__).resolve().parent))
    if app.platformName()=='offscreen':
        # The offscreen platform starts with no Windows font database.
        # Load installed fonts for readable diagnostic image exports.
        for filename in ('msyh.ttc','segoeui.ttf'):
            font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/filename
            if font.is_file():QFontDatabase.addApplicationFont(str(font))
    app.setQuitOnLastWindowClosed(args.no_input and args.no_audio)
    data=args.data_dir or user_data_dir()
    # Legacy helpers must use the same portable data root as this entry.
    sr.DATA_DIR=data
    sr.CONFIG_PATH=data/'config.json'; sr.SOUNDS_CONFIG_PATH=data/'sounds.json'
    sr.SOUNDS_DIR=data/'sounds'; sr.LOG_PATH=data/'sr_roulette.log'
    if not args.check:
        from diagnostics import install_logging
        install_logging(data)
    mutex=None
    if not args.check:
        identity=hashlib.sha256(str(data.resolve()).casefold().encode()).hexdigest()[:20]
        mutex=sr._kernel32.CreateMutexW(None,False,'Local\\FF14Soundbar_'+identity)
        if ctypes.get_last_error()==183:
            QMessageBox.information(None,'FF14 音效技能栏','这个音效库的程序已经在运行，请从系统托盘打开设置。')
            return 0
    resource=Path(__file__).resolve().parent
    legacy=Path(sys.executable).parent if getattr(sys,'frozen',False) else resource
    try:
        prepare_user_data(legacy,data,resource)
        from bundled_audio import sync_bundled_audio
        sync_bundled_audio(resource/'sounds',data)
        native=NativeApplication(data,resource,enable_input=not(args.no_input or args.no_audio or args.check),enable_audio=not(args.no_audio or args.check))
    except (OSError,ValueError,TypeError) as exc:
        if args.report:args.report.write_text(json.dumps({'error':str(exc)},ensure_ascii=False),encoding='utf-8')
        if not args.check:QMessageBox.critical(None,'启动失败',str(exc))
        return 1
    app.aboutToQuit.connect(native.shutdown)
    if args.check:
        native.window.show_library(); native.window.resize(1180,800)
        if args.render:native.window.change_page(native.window.audio_page if args.check_cable else native.window.bar_page)
        native.window.show(); app.processEvents();app.processEvents()
        if args.render:native.window.grab().save(str(args.render))
        report={'slots':len(native.model.slots),'sounds':len(native.window.bind_buttons),'professions':len(native.icons.jobs),
                'theme_version':THEME_VERSION,
                'icons':len(native.icons.files),'cooldown':native.model.cooldown,'bound_slots':[i for i,slot in enumerate(native.model.slots) if slot.sound],
                'input_started':native.poller is not None,'audio_started':native.engine is not None}
        report.update(presets=[{'id':identity,'name':entry['name']} for identity,entry in native.model.presets.items()],
                      active_preset=native.model.active_preset,preset_name=native.model.preset_name,unsaved_changes=native.model.dirty)
        from virtual_cable import PACKAGE_SHA256
        report['bundled_cable']={'available':native.window.cable_panel.bundle_ok,'sha256':PACKAGE_SHA256,'installer_started':native.window.cable_panel.process is not None}
        if args.check_cable:
            try:
                prepared=native.window.cable_panel.package.prepare()
                report['bundled_cable'].update(prepared_files=len(prepared.hashes),prepared_directory=str(prepared.directory),selected_installer=prepared.executable.name)
            except (OSError,ValueError) as exc:report['bundled_cable']['error']=str(exc)
        if args.check_image:
            from dataclasses import asdict
            from screenshot_import import analyze_screenshot
            try:
                result=analyze_screenshot(args.check_image,native.icons)
                report['screenshot']={'icons':sum(bool(v.icon) for v in result.visuals),'keys':sum(bool(v.key) for v in result.visuals),
                                      'visuals':[asdict(v) for v in result.visuals],'cells':result.cells,'warning':result.warning}
            except Exception as exc:
                report['screenshot_error']=str(exc)
        if args.check_advanced:
            from advanced_audio_check import run_check
            try:report['advanced_audio']=run_check(args.check_advanced,resource,render=bool(args.render))
            except Exception as exc:report['advanced_error']=str(exc)
        if args.check_wheel:
            from wheel_check import run_check
            try:report['wheel']=run_check(args.check_wheel,resource,render=bool(args.render))
            except Exception as exc:report['wheel_error']=str(exc)
        if args.report:args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        native.shutdown(); native.window.close()
        return 1 if 'screenshot_error' in report or 'advanced_error' in report or 'wheel_error' in report or 'error' in report['bundled_cable'] else 0
    native.show_settings()
    code=app.exec()
    if mutex:sr._kernel32.CloseHandle(mutex)
    return code


if __name__=='__main__':raise SystemExit(main())
