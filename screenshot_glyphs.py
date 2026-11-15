"""Constrained glyph recognition for the small c/a/s labels used by FF14."""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np


class GlyphReader:
    def __init__(self,path):
        with np.load(path,allow_pickle=False) as data:
            self.names=data['names'].tolist()
            self.patterns=data['patterns'].reshape(len(self.names),-1)
            self.regions=data['regions'].reshape(len(self.names),-1)
        self.base_count=len(self.names)
        self.hud_names=frozenset()
        reference=path.with_name('hud-key-labels.npz')
        if reference.is_file():
            with np.load(reference,allow_pickle=False) as data:
                names=data['names'].tolist()
                self.hud_names=frozenset(names)
                self.names.extend(names)
                self.patterns=np.concatenate((self.patterns,data['patterns'].reshape(len(names),-1)))
                self.regions=np.concatenate((self.regions,data['regions'].reshape(len(names),-1)))
        self.ink=self.patterns.sum(axis=1)

    def read(self,image):
        return self.read_many([image])[0]

    def read_many(self, images, *, min_height=18, calibrated=False):
        observed = [self._observe(image) if image.shape[0]>=min_height and image.shape[1]>0 else None
                    for image in images]
        shifts = [(dx,dy) for dy in (-2,-1,0,1,2) for dx in (-1,0,1,2)]
        masks = [cv2.warpAffine(mask,np.float32([[1,0,dx],[0,1,dy]]),(52,24)).ravel()
                 for mask in observed if mask is not None for dx,dy in shifts]
        if not masks:
            return [('',0,[]) for image in images]
        pixels = np.asarray(masks,dtype=np.float32).T
        template_count = len(self.names) if calibrated else self.base_count
        overlap = self.patterns[:template_count] @ pixels
        count = self.regions[:template_count] @ pixels
        scores = (2*overlap/(self.ink[:template_count,None]+count+1e-6)).reshape(template_count,-1,len(shifts)).max(axis=2)
        columns = iter(scores.T)
        return [self._rank(mask,next(columns)) if mask is not None else ('',0,[]) for mask in observed]

    @staticmethod
    def _observe(image):
        # Enlarging an undersized label does not restore its missing strokes.
        image=cv2.resize(image,(52,22),interpolation=cv2.INTER_CUBIC)
        maximum=image.max(axis=2).astype(float);minimum=image.min(axis=2).astype(float)
        observed=np.clip((minimum-155)/80,0,1)*(maximum-minimum<90)
        return cv2.copyMakeBorder(observed,0,2,0,0,cv2.BORDER_CONSTANT)

    def _rank(self, observed, best_scores):
        ranked={}
        for name,score in zip(self.names,best_scores):ranked[name]=max(ranked.get(name,0),float(score))
        order=sorted(ranked,key=ranked.get,reverse=True)
        first,second=order[:2];score=ranked[first];margin=score-ranked[second]
        # A modifier prefix is smaller and lower than an ordinary uppercase key.
        # Do not accept the prefix alone as a bare C/A/S when its base is unreadable.
        pixels=np.argwhere(observed[:,:19]>.5)
        plausible=not (len(first)==1 and first.isalpha() and len(pixels) and pixels[:,0].min()>10)
        minimum=.75 if len(first)==1 and first.isalnum() else .61
        accepted=score>=minimum and margin>=(.022 if score>=.8 else .035) and plausible
        return (first if accepted else ''),score,[(name,round(ranked[name],3)) for name in order[:3]]


@lru_cache(maxsize=1)
def reader():
    path=Path(__file__).resolve().parent/'assets'/'ocr'/'key-glyphs.npz'
    return GlyphReader(path) if path.is_file() else None
