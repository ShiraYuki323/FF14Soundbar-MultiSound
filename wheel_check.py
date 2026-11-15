"""Generated-data radial selector check, no live input/audio/hooks."""
import json,tempfile,wave
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import QPoint,QPointF,QRect
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import QTimer
from wheel_geometry import slot_center,PAGE_COUNT,PAGE_SIZE


def run_check(output,resources,render=False):
    from ff14_app import NativeApplication
    from skillbar_overlay import SkillbarController
    output=Path(output);output.mkdir(parents=True,exist_ok=True);app=QApplication.instance()
    class Capture:
        def __init__(self):self.delta=0
        def start(self):return True
        def stop(self):self.delta=0
        def take(self):delta=self.delta;self.delta=0;return delta
    images=[]
    def save(widget,name):
        if render:
            app.processEvents();app.processEvents();widget.grab().save(str(output/name));images.append(name)
    with tempfile.TemporaryDirectory(prefix='wheel-',dir=output) as folder:
        data=Path(folder);sounds=data/'sounds';sounds.mkdir()
        labels=['嗯？','冰冰冰','真的很帅','怒','哎呦我去','哇哦','笑声','啊叽','灵魂尖叫','男人叹气','爱音唐哭','哈哈哈哈','出发','加油','好耶','谢谢','没问题','再来一次','倒计时','恭喜','等等我','收到','晚安','结束啦']
        for label in labels:
            with wave.open(str(sounds/(label+'.wav')),'wb') as audio:audio.setnchannels(2);audio.setsampwidth(2);audio.setframerate(48000);audio.writeframes(b'\0'*1920)
        native=NativeApplication(data,resources,enable_input=False,enable_audio=False);controller=None
        try:
            job=next((j for j in native.icons.jobs if j.get('id')=='blackmage'),None)
            skills=job.get('skills',[]) if job else []
            for index in native.cfg['wheel_order']:
                label=labels[index%len(labels)]
                native.model.bind(index,label+'.wav')
                if skills:native.model.update_slot(index,icon=skills[(index+1)%len(skills)])
            native.bank.reload();native.window.refresh();cursor=[900,500];capture=Capture()
            audio=SimpleNamespace(remaining=lambda:0,ability_cooldown=lambda _: (0,2.5),duration=2.5,bank=native.bank)
            controller=SkillbarController(native.cfg,native.bank,SimpleNamespace(drop=lambda:None,take=lambda:(900,900)),audio,native.model,native.icons,
                cursor=lambda:QPoint(*cursor),capture=capture,screen_rect=lambda _:QRect(0,0,1920,1080))
            selected=[]
            for page in range(PAGE_COUNT):
                for sector in range(len(native.cfg['wheel_order'][page*PAGE_SIZE:(page+1)*PAGE_SIZE])):
                    cursor[:]=[900,500];controller.show_wheel();capture.delta=-(page-controller.widget.page)*120;controller.poll_selection()
                    x,y=slot_center(sector,controller.widget.width());cursor[:]=[controller.widget.x()+round(x),controller.widget.y()+round(y)]
                    controller.poll_selection();assert controller.selected==native.cfg['wheel_order'][page*PAGE_SIZE+sector]
                    if sector==2:save(controller.widget,f'轮盘-第{page+1}页.png')
                    selected.append(controller.commit())
            assert selected==native.cfg['wheel_order']
            remembered=controller.widget.page;controller.show_wheel();assert controller.widget.page==remembered;controller.hide_wheel()
            from screen_capture_ui import RegionCapture
            sample=QImage(800,450,QImage.Format_RGB32);sample.fill(QColor('#354654'))
            selector=RegionCapture(sample,QRect(0,0,400,225),native.window);selector.region=QRect(20,30,100,50)
            cropped=selector.cropped_image();assert (cropped.width(),cropped.height())==(200,100)
            save(selector,'框选截图-模拟图片.png');selector.close();selector.deleteLater()
            def cancel_close():
                dialog=app.activeModalWidget()
                if dialog:
                    save(dialog,'退出选择.png')
                    for button in dialog.buttons():
                        if button.text()=='取消':button.click();break
            QTimer.singleShot(0,cancel_close);assert native.window.ask_close_action()=='cancel'
            native.cfg['wheel_pointer_mode']='relative';cursor[:]=[900,500];controller.widget.page=0;controller.show_wheel()
            controller.raw.take=lambda:(-1000,800);controller.poll_selection();controller.raw.take=lambda:(0,0)
            relative_boundary=controller.commit();assert relative_boundary==native.cfg['wheel_order'][5]
            native.cfg['wheel_pointer_mode']='cursor';cursor[:]=[900,500];controller.show_wheel();assert controller.commit() is None
            cursor[:]=[4,4];controller.show_wheel();assert controller.commit()==-1
            native.window.open_wheel_order();save(native.window.wheel_dialog,'轮盘排序.png');native.window.wheel_dialog.reject()
            native.window.change_page(native.window.preferences_page);save(native.window,'轮盘设置.png')
            report={'platform':app.platformName(),'pages':PAGE_COUNT,'slots_per_page':PAGE_SIZE,'selected_indices':selected,
                'page_memory_verified':True,'synthetic_crop_verified':True,'close_dialog_verified':True,'edge_open_noop':True,'relative_boundary_slot':relative_boundary,'center_stop_preserved':True,
                'input_started':native.poller is not None,'audio_started':native.engine is not None,'real_hook_started':False,'images':images}
            (output/'wheel-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report
        finally:
            if controller:controller.hide_wheel();controller.widget.close();controller.widget.deleteLater();controller.deleteLater()
            native.shutdown();native.window.close();native.window.deleteLater();app.processEvents()
