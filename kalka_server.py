"""Local, session-scoped bridge between the UI and Archivarius decoding code."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import io
import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import webbrowser
import zipfile

import kalka_core as core
from kalka_export import export_png
from kalka_compare import compare, mark
from vendor.archivarius.document_pages import drawing_alpha_threshold, selected_page

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
TOKEN = secrets.token_urlsafe(32)
FILES = {}
LOCK = threading.RLock()
JOBS = {}
COMPARE_CACHE = {}
JOB_LOCK = threading.RLock()
TEMP = tempfile.TemporaryDirectory(prefix='CR20KB-Kalka-')
SESSION = Path(TEMP.name)
MAX_BODY = core.MAX_PROJECT_BYTES + 5 * 1024 * 1024
LAST_PING = time.monotonic()


def register(data, name, last_modified=None):
    if len(data) > core.MAX_SOURCE_BYTES or not data:
        raise ValueError('Пустой файл или файл больше 200 МиБ.')
    name = Path(name).name
    suffix = Path(name).suffix.lower()
    if suffix not in {'.pdf', '.png', '.jpg', '.jpeg'}:
        raise ValueError('Поддерживаются PDF, JPG и PNG.')
    ident = secrets.token_hex(16)
    path = SESSION / (ident + suffix)
    path.write_bytes(data)
    try:
        if isinstance(last_modified, (int, float)) and 0 < last_modified < 10**13:
            os.utime(path, (last_modified / 1000, last_modified / 1000))
        layer = core.new_layer(path)
        layer.update(name=Path(name).stem, source_name=name)
        image, meta = selected_page(data, suffix, preview_max_edge=1600)
        image.close()
        core.validate_layer(layer)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    FILES[ident] = path
    return {'id': ident, 'layer': layer, 'meta': meta}


def file_for(ident):
    if not isinstance(ident, str) or ident not in FILES:
        raise ValueError('Источник отсутствует в текущем сеансе.')
    return FILES[ident]


def start_job(suffix, mime, operation, protected=False):
    ident = secrets.token_hex(16)
    target = SESSION / (ident + suffix)
    with JOB_LOCK:
        JOBS[ident] = {'status': 'working', 'path': target, 'mime': mime, 'protected': protected}
    def work():
        try:
            with LOCK:
                meta = operation(target)
            with JOB_LOCK:
                JOBS[ident].update(status='ready', meta=meta)
        except Exception as exc:
            target.unlink(missing_ok=True)
            with JOB_LOCK:
                JOBS[ident].update(status='error', error=str(exc) or type(exc).__name__)
    threading.Thread(target=work, daemon=True).start()
    return ident


def render_png(source, layer, preview, target):
    image, meta = selected_page(source.read_bytes(), source.suffix, layer['page'], layer['dpi'], 1600 if preview else None)
    try:
        ink = drawing_alpha_threshold(image, layer['threshold'])
        try:
            ink.save(target, format='PNG')
        finally:
            ink.close()
    finally:
        image.close()
    return meta


def pair_result(items, target, show_marks=False):
    keys = ('page', 'dpi', 'threshold', 'x', 'y', 'angle', 'scale')
    cache_key = json.dumps([(str(path), {k: layer[k] for k in keys}) for path, layer in items], sort_keys=True)
    cached = COMPARE_CACHE.get(cache_key)
    if cached is None:
        image, meta = compare(items)
        cached_path = SESSION / (secrets.token_hex(16) + '-compare.png')
        try:
            image.save(cached_path, format='PNG')
        finally:
            image.close()
        # Bounded cache; evict only files created by this session.
        if len(COMPARE_CACHE) >= 4:
            oldkey = next(iter(COMPARE_CACHE))
            old = COMPARE_CACHE.pop(oldkey)
            old[0].unlink(missing_ok=True)
        cached = (cached_path, meta)
        COMPARE_CACHE[cache_key] = cached
    meta = dict(cached[1])
    meta['alignment_checked'] = all(layer['aligned'] for _, layer in items)
    if show_marks:
        from PIL import Image
        with Image.open(cached[0]) as image:
            result = mark(image, meta['regions'])
            try: result.save(target, format='PNG')
            finally: result.close()
    else:
        shutil.copyfile(cached[0], target)
    return meta


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *_):
        pass

    def respond(self, status, data, mime='application/json'):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        if self.close_connection:
            self.send_header('Connection', 'close')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        routes = {'/': ('web/index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('web/app.js', 'text/javascript; charset=utf-8'),
                  '/app.css': ('web/app.css', 'text/css; charset=utf-8'),
                  '/compare_layers.js': ('vendor/archivarius/compare_layers.js', 'text/javascript; charset=utf-8'),
                  '/trace_geometry.js': ('vendor/archivarius/trace_geometry.js', 'text/javascript; charset=utf-8')}
        item = routes.get(urllib.parse.urlsplit(self.path).path)
        if not item:
            return self.respond(404, {'error': 'not found'})
        try:
            self.respond(200, (ROOT / item[0]).read_bytes(), item[1])
        except FileNotFoundError:
            self.respond(404, {'error': 'not found'})

    def do_POST(self):
        global LAST_PING
        if not secrets.compare_digest(self.headers.get('X-Kalka-Token', ''), TOKEN):
            # Reject without consuming the body; do not reuse this connection.
            self.close_connection = True
            return self.respond(403, {'error': 'forbidden'})
        LAST_PING = time.monotonic()
        response_started = False
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if size < 0 or size > MAX_BODY:
                raise ValueError('Недопустимый размер запроса.')
            if self.path == '/api/open':
                project = SESSION / (secrets.token_hex(16) + '.kalka')
                created = []
                try:
                    with project.open('wb') as stream:
                        remaining = size
                        while remaining:
                            chunk = self.rfile.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError('Неполный запрос.')
                            stream.write(chunk)
                            remaining -= len(chunk)
                    with LOCK:
                        manifest = core.load_project(project)
                        entries = []
                        with zipfile.ZipFile(project) as archive:
                            for layer in manifest['layers']:
                                path = SESSION / (secrets.token_hex(16) + Path(layer['source_name']).suffix.lower())
                                created.append(path)
                                with archive.open(layer['asset']) as src, path.open('wb') as dst:
                                    while chunk := src.read(1024 * 1024):
                                        dst.write(chunk)
                                ident = path.stem
                                clean = {k: v for k, v in layer.items() if k not in {'asset', 'sha256', 'size'}}
                                entries.append({'id': ident, 'layer': clean})
                        for path in created:
                            FILES[path.stem] = path
                    return self.respond(200, {'entries': entries, 'language': manifest['language'], 'comparison': manifest.get('comparison')})
                except Exception:
                    for path in created:
                        path.unlink(missing_ok=True)
                    raise
                finally:
                    project.unlink(missing_ok=True)
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError('Неполный запрос.')
            if self.path in {'/api/job', '/api/result'}:
                obj = json.loads(body)
                with JOB_LOCK:
                    job = JOBS.get(obj.get('job'))
                    if not job:
                        raise ValueError('Задача экспорта не найдена.')
                    if self.path == '/api/job':
                        return self.respond(200, {'status': job['status'], 'error': job.get('error')})
                    if job['status'] != 'ready':
                        raise ValueError('Экспорт ещё не готов.')

                    target = job['path']
                try:
                    self.send_response(200)
                    self.send_header('Content-Type', job['mime'])
                    if isinstance(job.get('meta'), dict):
                        self.send_header('X-Image-Meta', json.dumps(job['meta'], separators=(',', ':')))
                    self.send_header('Content-Length', str(target.stat().st_size))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    response_started = True
                    with target.open('rb') as src:
                        while chunk := src.read(1024 * 1024):
                            self.wfile.write(chunk)
                    return
                finally:
                    target.unlink(missing_ok=True)
                    with JOB_LOCK:
                        JOBS.pop(obj.get('job'), None)
            with LOCK:
                if self.path == '/api/ping':
                    return self.respond(200, {'ok': True})
                if self.path == '/api/shutdown':
                    self.respond(200, {'ok': True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                if self.path == '/api/import':
                    name = urllib.parse.unquote(self.headers.get('X-File-Name', ''))
                    modified = float(self.headers.get('X-File-Modified', '0'))
                    return self.respond(200, register(body, name, modified))
                obj = json.loads(body)
                if self.path == '/api/compare':

                    entries = obj.get('entries')
                    if not isinstance(entries, list) or len(entries) != 2 or entries[0]['id'] == entries[1]['id']:
                        raise ValueError('Выберите две разные редакции.')
                    items = [(file_for(e['id']), e['layer']) for e in entries]
                    return self.respond(200, {'job': start_job('.png', 'image/png',
                        lambda target: pair_result(items, target), protected=True)})
                if self.path == '/api/export':

                    entries = obj.get('entries')
                    layer_only = obj.get('layer_only', False)
                    if not isinstance(entries, list) or not 1 <= len(entries) <= core.MAX_LAYERS or not isinstance(layer_only, bool):
                        raise ValueError('Некорректный список слоёв.')
                    items = [(file_for(e['id']), e['layer']) for e in entries]
                    if obj.get('pair_compare') is True:
                        if layer_only or len(items)!=2 or entries[0]['id']==entries[1]['id'] or not isinstance(obj.get('show_marks'), bool):
                            raise ValueError('Некорректный парный экспорт.')
                        return self.respond(200, {'job': start_job('.png', 'image/png',
                            lambda target: pair_result(items, target, obj['show_marks']), protected=True)})
                    return self.respond(200, {'job': start_job('.png', 'image/png',
                        lambda target: export_png(items, target, SESSION, layer_only), protected=True)})
                if self.path == '/api/render':
                    preview = obj.get('preview', True)
                    if not isinstance(preview, bool):
                        raise ValueError('Некорректный режим просмотра.')

                    layer = obj['layer']
                    core.validate_layer(layer)
                    source = file_for(obj['id'])
                    return self.respond(200, {'job': start_job('.png', 'image/png',
                        lambda target: render_png(source, layer, preview, target), protected=True)})
                if self.path == '/api/save':
                    entries = obj['entries']
                    if not isinstance(entries, list) or not 1 <= len(entries) <= core.MAX_LAYERS:
                        raise ValueError('Должно быть от одного до десяти слоёв.')
                    paths = [file_for(entry['id']) for entry in entries]
                    layers = [entry['layer'] for entry in entries]
                    return self.respond(200, {'job': start_job('.kalka', 'application/octet-stream',
                        lambda target: core.save_project(target, layers, paths, obj['language'], obj.get('comparison')))})
                raise ValueError('Неизвестный запрос.')
        except Exception as exc:
            traceback.print_exc()
            if not response_started:
                self.respond(400, {'error': str(exc) or type(exc).__name__})


def main():
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        url = f'http://127.0.0.1:{server.server_port}/#{TOKEN}'
        native = '--native' in sys.argv
        if '--test-server' in sys.argv or native:
            print(url, flush=True)
        else:
            webbrowser.open(url)
        def monitor():
            while time.monotonic() - LAST_PING < 120:
                time.sleep(5)
            server.shutdown()
        if not native:
            threading.Thread(target=monitor, daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            TEMP.cleanup()


if __name__ == '__main__':
    main()
