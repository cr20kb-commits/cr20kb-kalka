"""Full-resolution pair comparison using the same masks for display and export."""
from contextlib import ExitStack
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps
import kalka_core as core
from kalka_export import Page, _corners, _metadata, _transform

MAX_PAIR_PIXELS = 25_000_000
BLUE, RED, PURPLE = (21, 101, 192), (211, 47, 47), (106, 27, 154)


def _shift(image, dx, dy):
    result = Image.new('L', image.size, 0)
    result.paste(image, (dx, dy))
    return result


def _register_translation(a, b):
    """Correct only a well-supported, sheet-wide integer shift of at most 2 px.

    The scoring mask is independent of the difference threshold. It estimates
    a single translation; the full greyscale masks remain the comparison data.
    Sparse or ambiguous drawings are left untouched.
    """
    am = a.point(lambda p: 255 if p >= 64 else 0)
    bm = b.point(lambda p: 255 if p >= 64 else 0)
    if min(am.histogram()[255], bm.histogram()[255]) < 1000:
        return b, (0, 0)
    scores = []
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            shifted = _shift(bm, dx, dy)
            score = ImageChops.difference(am, shifted).histogram()[255]
            scores.append((score, dx, dy))
    scores.sort()
    best, dx, dy = scores[0]
    zero = next(score for score, x, y in scores if x == y == 0)
    if (dx, dy) == (0, 0) or best * 5 >= zero or scores[1][0] - best < max(100, zero // 20):
        return b, (0, 0)
    before = ImageChops.difference(am, bm)
    after = ImageChops.difference(am, _shift(bm, dx, dy))
    w, h = am.size
    # Evidence must be distributed over the sheet, not just a changed digit.
    supported = 0
    for x0, y0, x1, y1 in ((0,0,w//2,h//2), (w//2,0,w,h//2),
                           (0,h//2,w//2,h), (w//2,h//2,w,h)):
        old = before.crop((x0,y0,x1,y1)).histogram()[255]
        new = after.crop((x0,y0,x1,y1)).histogram()[255]
        if old >= 100 and new * 2 < old:
            supported += 1
    if supported < 3:
        return b, (0, 0)
    return _shift(b, dx, dy), (dx, dy)


def _register_fractional(a, b, path, layer, box, reference):
    """Try correcting the sampling phase before interpolation, if well supported."""
    delta = [reference[k] - layer[k] for k in ('x', 'y')]
    fraction = [v - round(v) for v in delta]
    if all(abs(v) < 1e-9 for v in fraction):
        return _register_translation(a, b)
    shifted_layer = dict(layer)
    for key, value in zip(('x', 'y'), fraction):
        shifted_layer[key] += value
    candidate = _mask(path, shifted_layer, box)
    candidate, integer = _register_translation(a, candidate)
    binary = lambda im: im.point(lambda p: 255 if p >= 64 else 0)
    am, bm, cm = binary(a), binary(b), binary(candidate)
    if min(am.histogram()[255], bm.histogram()[255]) < 1000:
        return _register_translation(a, b)
    before, after = ImageChops.difference(am, bm), ImageChops.difference(am, cm)
    old, new = before.histogram()[255], after.histogram()[255]
    if old < 500 or new * 5 >= old:
        return _register_translation(a, b)
    w, h = am.size
    supported = 0
    for part in ((0,0,w//2,h//2), (w//2,0,w,h//2),
                 (0,h//2,w//2,h), (w//2,h//2,w,h)):
        prior = before.crop(part).histogram()[255]
        current = after.crop(part).histogram()[255]
        if prior >= 100 and current * 2 < prior:
            supported += 1
    if supported < 3:
        return _register_translation(a, b)
    return candidate, tuple(round(f+i, 8) for f,i in zip(fraction, integer))


def _mask(path, layer, box):
    left, top, right, bottom = box
    width, height = round(right-left), round(bottom-top)
    with ExitStack() as stack:
        page = Page(path, layer, stack)
        if page.width * page.height > MAX_PAIR_PIXELS:
            raise ValueError('Страница сравнения превышает 25 Мп; уменьшите DPI.')
        image = page.crop(0, 0, page.width, page.height)
        try:
            rgba = image.convert('RGBA')
            r,g,b,opacity = rgba.split()
            # Saturated light colours (e.g. yellow) are still drawing content.
            alpha = ImageOps.invert(ImageChops.darker(ImageChops.darker(r,g),b))
            alpha = ImageChops.multiply(alpha,opacity)
            alpha = alpha.point(lambda x: x if x >= 32 and 255-x < layer['threshold'] else 0)
            rgba.close()
        finally:
            image.close()
    # Suppress light paper and modest JPEG noise while retaining antialiased ink.
    c, s, scale = _transform(layer)
    gx, gy = left-layer['x'], top-layer['y']
    coeff = (c/scale, s/scale, (c*gx+s*gy)/scale,
             -s/scale, c/scale, (-s*gx+c*gy)/scale)
    return alpha.transform((width, height), Image.Transform.AFFINE, coeff,
                           resample=Image.Resampling.BILINEAR, fillcolor=0)


def regions(diff, width, height):
    """Group nearby changed pixels by connected runs, without discarding tiny marks."""
    pixels = diff.tobytes()
    parent, boxes = [], []
    previous = []
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for y in range(height):
        row = pixels[y*width:(y+1)*width]
        runs, x = [], 0
        while x < width:
            x = row.find(b'\xff', x)
            if x < 0: break
            end = row.find(b'\x00', x)
            if end < 0: end = width
            idx = len(parent); parent.append(idx); boxes.append([x,y,end,y+1])
            runs.append((x,end,idx)); x = end
        if len(parent) > 500000:
            raise ValueError('Слишком много фрагментов: проверьте совмещение и качество изображения.')
        j = 0
        for x0,x1,idx in runs:
            while j < len(previous) and previous[j][1] < x0-1: j += 1
            k = j
            while k < len(previous) and previous[k][0] <= x1+1:
                a,b = root(idx),root(previous[k][2])
                if a != b: parent[b] = a
                k += 1
        previous = runs
    combined = {}
    for i, box in enumerate(boxes):
        r = root(i)
        if r not in combined: combined[r] = box[:]
        else:
            b=combined[r]; b[0]=min(b[0],box[0]); b[1]=min(b[1],box[1]); b[2]=max(b[2],box[2]); b[3]=max(b[3],box[3])
    found = list(combined.values())
    if len(found) > 4000:
        raise ValueError('Слишком много областей: проверьте совмещение и качество изображения.')
    # Merge locally neighbouring fragments of a character/number. Long lines
    # are not widened into bridges, avoiding distant edits merging through them.
    changed=True
    while changed:
        changed=False; out=[]
        for b in sorted(found, key=lambda v:(v[1],v[0])):
            for a in out:
                if max(a[2]-a[0],a[3]-a[1],b[2]-b[0],b[3]-b[1]) > 180: continue
                if b[0]<=a[2]+8 and b[2]>=a[0]-8 and b[1]<=a[3]+8 and b[3]>=a[1]-8:
                    a[0]=min(a[0],b[0]);a[1]=min(a[1],b[1]);a[2]=max(a[2],b[2]);a[3]=max(a[3],b[3]);changed=True;break
            else: out.append(b[:])
        found=out
    return sorted(found,key=lambda v:(v[1],v[0]))


def compare(entries):
    if len(entries)!=2: raise ValueError('Выберите две редакции.')
    points=[]
    for path, layer in entries:
        core.validate_layer(layer)
        if layer['threshold'] == 0:
            raise ValueError('Порог фона 0 удаляет всё изображение. Для сравнения установите 1–255 в обоих слоях.')
        w,h=_metadata(path,layer)
        points.extend(_corners(layer,w,h))
    # For untranslated unit-scale rasters, sample on A's pixel grid so that a
    # fractional A position does not blur both images and erase fine edits.
    reference=entries[0][1]
    axis_aligned=all(layer['angle']==0 and layer['scale']==1 for _,layer in entries)
    phase_x=reference['x']-math.floor(reference['x']) if axis_aligned else 0
    phase_y=reference['y']-math.floor(reference['y']) if axis_aligned else 0
    box=(math.floor(min(p[0] for p in points)-phase_x)+phase_x,
         math.floor(min(p[1] for p in points)-phase_y)+phase_y,
         math.ceil(max(p[0] for p in points)-phase_x)+phase_x,
         math.ceil(max(p[1] for p in points)-phase_y)+phase_y)
    w,h=round(box[2]-box[0]),round(box[3]-box[1])
    if w<1 or h<1 or w*h>MAX_PAIR_PIXELS:
        raise ValueError('Поле сравнения превышает 25 Мп; уменьшите DPI или проверьте совмещение.')
    a,b=(_mask(path,layer,box) for path,layer in entries)
    if axis_aligned:
        b, correction = _register_fractional(a, b, entries[1][0], entries[1][1], box, reference)
    else:
        b, correction = _register_translation(a, b)
    common=ImageChops.darker(a,b)
    only_a=ImageChops.subtract(a,b);only_b=ImageChops.subtract(b,a)
    canvas=Image.new('RGB',(w,h),'white')
    for color,mask in ((BLUE,only_a),(RED,only_b),(PURPLE,common)):
        canvas.paste(color,(0,0,w,h),mask)
    diff=ImageChops.difference(a,b).point(lambda x: 255 if x>=56 else 0)
    found=regions(diff,w,h)
    return canvas, {'bounds':list(box),'regions':found,'translation_correction':list(correction),
                    'alignment_checked':all(layer['aligned'] for _,layer in entries)}


def mark(image, regions):
    output=image.copy(); draw=ImageDraw.Draw(output)
    # Outlines are unfilled; sizes scale with the full-resolution sheet.
    stroke=max(2,round(min(image.size)/700)); pad=max(4,stroke*3)
    for x0,y0,x1,y1 in regions:
        rect=(max(0,x0-pad),max(0,y0-pad),min(image.width-1,x1+pad),min(image.height-1,y1+pad))
        draw.rounded_rectangle(rect,radius=pad,outline='white',width=stroke*3)
        draw.rounded_rectangle(rect,radius=pad,outline=(181,75,0),width=stroke)
    return output
