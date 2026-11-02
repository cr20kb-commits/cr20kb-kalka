"""Prepare build inputs from Microsoft's pinned Fixed Runtime CAB and notices."""
import argparse
import hashlib
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CAB_HASH = 'fcf0cd55f7c6e8efced05114372de8b8ffc9032c0296d16e060d260637dfe5f2'
RUNTIME_HASHES = {'98c6d2e4f84be737742d21bb866e1c461a9187fcc8d483960111acaae9246792',
                  '4458fb87fcf12f14486e54814f22bd98f80e243ef4e6358dd2ded16e99b03713',
                  'f738893216868242270d1687abf8a229184f46a6f23b609b7a358ff2f25df9a8'}
MANIFEST_HASH = '8a06a99dcc622eca4fddc6a60dcbc56e5d9e33871d6f3b80ebe1e27d87949dc1'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def safe(name):
    p=PurePosixPath(name)
    if p.is_absolute() or any(x in ('','..') for x in p.parts) or '\\' in name or ':' in name: raise ValueError('Invalid input path')
    return p

def main():
    p=argparse.ArgumentParser();p.add_argument('--cab',required=True);p.add_argument('--runtime-zip',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    cab=Path(args.cab).resolve();runtime=Path(args.runtime_zip).resolve();out=Path(args.output).resolve();manifest=ROOT/'audit/fixed-inputs.sha256'
    if out.exists():raise FileExistsError(out)
    if sha(cab)!=CAB_HASH or sha(runtime) not in RUNTIME_HASHES or sha(manifest)!=MANIFEST_HASH:raise ValueError('Pinned input hash mismatch')
    lines=manifest.read_text(encoding='utf-8').splitlines();entries={}
    for line in lines:
        digest,name=line.split('  ',1);safe(name)
        if name in entries or not name.startswith(('FixedRuntime/','third_party_licenses/')) and name!='THIRD_PARTY_NOTICES.md': raise ValueError('Unexpected manifest entry')
        entries[name]=digest
    if len(entries)!=286:raise ValueError('Unexpected manifest count')
    out.mkdir(parents=True);fixed=out/'fixed';fixed.mkdir();unpacked=out/'unpacked';unpacked.mkdir()
    subprocess.run(['expand.exe',str(cab),'-F:*',str(unpacked)],check=True,stdout=subprocess.DEVNULL)
    inner=unpacked/'Microsoft.WebView2.FixedVersionRuntime.156.0.4314.50.x64'
    if not inner.is_dir() or list(unpacked.iterdir())!=[inner]:raise ValueError('Unexpected CAB directory layout')
    inner.rename(fixed/'FixedRuntime');unpacked.rmdir()
    for name in entries:
        if name.startswith('FixedRuntime/'):continue
        source=ROOT/name;target=fixed/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    actual={p.relative_to(fixed).as_posix() for p in fixed.rglob('*') if p.is_file()}
    if actual!=set(entries):raise ValueError('Fixed input file set mismatch')
    for name,digest in entries.items():
        if sha(fixed/name)!=digest:raise ValueError('Fixed input hash mismatch: '+name)
    shutil.copyfile(manifest,fixed/'SHA256SUMS.txt')
    sdk=out/'sdk';sdk.mkdir()
    with zipfile.ZipFile(runtime) as z:
        for name in ('Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll','WebView2Loader.dll'):
            (sdk/name).write_bytes(z.read('webview/'+name))
    print('PASS: official Fixed CAB,',len(entries),'verified runtime and notice files; SDK extracted')
    print('fixed:',fixed,'sdk:',sdk)

if __name__=='__main__':main()
