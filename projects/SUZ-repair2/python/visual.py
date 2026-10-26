"""Deterministic screenshot-derived diagnostics and a separate warning overlay.

Raw observations are never modified. Derived images have an explicit provenance
label and are excluded from Monitor/Critic evidence and native OpenCUA history.
"""
import base64
import hashlib
import io
import math
from PIL import Image, ImageDraw, ImageChops, ImageStat


def _open(data):
    image=Image.open(io.BytesIO(data));image.load()
    return image.convert('RGB')


def _png(image):
    stream=io.BytesIO();image.save(stream,format='PNG');return stream.getvalue()


def image_metrics(current, previous=None):
    image=_open(current)
    result={'width':image.width,'height':image.height,
            'pixel_sha256':hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest(),
            'measure':'RGB thumbnail absolute difference; not semantic progress or SSIM'}
    if previous is not None:
        prior=_open(previous)
        if prior.size==image.size:
            a=prior.resize((128,128),Image.Resampling.BILINEAR)
            b=image.resize((128,128),Image.Resampling.BILINEAR)
            diff=ImageChops.difference(a,b)
            result['mean_absolute_difference']=sum(ImageStat.Stat(diff).mean)/(3*255)
            channels=diff.split()
            maximum=ImageChops.lighter(channels[0],ImageChops.lighter(channels[1],channels[2]))
            result['changed_pixel_fraction']=sum(maximum.histogram()[25:])/(128*128)
    return result


def _box(value):
    if not isinstance(value,list) or len(value)!=4 or not all(isinstance(v,(float,int)) and math.isfinite(v) and 0<=v<=1 for v in value):
        raise ValueError('normalized box required')
    if value[2]<=value[0] or value[3]<=value[1]:raise ValueError('empty box')
    return value


def render_overlay(original, warnings, frame_id):
    """Return a SAME-SIZE transparent overlay copy, never overwrite raw bytes."""
    raw_sha=hashlib.sha256(original).hexdigest();image=_open(original).convert('RGBA')
    layer=Image.new('RGBA',image.size,(0,0,0,0));draw=ImageDraw.Draw(layer)
    used=[]
    for warning in warnings:
        if warning.get('status')!='active' or warning.get('anchor_sha256')!=raw_sha:continue
        b=_box(warning['box']);x0,y0,x1,y1=[round(v*s) for v,s in zip(b,[image.width,image.height,image.width,image.height])]
        red=warning['style']=='red_cross';color=(220,30,45,190) if red else (220,150,0,190)
        draw.rectangle((x0,y0,x1,y1),outline=color,width=2)
        if red:
            draw.line((x0,y0,x1,y1),fill=(220,30,45,125),width=3)
            draw.line((x0,y1,x1,y0),fill=(220,30,45,125),width=3)
        label=warning['id'];yy=max(0,y0-16)
        draw.rectangle((x0,yy,min(image.width,x0+36),yy+14),fill=(255,255,255,235))
        draw.text((x0+2,yy),label,fill=color)
        used.append(label)
    if not used:return None
    return {'bytes':_png(Image.alpha_composite(image,layer).convert('RGB')),
        'metadata':{'kind':'derived_warning_overlay','source_frame':frame_id,'source_sha256':raw_sha,
                    'warning_ids':used,'coordinate_space':'same pixel dimensions as unmodified source',
                    'semantics':'SUZ annotations, not actual UI; conditional warning, clicks remain allowed'}}


def diagnostic_crops(images, evidence):
    """Two enlarged views of the latest clicked region, with explicit source coordinates."""
    if not evidence:return []
    latest=list(evidence.values())[-1];points=latest.get('action',{}).get('points',[])
    if not points:return []
    point=points[-1];x,y=point['x'],point['y']
    box=[max(0,x-.1),max(0,y-.1),min(1,x+.1),min(1,y+.1)]
    views=[]
    for frame_id in latest['frame_ids']:
        frame=next((f for f in images if f['id']==frame_id),None)
        if frame is None:continue
        raw=base64.b64decode(frame['dataUrl'].split(',',1)[1]);image=_open(raw)
        rect=(int(box[0]*image.width),int(box[1]*image.height),max(int(box[0]*image.width)+1,int(box[2]*image.width)),max(int(box[1]*image.height)+1,int(box[3]*image.height)))
        crop=image.crop(rect);crop.thumbnail((320,320))
        scale=min(2,640/max(crop.size));crop=crop.resize((max(1,int(crop.width*scale)),max(1,int(crop.height*scale))))
        views.append({'bytes':_png(crop),'metadata':{'kind':'diagnostic_crop','source_frame':frame_id,
            'source_sha256':hashlib.sha256(raw).hexdigest(),'box':box,'point':point,
            'semantics':'enlarged raw crop, not a full-screen action coordinate system'}})
    return views
