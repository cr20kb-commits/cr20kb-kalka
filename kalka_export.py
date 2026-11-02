"""Disk-backed, tiled PNG export for Kalka. One decoded raster source at a time."""
from contextlib import ExitStack, closing
import math
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

from PIL import Image
from vendor.archivarius.document_pages import PDF_LOCK, open_pdf, drawing_alpha_threshold
import kalka_core as core

TILE_W, TILE_H = 1024, 128
# PDF glyph rendering can depend on the complete glyph around a tile edge.
# Padding keeps most strokes away from PDFium's clipping boundary.
SOURCE_PADDING = 64


def _png_chunk(out, kind, data):
    out.write(struct.pack('>I', len(data)))
    out.write(kind)
    out.write(data)
    out.write(struct.pack('>I', zlib.crc32(data, zlib.crc32(kind)) & 0xffffffff))


def _png_from_raw(raw, output, width, height):
    output.write(b'\x89PNG\r\n\x1a\n')
    _png_chunk(output, b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    compressor = zlib.compressobj(6)
    raw.seek(0)
    for _ in range(height):
        row = raw.read(width * 4)
        if len(row) != width * 4:
            raise ValueError('Неполный временный растр.')
        data = compressor.compress(b'\0' + row)
        if data:
            _png_chunk(output, b'IDAT', data)
    data = compressor.flush()
    if data:
        _png_chunk(output, b'IDAT', data)
    _png_chunk(output, b'IEND', b'')


def _transform(layer):
    angle = math.radians(layer['angle'])
    c, s = math.cos(angle), math.sin(angle)
    # Exact quadrantal rotations must not gain a blank pixel from FP noise.
    if abs(c) < 1e-12: c = 0.0
    if abs(s) < 1e-12: s = 0.0
    return c, s, layer['scale']


def _corners(layer, width, height):
    c, s, scale = _transform(layer)
    return [(layer['x'] + scale * (c*x-s*y), layer['y'] + scale * (s*x+c*y))
            for x, y in ((0, 0), (width, 0), (0, height), (width, height))]


class Page:
    def __init__(self, path, layer, stack):
        self.path, self.layer = Path(path), layer
        suffix = self.path.suffix.lower()
        self.pdf = suffix == '.pdf'
        if self.pdf:
            stack.enter_context(PDF_LOCK)
            doc = stack.enter_context(open_pdf(self.path.read_bytes()))
            doc.init_forms()
            if layer['page'] >= len(doc):
                raise ValueError('Страница отсутствует.')
            self.page = stack.enter_context(closing(doc[layer['page']]))
            self.pdf_scale = layer['dpi'] / 72
            self.width = math.ceil(self.page.get_width() * self.pdf_scale)
            self.height = math.ceil(self.page.get_height() * self.pdf_scale)
        else:
            if layer['page'] != 0:
                raise ValueError('Страница отсутствует.')
            self.image = stack.enter_context(Image.open(self.path, formats=('JPEG', 'PNG')))
            self.width, self.height = self.image.size
            # Pillow decodes one raster source at a time. PNG/JPG may require
            # memory proportional to that source; PDF is rendered by tile.
            self.image.load()

    def crop(self, x0, y0, x1, y1):
        if not self.pdf:
            return self.image.crop((x0, y0, x1, y1))
        scale = self.pdf_scale
        # pypdfium2 rounds each crop edge up to pixels.
        unit = lambda n: max(0, n - 1e-7) / scale
        crop = (unit(x0), unit(self.height-y1), unit(self.width-x1), unit(y0))
        bitmap = self.page.render(scale=scale, crop=crop, rev_byteorder=True)
        try:
            image = bitmap.to_pil().copy().convert('RGB')
        finally:
            bitmap.close()
        if image.size != (x1-x0, y1-y0):
            image.close()
            raise ValueError('Ошибка размера плитки PDF.')
        return image


def _metadata(path, layer):
    with ExitStack() as stack:
        if Path(path).suffix.lower() == '.pdf':
            stack.enter_context(PDF_LOCK)
            doc = stack.enter_context(open_pdf(Path(path).read_bytes()))
            if layer['page'] >= len(doc):
                raise ValueError('Страница отсутствует.')
            page = stack.enter_context(closing(doc[layer['page']]))
            return (math.ceil(page.get_width()*layer['dpi']/72), math.ceil(page.get_height()*layer['dpi']/72))
        img = stack.enter_context(Image.open(path))
        return img.size


def export_png(entries, output, temporary_dir, layer_only=False):
    """Write PNG to output using an on-disk compositing buffer and tiled work."""
    if not entries:
        raise ValueError('Нет слоёв для экспорта.')
    prepared = []
    for path, layer in entries:
        core.validate_layer(layer)
        layer = dict(layer)
        if layer_only:
            layer.update(x=0, y=0, angle=0, scale=1, color='#000000', opacity=100)
        width, height = _metadata(path, layer)
        prepared.append((path, layer, width, height))
    points = [p for _, layer, w, h in prepared for p in _corners(layer, w, h)]
    left = math.floor(min(p[0] for p in points)); top = math.floor(min(p[1] for p in points))
    right = math.ceil(max(p[0] for p in points)); bottom = math.ceil(max(p[1] for p in points))
    width, height = right-left, bottom-top
    if width < 1 or height < 1 or width > 100000 or height > 100000:
        raise ValueError('Некорректные или чрезмерные размеры результата.')
    raw_bytes = width * height * 4
    free = shutil.disk_usage(temporary_dir).free
    if raw_bytes * 2 + 32*1024*1024 > free:
        raise ValueError('Недостаточно места для временного растра и PNG.')
    with tempfile.TemporaryFile(dir=temporary_dir) as raw:
        raw.truncate(raw_bytes)
        for path, layer, sw, sh in prepared:
            with ExitStack() as stack:
                page = Page(path, layer, stack)
                if (page.width, page.height) != (sw, sh):
                    raise ValueError('Размер источника изменился.')
                c, s, scale = _transform(layer)
                color = tuple(int(layer['color'][i:i+2], 16) for i in (1, 3, 5))
                for oy in range(0, height, TILE_H):
                    th = min(TILE_H, height-oy)
                    for ox in range(0, width, TILE_W):
                        tw = min(TILE_W, width-ox)
                        gx, gy = left+ox-layer['x'], top+oy-layer['y']
                        coeff = (c/scale, s/scale, (c*gx+s*gy)/scale,
                                 -s/scale, c/scale, (-s*gx+c*gy)/scale)
                        xs = [coeff[0]*u+coeff[1]*v+coeff[2] for u,v in ((0,0),(tw,0),(0,th),(tw,th))]
                        ys = [coeff[3]*u+coeff[4]*v+coeff[5] for u,v in ((0,0),(tw,0),(0,th),(tw,th))]
                        x0=max(0, math.floor(min(xs))-SOURCE_PADDING); y0=max(0, math.floor(min(ys))-SOURCE_PADDING)
                        x1=min(sw, math.ceil(max(xs))+SOURCE_PADDING); y1=min(sh, math.ceil(max(ys))+SOURCE_PADDING)
                        if x0>=x1 or y0>=y1:
                            continue
                        source = page.crop(x0,y0,x1,y1)
                        try:
                            mask = drawing_alpha_threshold(source, layer['threshold'])
                        finally:
                            source.close()
                        try:
                            alpha = mask.getchannel('A').point(lambda v: round(v*layer['opacity']/100))
                            mask.paste(color + (0,), (0, 0, mask.width, mask.height))
                            mask.putalpha(alpha)
                            mapped = mask.transform((tw,th), Image.Transform.AFFINE,
                                (coeff[0],coeff[1],coeff[2]-x0,coeff[3],coeff[4],coeff[5]-y0),
                                resample=Image.Resampling.BILINEAR)
                        finally:
                            mask.close()
                        try:
                            data = bytearray()
                            for row in range(th):
                                raw.seek(((oy+row)*width+ox)*4)
                                data.extend(raw.read(tw*4))
                            background = Image.frombytes('RGBA', (tw,th), bytes(data))
                            background.alpha_composite(mapped)
                            pixels = background.tobytes()
                            background.close()
                            for row in range(th):
                                raw.seek(((oy+row)*width+ox)*4)
                                raw.write(pixels[row*tw*4:(row+1)*tw*4])
                        finally:
                            mapped.close()
        with Path(output).open('wb') as out:
            _png_from_raw(raw, out, width, height)
    return width, height
