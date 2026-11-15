"""Offline, constrained recognition of FF14's white c/a/s hotkey labels."""
import re
from collections import Counter
from skillbar_model import canonical_key


def parse_key_label(text):
    text=re.sub(r'\s+','',str(text)).lower().replace('control','ctrl')
    if not text:return ''
    if '+' not in text and len(text)>1 and text[0] in 'cas' and not text.startswith(('ctrl','alt','shift')):
        text={'c':'ctrl','a':'alt','s':'shift'}[text[0]]+'+'+text[1:]
    text=re.sub(r'(^|\+)m([45])$',r'\1mouse_\2',text)
    try:return canonical_key(text)
    except ValueError:return ''


def recognize_keys(images,cancelled=lambda:False):
    from screenshot_glyphs import reader
    from screenshot_import import RecognitionCancelled
    glyphs = reader()
    labels=[]
    for image in images:
        if cancelled():raise RecognitionCancelled()
        label,score,candidates=glyphs.read(image) if glyphs is not None and image.size else ('',0,[])
        labels.append(label)
    return labels,''


def key_crop(image, cell, dx=0, dy=0, width_delta=0):
    x,y,w,h = cell
    left = max(0,x-2+dx)
    top = max(0,y-round(h*.25)+dy)
    right = min(image.shape[1],x+w+dx+width_delta)
    bottom = min(image.shape[0],y+round(h*.18)+dy)
    return (left,top,max(0,right-left),max(0,bottom-top))


def read_key_region(image, cell):
    from screenshot_glyphs import reader
    # The frame finder follows the icon. The small text is offset from that frame.
    # Read nearby positions and widths, retaining the original pixels in each.
    step = max(1, round((cell[2]-40)/10)+1)
    offsets = [(0,0,0),(-1,-1,0),(1,-1,0),(-1,1,0),(1,1,0),(-1,0,0),
               (0,1,1),(0,-1,1),(0,0,-1),(0,0,1)]
    rects = [key_crop(image,cell,dx*step,dy*step,dw*step) for dx,dy,dw in offsets]
    crops = [image[y:y+h,x:x+w] for x,y,w,h in rects]
    small_text=rects[0][3]<18
    left,top,_,_=rects[0]
    x,y,w,h=cell
    source_rect=(left,top,min(image.shape[1],x+w)-left,min(image.shape[0],y+h)-top)
    glyphs=reader()
    if glyphs is None:
        return '',(),source_rect
    results = glyphs.read_many(crops,min_height=14,calibrated=True)
    votes = Counter(label for label,_,_ in results if label)
    accepted = '' if small_text else results[0][0]
    leaders = votes.most_common()
    if leaders:
        label,count = leaders[0]
        if count>=(4 if small_text else 3) and (len(leaders)==1 or count>=leaders[1][1]+2):
            accepted = label
        elif accepted and len(leaders)>1:
            accepted = ''
    strongest = {}
    rank_votes = Counter(ranked[0][0] for _,_,ranked in results if ranked)
    for _,_,ranked in results:
        for name,score in ranked:
            strongest[name] = max(score,strongest.get(name,0.0))
    ordered = sorted(strongest,key=strongest.get,reverse=True)
    if not accepted and len(ordered)>=2 and not small_text:
        best,second=ordered[:2]
        # Verify that the strongest HUD match wins across several nearby crops,
        # even if each individual crop falls short of the generic acceptance rule.
        if (best in glyphs.hud_names and rank_votes[best]>=5 and strongest[best]>=.65
                and strongest[best]-strongest[second]>=.035):
            accepted=best
    candidates=tuple(dict.fromkeys(parse_key_label(name) for name in ordered
                                   if strongest[name]>=.52 and parse_key_label(name)))[:2]
    return accepted,candidates,source_rect
