"""Kalka project primitives. Source files are read only and packed in the project."""
from __future__ import annotations

from datetime import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import zipfile

from PIL import Image
from vendor.archivarius.document_pages import PDF_LOCK, open_pdf

MAX_LAYERS = 10
MAX_SOURCE_BYTES = 200 * 1024 * 1024
MAX_PROJECT_BYTES = MAX_LAYERS * MAX_SOURCE_BYTES


def source_date(path):
    """Return editable ISO date and the metadata source, without touching source."""
    path = Path(path)
    try:
        if path.suffix.lower() == '.pdf':
            with PDF_LOCK, open_pdf(path.read_bytes()) as pdf:
                raw = pdf.get_metadata_value('ModDate')
            match = re.match(r'^(?:D:)?(\d{4})(\d{2})(\d{2})', raw or '')
            if match:
                return datetime(*map(int, match.groups())).date().isoformat(), 'PDF ModDate'
        elif path.suffix.lower() in {'.jpg', '.jpeg', '.png'}:
            with Image.open(path, formats=('JPEG', 'PNG')) as image:
                exif = image.getexif()
                raw = exif.get(306) or exif.get(36867)
            if raw:
                return datetime.strptime(raw[:19], '%Y:%m:%d %H:%M:%S').date().isoformat(), 'EXIF'
    except (ValueError, OSError, TypeError):
        pass
    return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat(), 'file modification time'


def validate_layer(layer):
    if not isinstance(layer, dict):
        raise ValueError('Некорректный слой.')
    for key in ('name', 'date', 'date_source', 'role', 'comment', 'source_name'):
        if not isinstance(layer.get(key), str) or len(layer[key]) > 4096:
            raise ValueError('Некорректные метаданные слоя: ' + key)
    try:
        datetime.strptime(layer['date'], '%Y-%m-%d')
    except ValueError as exc:
        raise ValueError('Дата должна иметь формат YYYY-MM-DD.') from exc
    if Path(layer['source_name']).name != layer['source_name'] or not layer['source_name'] or any(c in layer['source_name'] for c in ('/', '\\', '\0')):
        raise ValueError('Некорректное имя источника.')
    if Path(layer['source_name']).suffix.lower() not in {'.pdf', '.jpg', '.jpeg', '.png'}:
        raise ValueError('Неподдерживаемый тип источника.')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', layer.get('color', '')):
        raise ValueError('Некорректный цвет.')
    if not isinstance(layer.get('visible'), bool) or not isinstance(layer.get('aligned'), bool):
        raise ValueError('Некорректная видимость или состояние совмещения.')
    for key, low, high in (('opacity', 0, 100), ('x', -1000000, 1000000),
                           ('y', -1000000, 1000000), ('angle', -36000, 36000),
                           ('scale', 0.01, 100), ('threshold', 0, 255), ('dpi', 36, 600)):
        value = layer.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Некорректный параметр: ' + key)
    for key in ('threshold', 'dpi', 'page'):
        if isinstance(layer.get(key), bool) or not isinstance(layer.get(key), int):
            raise ValueError('Некорректное целое значение: ' + key)
    if layer['page'] < 0:
        raise ValueError('Некорректная страница.')


def source_from_project(project, layer):
    """Read a validated packed source without extracting user-provided paths."""
    with zipfile.ZipFile(project) as archive:
        return archive.read(layer['asset'])


def new_layer(path):
    path = Path(path)
    date, date_source = source_date(path)
    layer = {'name': path.stem, 'source_name': path.name, 'date': date, 'date_source': date_source,
             'role': '', 'comment': '', 'color': '#e1233c', 'opacity': 100, 'visible': True,
             'aligned': False, 'x': 0, 'y': 0, 'angle': 0, 'scale': 1,
             'page': 0, 'dpi': 144, 'threshold': 255}
    validate_layer(layer)
    return layer


def validate_comparison(value, count):
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {'base', 'selected', 'mode', 'show_marks'}:
        raise ValueError('Некорректные настройки сравнения.')
    for key in ('base', 'selected'):
        if isinstance(value[key], bool) or not isinstance(value[key], int) or not 0 <= value[key] < count:
            raise ValueError('Некорректная выбранная редакция.')
    if value['mode'] not in {'overlay', 'diff', 'blink'} or not isinstance(value['show_marks'], bool):
        raise ValueError('Некорректные настройки сравнения.')


def save_project(destination, layers, sources, language='ru', comparison=None):
    """Atomically replace project only after packing and verifying all source bytes."""
    destination = Path(destination).resolve()
    if len(layers) != len(sources) or not 1 <= len(layers) <= MAX_LAYERS:
        raise ValueError('Проект должен содержать от 1 до 10 слоёв и столько же исходников.')
    if language not in {'ru', 'en', 'zh'}:
        raise ValueError('Некорректный язык.')
    validate_comparison(comparison, len(layers))
    paths = [Path(source).resolve(strict=True) for source in sources]
    for path in paths:
        if path == destination or (destination.exists() and os.path.samefile(path, destination)):
            raise ValueError('Нельзя записать проект поверх исходного файла.')
    for layer in layers:
        validate_layer(layer)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.kalka-', suffix='.tmp', dir=destination.parent, delete=False) as tmp:
            temporary = Path(tmp.name)
        manifest = {'format': 'CR20KB-KALKA', 'version': 1, 'language': language, 'layers': []}
        if comparison is not None:
            manifest['comparison'] = comparison
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for index, (layer, path) in enumerate(zip(layers, paths)):
                if path.stat().st_size > MAX_SOURCE_BYTES:
                    raise ValueError('Исходный файл больше 200 МиБ.')
                digest = hashlib.sha256()
                size = 0
                asset = f'sources/{index:02d}{path.suffix.lower()}'
                with path.open('rb') as source, archive.open(asset, 'w', force_zip64=True) as target:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_SOURCE_BYTES:
                            raise ValueError('Исходный файл больше 200 МиБ.')
                        digest.update(chunk)
                        target.write(chunk)
                manifest['layers'].append({**layer, 'asset': asset, 'sha256': digest.hexdigest(), 'size': size})
            archive.writestr('project.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
        load_project(temporary)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_project(path):
    """Validate portable project; no extraction or writes. Return manifest."""
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or 'project.json' not in names:
            raise ValueError('Повторяющиеся записи или отсутствует описание проекта.')
        if archive.getinfo('project.json').file_size > 1024 * 1024:
            raise ValueError('Описание проекта слишком велико.')
        manifest = json.loads(archive.read('project.json'))
        if manifest.get('format') != 'CR20KB-KALKA' or manifest.get('version') != 1 or manifest.get('language') not in {'ru', 'en', 'zh'}:
            raise ValueError('Неподдерживаемый формат проекта.')
        layers = manifest.get('layers')
        if not isinstance(layers, list) or not 1 <= len(layers) <= MAX_LAYERS:
            raise ValueError('Некорректное число слоёв.')
        validate_comparison(manifest.get('comparison'), len(layers))
        expected = {'project.json'}
        total = 0
        for index, layer in enumerate(layers):
            validate_layer(layer)
            asset = f'sources/{index:02d}{Path(layer["source_name"]).suffix.lower()}'
            if layer.get('asset') != asset or asset not in names:
                raise ValueError('Исходник слоя отсутствует или указан неверно.')
            info = archive.getinfo(asset)
            total += info.file_size
            if info.file_size > MAX_SOURCE_BYTES or total > MAX_PROJECT_BYTES or layer.get('size') != info.file_size:
                raise ValueError('Некорректный размер исходника.')
            digest = hashlib.sha256()
            with archive.open(info) as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != layer.get('sha256'):
                raise ValueError('Контрольная сумма исходника не совпадает.')
            expected.add(asset)
        if set(names) != expected:
            raise ValueError('В проекте есть неизвестные записи.')
        return manifest
