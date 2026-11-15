"""Cursor-centred paged selector, retaining the original hold/release state machine."""
import math,time
from PySide6.QtCore import QObject,QPoint,QPointF,QRectF,Qt,QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication,QWidget
from wheel_geometry import hit_slot,validate_order,WheelSteps,radii,DEFAULT_ORDER,PAGE_COUNT
from wheel_capture import WheelCapture
from wheel_paint import paint_wheel,page_rect


# Previous hotbar helpers remain for external source/QA consumers.
# Gameplay below uses only radial hit_slot.
def slot_rect(index,width=860,height=260):
    if not 0<=index<24:raise ValueError('技能格位置无效。')
    pitch=(width-64)/12
    return QRectF(32+(index%12)*pitch,height/2+(-80 if index<12 else 16),pitch-6,64)


def hit_test(point,width=860,height=260):
    return next((i for i in range(24) if slot_rect(i,width,height).contains(point)),None)


class SkillbarOverlay(QWidget):
    def __init__(self,model,icons,audio,effects=None):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.WindowDoesNotAcceptFocus|Qt.WindowTransparentForInput)
        for attribute in (Qt.WA_TranslucentBackground,Qt.WA_TransparentForMouseEvents,Qt.WA_ShowWithoutActivating):self.setAttribute(attribute)
        self.setFocusPolicy(Qt.NoFocus);self.model=model;self.icons=icons;self.audio=audio;self.effects=effects
        self.selected=None;self.page=0;self.order=list(DEFAULT_ORDER);self.pointer=None;self.paused=False;self.scroll_ready=True
        self.vx=self.vy=0
        self.resize(580,580);self.timer=QTimer(self);self.timer.setInterval(50);self.timer.timeout.connect(self.update)
    def showEvent(self,event):super().showEvent(event);self.timer.start()
    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)
    def paintEvent(self,event):paint_wheel(self)


class SkillbarController(QObject):
    def __init__(self,cfg,bank,raw,audio,model,icons,*,cursor=None,capture=None,screen_rect=None):
        super().__init__();self.cfg=cfg;self.bank=bank;self.raw=raw;self.audio=audio;self.model=model
        self.cursor=cursor or QCursor.pos;self.capture=capture if capture is not None else WheelCapture();self.screen_rect=screen_rect or self._screen_rect
        self.widget=SkillbarOverlay(model,icons,audio,getattr(bank,'scfg',None));self.active=False;self.selected=None
        self.vx=self.vy=0;self.steps=WheelSteps();self.armed=False;self.guard=QPoint();self.hover_page=None;self.hover_at=0;self.hover_fired=False
        self.noop=False;self.guard_vector=(0,0)

    @staticmethod
    def _screen_rect(point):
        screen=QApplication.screenAt(point) or QApplication.primaryScreen()
        return screen.availableGeometry()

    def show_wheel(self):
        if self.active:return
        point=self.cursor();geo=self.screen_rect(point);size=max(120,min(580,geo.width()-16,geo.height()-16))
        x=max(geo.left()+8,min(point.x()-size//2,geo.right()-size+1-8));y=max(geo.top()+8,min(point.y()-size//2,geo.bottom()-size+1-8))
        self.widget.resize(size,size);self.widget.move(x,y)
        try:self.widget.order=validate_order(self.cfg.get('wheel_order',DEFAULT_ORDER))
        except ValueError:self.widget.order=list(DEFAULT_ORDER)
        self.active=True;self.selected=None;self.widget.selected=None;self.steps.clear();self.raw.drop()
        self.guard=QPoint(point);self.armed=False;self.noop=False;self.vx=self.vy=0;self.guard_vector=(0,0)
        self.widget.pointer=QPointF(self.widget.mapFromGlobal(point));self.hover_page=None;self.hover_fired=False
        self.widget.scroll_ready=self.capture.start();self.widget.setWindowOpacity(float(self.cfg.get('opacity',.94)))
        self.widget.show();self.widget.update()

    def hide_wheel(self,**kwargs):
        self.active=False;self.selected=None;self.capture.stop();self.steps.clear();self.widget.hide()

    def change_page(self,delta,point):
        self.widget.page=(self.widget.page+delta)%PAGE_COUNT;self.selected=None;self.widget.selected=None
        self.guard=QPoint(point);self.guard_vector=(self.vx,self.vy);self.armed=False;self.noop=True;self.widget.update()

    def poll_selection(self):
        if not self.active:return
        point=self.cursor();delta=self.steps.add(self.capture.take())
        if delta:self.change_page(delta,point)
        if self.cfg.get('wheel_pointer_mode','cursor')=='relative':
            dx,dy=self.raw.take();sensitivity=float(self.cfg.get('sensitivity',.85));limit=radii(self.widget.width())[1]
            self.vx+=dx*sensitivity;self.vy+=dy*sensitivity;distance=math.hypot(self.vx,self.vy)
            if distance>limit:self.vx*=limit/distance;self.vy*=limit/distance
            local=QPointF(self.widget.width()/2+self.vx,self.widget.height()/2+self.vy)
            if delta:self.guard_vector=(self.vx,self.vy)
            if not delta and math.hypot(self.vx-self.guard_vector[0],self.vy-self.guard_vector[1])>=6:self.armed=True
        else:
            self.raw.take()
            local=QPointF(self.widget.mapFromGlobal(point))
            if not delta and (point-self.guard).manhattanLength()>=6:self.armed=True
        self.widget.pointer=local
        page=next((i for i in range(PAGE_COUNT) if page_rect(i,self.widget.width()).contains(local)),None) if self.armed else None
        now=time.monotonic()
        if page!=self.hover_page:self.hover_page=page;self.hover_at=now;self.hover_fired=False
        if page is not None:
            self.selected=None;self.widget.selected=None;self.noop=True
            if page!=self.widget.page and not self.hover_fired and now-self.hover_at>=.35:
                self.change_page(page-self.widget.page,point);self.hover_fired=True
        else:
            index=hit_slot(local.x(),local.y(),self.widget.width(),self.widget.page,self.widget.order) if self.armed else None
            self.selected=index if index is not None and self.model.slots[index].sound else None
            self.widget.selected=self.selected
            inner,_=radii(self.widget.width());distance=math.hypot(local.x()-self.widget.width()/2,local.y()-self.widget.height()/2)
            self.noop=self.selected is None and (distance>=inner or not self.armed and self.noop)
        self.widget.update()

    def commit(self):
        self.poll_selection();index=self.selected;noop=self.noop
        self.hide_wheel()
        return index if index is not None else -1 if noop else None
