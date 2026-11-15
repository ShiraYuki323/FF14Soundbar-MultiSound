"""Build a small offline glyph bank for FF14 hotkey labels, not screenshot answers."""
import argparse
import os
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageFont,ImageDraw


def build(source,output):
    font_dir=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    fonts=[ImageFont.truetype(str(font_dir/name),40) for name in ('arial.ttf','arialbd.ttf','segoeui.ttf','tahoma.ttf') if (font_dir/name).exists()]
    if not fonts:raise RuntimeError('缺少用于生成识别模板的本地字体。')
    sprite=cv2.imdecode(np.fromfile(Path(source)/'16 字体 字母 数字'/'miedinger_number_hr1.png',np.uint8),cv2.IMREAD_UNCHANGED)
    alpha=sprite[:,:,3];alpha=(alpha/257).astype(np.uint8) if alpha.dtype==np.uint16 else alpha
    count,labels,stats,_=cv2.connectedComponentsWithStats((alpha>80).astype(np.uint8))
    boxes=sorted([tuple(rect) for rect in stats[1:] if rect[3]>40 and rect[4]>500])
    digits={str(index):alpha[y:y+h,x:x+w] for index,(x,y,w,h,area) in enumerate(boxes[:10])}
    names=[];patterns=[];regions=[]
    bases=list('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-=')+[f'F{i}' for i in range(1,25)]+['M4','M5']
    # Silhouettes traced from the in-game c prefix and F-key label.
    game_letters={
        'c': ('..####.','.##..##','##.....','##.....','##.....','.##..##','..####.'),
        'F': ('######','##....','##....','##....','#####.','##....','##....','##....','##....'),
    }
    for font in fonts:
        cap=-font.getbbox('H',anchor='ls')[1]
        def glyph(char,use_game,height):
            if use_game and char in digits:
                image=digits[char];h=height;w=round(image.shape[1]*h/image.shape[0]);return cv2.resize(image,(w,h)), -h
            box=font.getbbox(char,anchor='ls');w=max(1,box[2]-box[0]);h=max(1,box[3]-box[1])
            image=Image.new('L',(w,h));ImageDraw.Draw(image).text((-box[0],-box[1]),char,font=font,fill=255,anchor='ls')
            return cv2.resize(np.asarray(image),(max(1,round(w*height/cap)),max(1,round(h*height/cap)))),round(box[1]*height/cap)
        for height in (9,10,11,12,13):
          for game_digits in (False,True):
              for prefix in ('','c','a','s'):
                  for base in bases:
                      canvas=np.zeros((24,52),np.float32);x=3
                      for char in prefix+base:
                          image,top=glyph(char,game_digits and char.isdigit(),height)
                          y=20+top-(3 if char in '-=' else 0);h,w=image.shape
                          if x+w>=52 or y<0 or y+h>24:break
                          canvas[y:y+h,x:x+w]=np.maximum(canvas[y:y+h,x:x+w],image/255)
                          x+=w+1
                      else:
                          region=np.zeros_like(canvas);region[7:22,2:min(52,max(19,x+1))]=1
                          names.append(prefix+base);patterns.append(canvas);regions.append(region)
    for prefix,base in ([(p,b) for p in ('c','a','s') for b in '0123456789-=']
                        +[('',f'F{i}') for i in range(1,25)]):
        for height in range(8,15):
            canvas=np.zeros((24,52),np.float32)
            x=3
            for char in prefix+base:
                if char in game_letters:
                    mask=np.array([[255 if pixel=='#' else 0 for pixel in row]
                                   for row in game_letters[char]],dtype=np.uint8)
                    target=height if char=='F' else round(height*.72)
                    w=max(1,round(mask.shape[1]*target/mask.shape[0]))
                    image=cv2.resize(mask,(w,target),interpolation=cv2.INTER_AREA)
                    top=-target
                else:
                    image,top=glyph(char,True,height)
                y=20+top-(3 if char in '-=' else 0)
                h,w=image.shape
                if x+w>=52 or y<0 or y+h>24:break
                canvas[y:y+h,x:x+w]=image/255
                x+=w+1
            else:
                region=np.zeros_like(canvas);region[7:22,2:min(52,max(19,x+1))]=1
                names.append(prefix+base);patterns.append(canvas);regions.append(region)

    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output/'key-glyphs.npz',names=np.asarray(names),patterns=np.asarray(patterns,np.float32),regions=np.asarray(regions,np.float32))
    print(f'{len(names)} generic key-label glyph templates generated')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('output');args=parser.parse_args();build(args.source,args.output)
