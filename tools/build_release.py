"""Build one audited application payload and package it as ZIP and per-user setup."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('kalka_installer_build', ROOT/'tools/installer/build.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def digest_file(path):
    return installer.sha(path)


def verify_setup(setup, portable, scratch):
    extractor = scratch/'extract-release.exe'
    subprocess.run([str(installer.CSC), '/nologo', '/target:exe', '/platform:x64',
                    '/out:'+str(extractor), str(ROOT/'tools/installer/extract_release_resources.cs')], check=True)
    extracted = scratch/'resources'
    subprocess.run([str(extractor), str(setup), str(extracted)], check=True)
    if digest_file(extracted/'Kalka.exe') != digest_file(portable/'Kalka.exe'):
        raise ValueError('Setup launcher differs from portable')
    expected = {p.relative_to(portable).as_posix(): p for p in portable.rglob('*') if p.is_file()}
    del expected['Kalka.exe']
    with zipfile.ZipFile(extracted/'bundle.zip') as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError('Setup payload file set differs from portable')
        for name in names:
            with bundle.open(name) as source:
                h = hashlib.sha256()
                for part in iter(lambda: source.read(1024*1024), b''): h.update(part)
            if h.hexdigest() != digest_file(expected[name]):
                raise ValueError('Setup payload differs: '+name)
    print('PASS: setup application payload and launcher match portable:', len(expected)+1, 'files')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', required=True)
    p.add_argument('--payload', required=True, help='Pinned Python and SDK input ZIP')
    p.add_argument('--fixed', required=True, help='Verified WebView2 Fixed input directory')
    p.add_argument('--sdk', required=True, help='Verified WebView2 SDK directory')
    p.add_argument('--msvc-cab', help='Pinned Microsoft VC++ Redist x64 CAB')
    p.add_argument('--upstream-runtime', action='store_true', help='Keep original Python and WebView2 runtime files')
    p.add_argument('--output', required=True, help='New release directory; never overwritten')
    a = p.parse_args()
    if not a.upstream_runtime and not a.msvc_cab: p.error('--msvc-cab is required unless --upstream-runtime is set')
    out = Path(a.output).resolve()
    if out.exists(): raise FileExistsError(out)
    out.mkdir(parents=True)
    portable = out/'KalkaPortable'
    setup = out/('KalkaSetup-v'+a.version+'.exe')
    a.portable_dir, a.output = str(portable), str(setup)
    a.previous_setup, a.previous_sha256, a.previous_meta = [], [], []
    installer.build(a)
    portable_zip = out/('KalkaPortable-v'+a.version+'.zip')
    with zipfile.ZipFile(portable_zip, 'x', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for path in sorted(portable.rglob('*')):
            if path.is_file(): z.write(path, 'KalkaPortable/'+path.relative_to(portable).as_posix())
    with tempfile.TemporaryDirectory(prefix='verify-release-', dir=str(out)) as tmp:
        verify_setup(setup, portable, Path(tmp))
    with zipfile.ZipFile(portable_zip) as z:
        files = {p.relative_to(portable).as_posix(): p for p in portable.rglob('*') if p.is_file()}
        names = z.namelist()
        if len(names)!=len(set(names)) or set(names)!={'KalkaPortable/'+n for n in files}:
            raise ValueError('Portable ZIP file set mismatch')
        for name, path in files.items():
            with z.open('KalkaPortable/'+name) as f:
                h=hashlib.sha256()
                for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
            if h.hexdigest()!=digest_file(path): raise ValueError('Portable ZIP mismatch: '+name)
    artifacts = {p.name: {'sha256':digest_file(p), 'bytes':p.stat().st_size} for p in (portable_zip, setup)}
    manifest = {'name':'CR20KB Kalka', 'version':a.version,
                'build_date':datetime.now().astimezone().isoformat(timespec='seconds'),
                'type':'local test candidate', 'architecture':'x64',
                'runtime':{'CPython':'3.12.10', 'Pillow':'13.0.0', 'pypdfium2':'5.14.0',
                           'PDFium':'158.0.8111.0', 'pypdfium2_build':'CR20KB custom bindings', 'WebView2 Fixed':'156.0.4314.50',
                           'Microsoft VC++ Redist': 'original upstream files' if a.upstream_runtime else '14.51.36247.0'}, 'artifacts':artifacts}
    (out/'release-manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (out/'SHA256SUMS.txt').write_text(''.join(v['sha256']+'  '+k+'\n' for k,v in artifacts.items()),encoding='ascii')
    print('Release directory:', out)
    print(json.dumps(artifacts, indent=2))


if __name__ == '__main__': main()
