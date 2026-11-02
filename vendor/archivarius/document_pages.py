"""Offline full-page decoding. Never opens CAD or changes an input document."""
from contextlib import closing
import io
import math
import threading
from PIL import Image, ImageOps

PDF_LOCK = threading.RLock()  # PDFium forbids concurrent calls, including different PDFs.
RASTER = {'png', 'jpg', 'jpeg', 'tif', 'tiff', 'bmp', 'webp'}
CAD = {'cdw', 'frw', 'a3d', 'm3d', 'spw'}
MAX_PAGES = 500
MAX_PIXELS = 25_000_000
MAX_DOCUMENT_PIXELS = 100_000_000


def open_pdf(raw):
    import pypdfium2 as pdfium
    try:
        return pdfium.PdfDocument(raw)
    except pdfium.PdfiumError as exc:
        raise ValueError('Не удалось прочитать PDF: повреждён, защищён паролем или имеет неподдерживаемую структуру. Код PDFium: '+str(exc.err_code)) from exc


def pages(raw, extension):
    """Yield full page PIL copies and physical metadata; no auto fit/crop/rotation."""
    extension = extension.lower().lstrip('.')
    if extension == 'pdf':
        import pypdfium2 as pdfium
        with PDF_LOCK, open_pdf(raw) as document:
            # Includes interactive form appearances, never executes JavaScript.
            document.init_forms()
            count = len(document)
            if count > MAX_PAGES:
                raise ValueError(f'Больше {MAX_PAGES} страниц: обработка не выполнена целиком.')
            total_pixels = 0
            for number in range(count):
                with closing(document[number]) as page:
                    width, height = page.get_size()
                    total_pixels += width * height * 4
                    if total_pixels > MAX_DOCUMENT_PIXELS:
                        raise ValueError('Суммарный растр документа превышает 100 Мп. Уменьшение не выполнялось.')
                    if width * height * 4 > MAX_PIXELS:
                        raise ValueError('Страница при 144 DPI превышает 25 Мп; уменьшение не выполнялось.')
                    bitmap = page.render(scale=2, rev_byteorder=True)
                    try:
                        image = bitmap.to_pil().copy().convert('RGB')
                    finally:
                        bitmap.close()
                    yield image, {'sheet_count':count, 'dpi':[144,144], 'paper_mm':[round(width/72*25.4,3),round(height/72*25.4,3)],
                                  'rotation':page.get_rotation(), 'drawing_scale':None, 'profile':'pdf-full-page-144dpi-v1', 'full_page':True, 'provenance':'PDFium, полный лист PDF; без CAD'}
    elif extension in RASTER:
        with Image.open(io.BytesIO(raw)) as original:
            count = getattr(original, 'n_frames', 1)
            if count > MAX_PAGES:
                raise ValueError(f'Больше {MAX_PAGES} кадров: обработка не выполнена целиком.')
            total_pixels = 0
            for number in range(count):
                original.seek(number)
                orientation = int(original.getexif().get(274, 1))
                total_pixels += original.width * original.height
                if total_pixels > MAX_DOCUMENT_PIXELS:
                    raise ValueError('Суммарный растр документа превышает 100 Мп.')
                if original.width * original.height > MAX_PIXELS:
                    raise ValueError('Изображение превышает 25 Мп.')
                dpi = original.info.get('dpi')
                dpi = [float(v) for v in dpi] if dpi and min(dpi)>0 else None
                # Do not silently normalise EXIF orientation; report it with the page.
                image = original.convert('RGBA' if 'A' in original.getbands() or 'transparency' in original.info else 'RGB')
                yield image, {'sheet_count':count, 'dpi':dpi, 'paper_mm':[round(image.width/dpi[0]*25.4,3),round(image.height/dpi[1]*25.4,3)] if dpi else None,
                              'rotation':orientation, 'drawing_scale':None, 'profile':'raster-full-page-v1', 'full_page':True, 'provenance':'Полный растр без уменьшения; без CAD'}
    else:
        raise ValueError('CAD ожидает отдельной проверки v22.' if extension in CAD else 'Просмотр/экспорт пока не поддерживается.')


def drawing_alpha(image):
    """White-paper optical density -> alpha. Explicit drawing mode only.

    Pixel positions and antialias coverage survive; black one-pixel lines stay opaque.
    This is a derived layer, never written back to JPG/source or used for photos.
    """
    gray = ImageOps.grayscale(image.convert('RGB'))
    result = Image.new('RGBA', image.size, (0,0,0,0))
    result.putalpha(ImageOps.invert(gray))
    return result


def selected_page(raw, extension, number=0, dpi=144, preview_max_edge=None):
    """Decode one selected page; existing pages() callers remain unchanged.

    PDF rasterisation is capped before allocation; previews use the same aspect
    ratio as the requested full-resolution output. Caller owns the returned image.
    """
    extension = extension.lower().lstrip('.')
    if not isinstance(number, int) or number < 0:
        raise ValueError('Некорректный номер страницы.')
    if not isinstance(dpi, int) or not 36 <= dpi <= 600:
        raise ValueError('Разрешение должно быть от 36 до 600 DPI.')
    if preview_max_edge is not None and (not isinstance(preview_max_edge, int) or preview_max_edge < 1):
        raise ValueError('Некорректный размер превью.')
    if extension == 'pdf':
        with PDF_LOCK, open_pdf(raw) as document:
            document.init_forms()
            count = len(document)
            if number >= count:
                raise ValueError('Страница отсутствует.')
            with closing(document[number]) as page:
                width, height = page.get_size()
                full_scale = dpi / 72
                scale = full_scale
                if preview_max_edge:
                    scale = min(scale, preview_max_edge / max(width, height))
                if width * height * scale * scale > MAX_PIXELS:
                    raise ValueError('Растр страницы превышает 25 Мп; уменьшите DPI.')
                bitmap = page.render(scale=scale, rev_byteorder=True)
                try:
                    image = bitmap.to_pil().copy().convert('RGB')
                finally:
                    bitmap.close()
                return image, {'sheet_count': count, 'dpi': dpi,
                               'full_size': [math.ceil(width * full_scale), math.ceil(height * full_scale)],
                               'paper_mm': [width / 72 * 25.4, height / 72 * 25.4]}
    if extension not in {'png', 'jpg', 'jpeg'} or number != 0:
        raise ValueError('Поддерживаются PDF, PNG, JPG и JPEG.')
    # Restrict decoding to supported formats, including for misleading names.
    with Image.open(io.BytesIO(raw), formats=('JPEG', 'PNG')) as original:
        if original.width * original.height > MAX_PIXELS and preview_max_edge is None:
            raise ValueError('Растр больше 25 Мп; требуется постраничная обработка больших изображений.')
        full_size = list(original.size)
        if preview_max_edge and extension in {'jpg', 'jpeg'}:
            original.draft('RGB', (preview_max_edge, preview_max_edge))
        image = original.convert('RGBA' if 'A' in original.getbands() or 'transparency' in original.info else 'RGB')
        if preview_max_edge:
            image.thumbnail((preview_max_edge, preview_max_edge), Image.Resampling.LANCZOS)
        return image, {'sheet_count': 1, 'dpi': original.info.get('dpi'), 'full_size': full_size}


def drawing_alpha_threshold(image, threshold=255):
    """Use Archivarius density conversion, retain source alpha and remove pale paper."""
    from PIL import ImageChops
    if not isinstance(threshold, int) or not 0 <= threshold <= 255:
        raise ValueError('Порог должен быть от 0 до 255.')
    result = drawing_alpha(image)
    alpha = result.getchannel('A')
    if threshold < 255:
        alpha = alpha.point(lambda density: density if 255 - density < threshold else 0)
    if 'A' in image.getbands() or 'transparency' in image.info:
        alpha = ImageChops.multiply(alpha, image.convert('RGBA').getchannel('A'))
    result.putalpha(alpha)
    return result
