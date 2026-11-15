"""Radial paging in logical widget coordinates."""
import math
from skillbar_model import COLUMNS, LEGACY_SLOTS, SLOT_COUNT

PAGE_SIZE = 8
PAGE_COUNT = math.ceil(SLOT_COUNT / PAGE_SIZE)
LEGACY_ORDER=list(range(COLUMNS,LEGACY_SLOTS))+list(range(COLUMNS))
DEFAULT_ORDER=LEGACY_ORDER+list(range(LEGACY_SLOTS,SLOT_COUNT))


def validate_order(value):
    if not isinstance(value,(list,tuple)) or any(type(i) is not int for i in value):
        raise ValueError('轮盘顺序无效。')
    if sorted(value)==list(range(LEGACY_SLOTS)):
        return list(value)+list(range(LEGACY_SLOTS,SLOT_COUNT))
    if sorted(value)!=list(range(SLOT_COUNT)):
        raise ValueError('轮盘顺序必须包含每个技能格一次。')
    return list(value)


def radii(size):return size*.15,size*.43


def slot_center(sector,size):
    radius=size*.302;angle=math.radians(sector*45)
    return size/2+radius*math.sin(angle),size/2-radius*math.cos(angle)


def hit_slot(x,y,size,page,order):
    dx,dy=x-size/2,y-size/2;radius=math.hypot(dx,dy);inner,outer=radii(size)
    # Relative-pointer clamping produces exact radii; translating by the centre
    # can add a few ulps. This subpixel tolerance prevents dead directions.
    if not inner-1e-6<=radius<=outer+1e-6 or not 0<=page<PAGE_COUNT:return None
    sector=int(((math.degrees(math.atan2(dx,-dy))+22.5)%360)//45)
    index=page*PAGE_SIZE+sector
    return order[index] if index<len(order) else None


class WheelSteps:
    def __init__(self):self.clear()
    def clear(self):self.pending=0
    def add(self,delta):
        self.pending+=delta;steps=math.trunc(self.pending/120);self.pending-=steps*120
        return -steps
