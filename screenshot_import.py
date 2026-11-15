"""Detect horizontal hotbars and replace their art with clear local PNG templates."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import cv2
import numpy as np
from PySide6.QtGui import QImage,QImageReader
from skillbar_model import contained_path
from screenshot_ocr import key_crop,parse_key_label,read_key_region


class RecognitionCancelled(Exception):pass


def read_image(path):
    reader=QImageReader(str(path));size=reader.size()
    if size.width()<=0 or size.height()<=0 or size.width()*size.height()>32_000_000:
        raise ValueError('无法读取截图，或图片过大；请使用清晰的 PNG/JPG 技能栏截图。')
    image=reader.read().convertToFormat(QImage.Format_RGBA8888)
    if image.isNull():raise ValueError('截图已损坏或格式不受支持。')
    data=np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.bytesPerLine())
    return data[:,:image.width()*4].reshape(image.height(),image.width(),4)[:,:,:3].copy()


def _fit_row(rects,image_width):
    side=float(np.median([min(w,h) for x,y,w,h in rects]))
    centers=sorted({round(x+w/2,1) for x,y,w,h in rects})
    best=None
    for start in centers:
        pitches={b-a for a,b in zip(centers,centers[1:]) if side*.9<b-a<side*1.55}
        for pitch in pitches:
            if start-side/2<0 or start+11*pitch+side/2>image_width:continue
            assigned=[]
            for column in range(12):
                nearest=min(centers,key=lambda value:abs(value-(start+column*pitch)))
                if abs(nearest-(start+column*pitch))<pitch*.18:assigned.append((column,nearest))
            if len(assigned)<10:continue
            fit=np.polyfit([p[0] for p in assigned],[p[1] for p in assigned],1)
            error=np.mean([abs(value-(fit[1]+column*fit[0])) for column,value in assigned])/pitch
            score=len(assigned)-error
            if best is None or score>best[0]:best=(score,float(fit[1]),float(fit[0]),side)
    return best


def _periodic_rows(gray,sizes):
    edges=cv2.dilate(cv2.Canny(gray,20,50).astype(np.float32)/255,np.ones((3,3),np.uint8))
    rows=[]
    for side in sizes:
        kernel=np.zeros((side,side),np.float32)
        kernel[5:-5,1]=1;kernel[5:-5,-2]=1;kernel[1,5:-5]=1;kernel[-2,5:-5]=1
        if kernel.sum()==0:continue
        response=cv2.matchTemplate(edges,kernel,cv2.TM_CCORR)/kernel.sum()
        for pitch in range(round(side*1.02),round(side*1.3)+1):
            valid=response.shape[1]-11*pitch
            if valid<1:continue
            combined=sum(response[:,column*pitch:column*pitch+valid] for column in range(12))/12
            values=combined.max(axis=1);starts=combined.argmax(axis=1)
            maximum=cv2.dilate(values[:,None],np.ones((max(3,round(side*.75)),1),np.uint8))[:,0]
            ys=np.flatnonzero((values>=maximum-1e-6)&(values>.89))
            selected=[]
            for y in sorted(ys,key=lambda y:values[y],reverse=True):
                if any(abs(y-old)<side*.75 for old in selected):continue
                selected.append(y)
                rows.append((float(y+side/2),float(values[y]*12),float(starts[y]+side/2),float(pitch),float(side)))
    return rows


def _selection(image,region):
    if image.ndim!=3 or min(image.shape[:2])<30:raise ValueError('截图尺寸过小。')
    if region is None:
        return image,0,0
    x,y,width,height=map(int,region)
    if min(width,height)<=0 or x<0 or y<0 or x+width>image.shape[1] or y+height>image.shape[0]:
        raise ValueError('框选区域超出截图。')
    return image[y:y+height,x:x+width],x,y


def detect_cells(image,region=None,*,max_rows=2):
    return _grid_candidates(image,region,max_rows)[0]


def _grid_candidates(image,region,max_rows):
    source,ox,oy=_selection(image,region)
    scale=min(1,2000/source.shape[1],1400/source.shape[0])
    if scale<1:
        smaller=cv2.resize(source,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
        try:
            selection=(0,0,smaller.shape[1],smaller.shape[0]) if region is not None else None
            candidates=_grid_candidates(smaller,selection,max_rows)
            return [[(round(ox+x/scale),round(oy+y/scale),round(w/scale),round(h/scale)) for x,y,w,h in cells]
                    for cells in candidates]
        except ValueError as exc:
            raise ValueError('未定位到技能栏，请框选清晰的技能栏再识别。') from exc
    gray=cv2.cvtColor(source,cv2.COLOR_RGB2GRAY)
    edges=cv2.Canny(gray,45,110)
    contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    maximum=min(240,source.shape[1]/9,source.shape[0]/1.5)
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if 20<=min(w,h)<=maximum and .82<w/h<1.2 and cv2.contourArea(contour)/(w*h)>.64:
            candidates.append((x,y,w,h))
    # Text and resource-cost overlays can break the otherwise rounded frame
    # contour. Recover squares from pairs of long vertical frame sides.
    sizes=[]
    widths=[w for x,y,w,h in candidates]
    for width in sorted(set(widths),key=lambda value:sum(abs(other-value)<=2 for other in widths),reverse=True):
        if not any(abs(width-old)<5 for old in sizes):sizes.append(width)
        if len(sizes)==4:break
    lines=cv2.HoughLinesP(edges,1,np.pi/180,12,minLineLength=14,maxLineGap=3)
    vertical=[]
    for line in ([] if lines is None else lines.reshape(-1,4)):
        x1,y1,x2,y2=map(int,line)
        if abs(x1-x2)<=2:vertical.append(((x1+x2)/2,min(y1,y2),abs(y1-y2)))
    for side in sizes:
        for x,y,length in vertical:
            if length<side*.35:continue
            for right,top,height in vertical:
                if abs(right-x-side)>2 or min(length,height)<side*.35 or abs((y+length/2)-(top+height/2))>side*.2:continue
                center=(y+length/2+top+height/2)/2
                candidates.append((round(x),round(center-side/2),side,side))
    rects=[]
    for rect in sorted(candidates,key=lambda r:r[2]*r[3],reverse=True):
        x,y,w,h=rect
        if not any(abs(x+w/2-(a+c/2))<w*.25 and abs(y+h/2-(b+d/2))<h*.25 and .7<w/c<1.4 for a,b,c,d in rects):rects.append(rect)
    groups=[]
    for rect in sorted(rects,key=lambda r:r[1]+r[3]/2):
        x,y,w,h=rect
        group=next((group for group in groups if abs(np.median([b+d/2 for a,b,c,d in group])-(y+h/2))<h*.23
                    and .75<h/np.median([d for a,b,c,d in group])<1.35),None)
        if group is None:groups.append([rect])
        else:group.append(rect)
    rows=[]
    for group in groups:
        if len(group)<10:continue
        fit=_fit_row(group,source.shape[1])
        if fit:
            score,start,pitch,side=fit
            center=float(np.median([y+h/2 for x,y,w,h in group]))
            rows.append((center,score,start,pitch,side))
    if len(rows)<max_rows:
        periodic=_periodic_rows(gray,sizes)
        if periodic:
            best_side=max(periodic,key=lambda row:row[1])[4]
            periodic=[row for row in periodic if abs(row[4]-best_side)<best_side*.15]
            selected=[]
            for row in sorted(periodic,key=lambda row:row[1],reverse=True):
                if not any(abs(row[0]-old[0])<best_side*.7 for old in [*rows,*selected]):selected.append(row)
            rows.extend(selected)
    pairs=[]
    for upper in rows:
        for lower in rows:
            if upper[0]>=lower[0]:continue
            if abs(upper[2]-lower[2])<upper[3]*.3 and abs(upper[3]-lower[3])<upper[3]*.1 and upper[4]*.9<lower[0]-upper[0]<upper[4]*5:
                pairs.append((upper,lower))
    if pairs:
        grids=list(pairs)
        if max_rows==3:
            above={}
            for first,second in pairs:
                above.setdefault(second,[]).append(first)
            for middle,bottom in pairs:
                grids.extend((top,middle,bottom) for top in above.get(middle,())
                             if abs((middle[0]-top[0])-(bottom[0]-middle[0]))<middle[4]*.8)
        # Keep plausible layouts of different sizes. A background pattern can
        # be geometrically valid without containing any skill icons.
        by_position=sorted(grids,key=lambda group:(group[-1][0],len(group),group[-2][0],sum(row[1] for row in group)),reverse=True)
        by_support=sorted(grids,key=lambda group:(len(group),sum(row[1] for row in group)),reverse=True)
        by_size=sorted(grids,key=lambda group:(min(row[4] for row in group),len(group),sum(row[1] for row in group)),reverse=True)
        shortlist=dict.fromkeys(group for ranking in (by_position,by_support,by_size) for group in ranking[:3])
        return [[(round(ox+row[2]+column*row[3]-row[4]/2),round(oy+row[0]-row[4]/2),round(row[4]),round(row[4]))
                 for row in grid for column in range(12)] for grid in shortlist]
    if region is not None:
        pitch=source.shape[1]/12;side=pitch*.93
        if pitch>=18 and 1.7*side<=source.shape[0]<=5*side:
            return [[(round(ox+column*pitch+(pitch-side)/2),round(oy+row*(source.shape[0]-side)),round(side),round(side))
                     for row in range(2) for column in range(12)]]
    raise ValueError('未找到每排 12 格的技能栏。请框选技能栏的外框后重试。')


@dataclass
class IconMatch:
    icon:str|None
    confidence:float
    candidate:str|None=None


def _feature(image):
    tile=cv2.resize(image,(32,32),interpolation=cv2.INTER_AREA)[7:26,4:28].astype(np.float32).ravel()/255
    tile-=tile.mean();norm=float(np.linalg.norm(tile))
    return tile/max(norm,1e-6),norm/np.sqrt(len(tile))


class IconMatcher:
    def __init__(self,root,files,cancelled=lambda:False):
        self.names=[];vectors=[];seen=set()
        for name in sorted(files):
            if cancelled():raise RecognitionCancelled()
            path=contained_path(root,name)
            try:image=read_image(path)
            except ValueError:continue
            signature=hashlib.sha256(image.tobytes()).digest()
            if signature in seen:continue
            seen.add(signature);feature,variance=_feature(image)
            if variance<.02:continue
            self.names.append(name);vectors.append(feature)
        if not vectors:raise ValueError('图标素材库为空或无法读取。')
        self.vectors=np.asarray(vectors,np.float32)

    def match(self,image):
        if image.size==0:return IconMatch(None,0)
        scores=None
        for inset in (0,.035,.065):
            dx=round(image.shape[1]*inset);dy=round(image.shape[0]*inset)
            crop=image[dy:image.shape[0]-dy or None,dx:image.shape[1]-dx or None]
            feature,variance=_feature(crop)
            if variance<.025:continue
            values=self.vectors@feature
            scores=values if scores is None else np.maximum(scores,values)
        if scores is None:return IconMatch(None,0)
        # Refine the leading candidates for a 1–2 px HUD frame/crop offset.
        candidates=np.argsort(scores)[-8:]
        samples=[]
        for inset in (0,.035,.065):
            tile=cv2.resize(image,(32,32),interpolation=cv2.INTER_AREA)
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    border=round(inset*32)
                    shifted=cv2.warpAffine(tile,np.float32([[1,0,dx],[0,1,dy]]),(32,32),borderMode=cv2.BORDER_REFLECT)
                    samples.append(_feature(shifted[border:32-border or None,border:32-border or None])[0])
        refined=np.asarray(samples)@self.vectors[candidates].T
        scores[candidates]=np.maximum(scores[candidates],refined.max(axis=0))
        order=np.argsort(scores)[::-1];first=int(order[0]);score=float(scores[first])
        margin=score-float(scores[order[1]]) if len(order)>1 else score
        name=self.names[first]
        return IconMatch(name if score>=.82 and margin>=.035 else None,max(0,score),name)


@dataclass
class VisualResult:
    key:str=''
    icon:str|None=None
    review:tuple=()
    confidence:float=0
    raw_key:str=''
    key_candidates:tuple=()
    source_rect:tuple|None=None


@dataclass
class ImportAnalysis:
    cells:list
    visuals:list
    warning:str=''


def _select_grid(image,region,max_rows,matcher,cancelled):
    source,ox,oy=_selection(image,region)
    height,width=source.shape[:2]
    cache={}
    seen_scales=set()
    best=None
    for requested_scale in (1,1.25,1.5,.8,.67):
        if cancelled():raise RecognitionCancelled()
        scale=min(requested_scale,2000/width,1400/height)
        if scale in seen_scales:
            continue
        seen_scales.add(scale)
        view=source if scale==1 else cv2.resize(source,None,fx=scale,fy=scale,
                                               interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR)
        selection=(0,0,view.shape[1],view.shape[0]) if region is not None else None
        try:
            candidates=_grid_candidates(view,selection,max_rows)
        except ValueError:
            continue
        scale_x,scale_y=view.shape[1]/width,view.shape[0]/height
        for candidate in candidates:
            cells=[(round(ox+x/scale_x),round(oy+y/scale_y),round(w/scale_x),round(h/scale_y))
                   for x,y,w,h in candidate]
            matches=[]
            for cell in cells:
                if cancelled():raise RecognitionCancelled()
                if cell not in cache:
                    x,y,w,h=cell
                    cache[cell]=matcher.match(image[max(0,y):y+h,max(0,x):x+w])
                matches.append(cache[cell])
            row_hits=[sum(bool(match.icon) for match in matches[i:i+12]) for i in range(0,len(matches),12)]
            confirmed_rows=sum(hits>=2 for hits in row_hits)
            score=(confirmed_rows==len(row_hits),confirmed_rows,sum(row_hits),
                   sum(match.confidence for match in matches if match.icon))
            if best is None or score>best[0]:
                best=(score,cells,matches)
        if best and best[0][0] and best[0][1]==max_rows and best[0][2]>=7*max_rows:
            break
    if best is None:
        raise ValueError('未找到每排 12 格的技能栏。请框选完整的技能栏后重试。')
    return best[1],best[2]


def analyze_screenshot(path,catalog,region=None,cancelled=lambda:False,progress=lambda text:None,key_reader=None,*,max_rows=3):
    if cancelled():raise RecognitionCancelled()
    image=read_image(path)
    progress('加载清晰图标素材…');matcher=IconMatcher(catalog.root,catalog.files,cancelled)
    progress('定位技能格并核对图标…')
    cells,matches=_select_grid(image,region,max_rows,matcher,cancelled)
    result = _read_visuals(image,cells,matches,cancelled,progress,key_reader)
    if not any(visual.icon or visual.key for visual in result.visuals):
        raise ValueError('没有找到可信的技能图标或键位。请重新框选完整的技能栏。')
    return result


def _read_visuals(image,cells,matches,cancelled,progress,key_reader=None):
    visuals=[];labels=[]
    for (x,y,w,h),match in zip(cells,matches):
        if cancelled():raise RecognitionCancelled()
        visuals.append(VisualResult(icon=match.icon,review=() if match.icon else ('icon',),confidence=match.confidence))
        left,top,width,height = key_crop(image,(x,y,w,h))
        labels.append(image[top:top+height,left:left+width])
    progress('识别按键文字…')
    warning=''
    if key_reader is None:
        raw=[]
        for cell,visual in zip(cells,visuals):
            if cancelled():raise RecognitionCancelled()
            label,visual.key_candidates,visual.source_rect=read_key_region(image,cell)
            raw.append(label)
    else:
        raw,warning=key_reader(labels,cancelled)
    if len(raw)!=len(cells):raise ValueError('键位识别返回的格子数量不正确，请重新识别。')
    seen={}
    for index,(visual,text) in enumerate(zip(visuals,raw)):
        visual.raw_key=text;visual.key=parse_key_label(text)
        if not visual.key:visual.review+=('key',)
        elif visual.key in seen:
            previous=visuals[seen[visual.key]];previous.key='';previous.review+=('key',)
            visual.key='';visual.review+=('key',)
        else:seen[visual.key]=index
    if cancelled():raise RecognitionCancelled()
    return ImportAnalysis(cells,visuals,warning)
