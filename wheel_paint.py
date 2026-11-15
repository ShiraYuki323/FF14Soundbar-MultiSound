"""FF14 framed skills on an eight-direction silver/gold radial selector."""
import math
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen,QFont
from wheel_geometry import radii,slot_center,PAGE_COUNT,PAGE_SIZE
from skillbar_paint import paint_slot,fit_frame
from skillbar_model import key_label,sound_label


def page_rect(page,size):
    scale=size/580
    offset=(page-(PAGE_COUNT-1)/2)*26*scale
    return QRectF(size/2+offset-11*scale,size/2+38*scale,22*scale,24*scale)


def paint_wheel(widget):
    p=QPainter(widget);p.setRenderHint(QPainter.Antialiasing)
    size=widget.width();scale=size/580;c=QPointF(size/2,size/2);inner,outer=radii(size)
    effects=getattr(getattr(widget.audio,'bank',None),'scfg',None) if widget.audio else None
    if widget.effects is not None:effects=widget.effects
    remaining=widget.audio.remaining() if widget.audio else 0
    for sector,index in enumerate(widget.order[widget.page*PAGE_SIZE:(widget.page+1)*PAGE_SIZE]):
        slot=widget.model.slots[index];selected=widget.selected==index;start=111.6-sector*45
        path=QPainterPath();path.arcMoveTo(QRectF(c.x()-outer,c.y()-outer,outer*2,outer*2),start)
        path.arcTo(QRectF(c.x()-outer,c.y()-outer,outer*2,outer*2),start,-43.2)
        end=math.radians(start-43.2);path.lineTo(c.x()+inner*math.cos(end),c.y()-inner*math.sin(end))
        path.arcTo(QRectF(c.x()-inner,c.y()-inner,inner*2,inner*2),start-43.2,43.2);path.closeSubpath()
        p.setBrush(QColor('#4a4940' if selected else '#252e33'));p.setPen(QPen(QColor('#dbc18a' if selected else '#657278'),1.5 if selected else .8));p.drawPath(path)
        x,y=slot_center(sector,size);box=fit_frame(QRectF(x-28*scale,y-38*scale,56*scale,59*scale))
        ability=widget.model.slot_is_ability(slot)
        cooldown=(widget.audio.ability_cooldown(index) if widget.audio and ability else
                  (remaining,getattr(widget.audio,'duration',widget.model.cooldown)))
        paint_slot(p,box,widget.icons,slot,selected=selected,review=widget.model.review.get(index,()),
                   ability=ability,remaining=cooldown[0],duration=cooldown[1])
        p.setFont(QFont('Microsoft YaHei UI',max(8,round(9*scale))));p.setPen(QColor('#f1e0b8' if selected else '#deded6' if slot.sound else '#818d92'))
        label=sound_label(slot.sound,effects) if slot.sound else '未设音效'
        text=p.fontMetrics().elidedText(label,Qt.ElideRight,round(102*scale))
        p.drawText(QRectF(x-55*scale,y+27*scale,110*scale,24*scale),Qt.AlignCenter,text)
    p.setBrush(QColor('#20272c'));p.setPen(QPen(QColor('#9c947d'),1));p.drawEllipse(c,inner-3,inner-3)
    def text(rect,value,color='#e6dfca',points=9,flags=Qt.AlignCenter):
        p.setPen(QColor(color));p.setFont(QFont('Microsoft YaHei UI',max(8,round(points*scale))));p.drawText(rect,flags,value)
    text(QRectF(c.x()-inner+8,c.y()-64*scale,inner*2-16,22*scale),f'音效轮盘  ·  {widget.page+1} / {PAGE_COUNT}','#aebbbf',8)
    if widget.selected is not None:
        slot=widget.model.slots[widget.selected];label=sound_label(slot.sound,effects)
        text(QRectF(c.x()-inner+8,c.y()-38*scale,inner*2-16,58*scale),label,points=10,flags=Qt.AlignCenter|Qt.TextWordWrap)
        text(QRectF(c.x()-inner+8,c.y()+17*scale,inner*2-16,18*scale),key_label(slot.key) or '无触发键','#c8bfaa',8)
    else:
        text(QRectF(c.x()-inner+8,c.y()-34*scale,inner*2-16,32*scale),'移动鼠标选择',points=10)
        text(QRectF(c.x()-inner+8,c.y()+1*scale,inner*2-16,28*scale),'松开恢复' if widget.paused else '中心松开停止 / 暂停','#aebbbf',8)
    for page in range(PAGE_COUNT):
        rect=page_rect(page,size);p.setPen(QPen(QColor('#d1bb89' if page==widget.page else '#556168'),1));p.setBrush(QColor('#555246' if page==widget.page else '#2a3439'));p.drawRoundedRect(rect,4,4)
        text(rect,str(page+1),points=8)
    text(QRectF(20,size-38*scale,size-40,20*scale),f'公共冷却 {remaining:.1f}s' if remaining else '长按呼出 · 滚轮切页 · 松手播放','#c6c5b8',9)
    if not widget.scroll_ready:text(QRectF(20,8,size-40,20*scale),'滚轮捕获不可用，可悬停中心页码切页','#d7bb91',8)
    if widget.pointer is not None:
        point=widget.pointer;dx,dy=point.x()-c.x(),point.y()-c.y();dist=math.hypot(dx,dy)
        if dist>inner:
            ratio=min(1,outer/max(1,dist));tip=QPointF(c.x()+dx*ratio,c.y()+dy*ratio)
            p.setPen(QPen(QColor(224,205,160,100),1));p.drawLine(c,tip)
        p.setBrush(QColor('#efdcac'));p.setPen(QPen(QColor('#232a2f'),1));p.drawEllipse(point,3,3)
    p.end()
