"""The approved FF14 frame, proportions and text shared by all native hotbars."""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QColor,QFont,QPen,QLinearGradient,QPainterPath,QPixmap,QIcon,QPainter
from skillbar_model import key_label,SkillSlot


def fit_frame(box):
    width=min(box.width(),box.height()*88/91)
    return QRectF(box.center().x()-width/2,box.center().y()-width*91/88/2,width,width*91/88)


def paint_slot(painter,rect,icons,slot,*,selected=False,matched=False,review=(),ability=False,remaining=0,duration=2.5,hover=False):
    painter.save();painter.setRenderHint(QPainter.Antialiasing)
    if selected:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor('#ffe3a1'),2))
        painter.drawRoundedRect(rect.adjusted(-2,-2,2,2),6,6)
    elif matched:
        for size,alpha in ((3,25),(2,65),(1,190)):
            painter.setPen(QPen(QColor(234,211,160,alpha),1));painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-size,-size,size,size),6,6)
    art=icons.pixmap(slot.icon)
    inner=QRectF(rect.x()+rect.width()*.0455,rect.y()+rect.height()*.033,rect.width()*.909,rect.height()*.8791)
    if not art.isNull():
        painter.drawPixmap(inner.toRect(),art)
        frame=icons.pixmap('frame.png')
        if not frame.isNull():painter.drawPixmap(rect.toRect(),frame)
    else:
        gradient=QLinearGradient(rect.topLeft(),rect.bottomRight());gradient.setColorAt(0,QColor('#343a3d'));gradient.setColorAt(1,QColor('#1a1e20'))
        painter.setBrush(gradient);painter.setPen(QPen(QColor('#b49b69' if review else '#545b5e'),1,Qt.DashLine if review else Qt.SolidLine))
        painter.drawRoundedRect(rect,5,5)
        painter.setFont(QFont('Microsoft YaHei UI',18));painter.setPen(QColor('#e3cb93' if 'icon' in review else '#747d80'))
        painter.drawText(rect,Qt.AlignCenter,'?' if 'icon' in review else '＋')
    if remaining>0 and slot.sound:
        path=QPainterPath();path.addRoundedRect(inner,4,4);painter.save();painter.setClipPath(path)
        painter.setPen(Qt.NoPen);painter.setBrush(QColor(8,13,19,185))
        radius=max(rect.width(),rect.height())*1.5;circle=QRectF(rect.center().x()-radius,rect.center().y()-radius,radius*2,radius*2)
        painter.drawPie(circle,90*16,-round(360*16*min(1,remaining/max(.1,duration))));painter.restore()
        painter.setFont(QFont('Microsoft YaHei UI',13));painter.setPen(QColor('#ffffff'));painter.drawText(inner,Qt.AlignCenter,f'{remaining:.1f}')
    if hover:
        painter.setPen(Qt.NoPen);painter.setBrush(QColor(255,255,255,18));painter.drawRoundedRect(rect,5,5)
    font=QFont('Microsoft YaHei UI');font.setPixelSize(11);painter.setFont(font)
    text=painter.fontMetrics().elidedText(key_label(slot.key,compact=True),Qt.ElideRight,int(rect.width()+2))
    if 'key' in review:
        badge=QRectF(rect.left()+2,rect.top()-7,15,15)
        painter.setPen(QPen(QColor('#ffd994'),1));painter.setBrush(QColor('#8a4c1b'))
        painter.drawRoundedRect(badge,3,3)
        painter.setPen(QColor('#fff6db'));painter.drawText(badge,Qt.AlignCenter,'?')
    elif text:
        path=QPainterPath();path.addText(QPointF(rect.left()+2,rect.top()+3),font,text)
        painter.setPen(QPen(QColor('#090c0e'),2.2));painter.setBrush(QColor('#fff8e6'));painter.drawPath(path)
        painter.setPen(Qt.NoPen);painter.drawPath(path)
    if 'icon' in review and not art.isNull():
        painter.setFont(font);painter.setPen(QColor('#e3cb93'));painter.drawText(rect.adjusted(0,0,-3,-3),Qt.AlignBottom|Qt.AlignRight,'?')
    if ability:
        badge=QRectF(rect.left()+2,rect.bottom()-16,15,14)
        painter.setPen(QPen(QColor('#8ed8d6'),1));painter.setBrush(QColor('#17474b'))
        painter.drawRoundedRect(badge,3,3)
        painter.setPen(QColor('#d8fffa'));painter.drawText(badge,Qt.AlignCenter,'能')
    if matched:
        badge=QRectF(rect.right()-14,rect.bottom()-13,13,13)
        painter.setBrush(QColor('#dccb9c'));painter.setPen(Qt.NoPen);painter.drawEllipse(badge)
        painter.setPen(QColor('#263137'));painter.drawText(badge,Qt.AlignCenter,'✓')
    painter.restore()


def framed_icon(icons,name,size=60):
    result=QPixmap(size,size+2);result.fill(Qt.transparent)
    painter=QPainter(result);paint_slot(painter,fit_frame(QRectF(0,0,size,size+2)),icons,SkillSlot(icon=name));painter.end()
    return QIcon(result)


def navigation_icon(kind):
    result=QPixmap(18,18);result.fill(Qt.transparent);p=QPainter(result);p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor('#bfc5bf'),1.3));p.setBrush(Qt.NoBrush)
    if kind==0:
        for x in (3,10):
            for y in (3,10):p.drawRoundedRect(QRectF(x,y,5,5),1,1)
    elif kind==1:
        for x,height in ((3,6),(6,12),(9,8),(12,14),(15,5)):p.drawLine(QPointF(x,9-height/2),QPointF(x,9+height/2))
    elif kind==2:
        p.drawRoundedRect(QRectF(6,2,6,9),3,3);p.drawArc(QRectF(3,5,12,9),180*16,180*16);p.drawLine(9,14,9,17);p.drawLine(6,17,12,17)
    elif kind==4:
        p.drawRoundedRect(QRectF(2,2,14,13),2,2)
        p.drawLine(9,3,9,15);p.drawLine(4,6,7,6);p.drawLine(11,6,14,6)
    else:
        for y,x in ((4,6),(9,12),(14,8)):
            p.drawLine(2,y,16,y);p.fillRect(QRectF(x-2,y-2,4,4),QColor('#222629'));p.drawRoundedRect(QRectF(x-2,y-2,4,4),1,1)
    p.end();return QIcon(result)
