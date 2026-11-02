"""Recreate the local runtime input from pinned packages, including the custom PDFium build."""
import argparse
import hashlib
import zipfile
from pathlib import Path

PACKAGES = {
    'python': ('python-3.12.10-embed-amd64.zip', '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'),
    'pillow': ('pillow-13.0.0-cp312-cp312-win_amd64.whl', 'ff3fe9eb621fbb9db4c4be33ab946f6bac5f98ab50ca8d3260503653656c961b'),
    'pypdfium2': ('pypdfium2-5.14.0-py3-none-win_amd64.whl', '4cabb46bb66fd9007bcdf53a0e5f2702129ca0ff168329a10bc85d917b04ee9f'),
    'sdk': ('Microsoft.Web.WebView2.1.0.3650.58.nupkg', '911a472128c82ac8baa0c486c23342cc9dd6e7dc50d754e676726642ca065c60'),
}
SDK_FILES = {
    'lib/net462/Microsoft.Web.WebView2.Core.dll': 'webview/Microsoft.Web.WebView2.Core.dll',
    'lib/net462/Microsoft.Web.WebView2.WinForms.dll': 'webview/Microsoft.Web.WebView2.WinForms.dll',
    'build/native/x64/WebView2Loader.dll': 'webview/WebView2Loader.dll',
}

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--packages',required=True);p.add_argument('--output',required=True);p.add_argument('--compare-payload');args=p.parse_args()
    output=Path(args.output)
    if output.exists(): raise FileExistsError(output)
    files={}
    for key,(name,digest) in PACKAGES.items():
        source=Path(args.packages)/name
        if sha(source.read_bytes())!=digest: raise ValueError('Package hash mismatch: '+name)
        with zipfile.ZipFile(source) as z:
            for n in z.namelist():
                if n.endswith('/'): continue
                if key=='sdk':
                    if n not in SDK_FILES: continue
                    target=SDK_FILES[n]
                else: target=('runtime/' if key=='python' else 'runtime/Lib/site-packages/')+n
                data=z.read(n)
                if target=='runtime/python312._pth': data=b'python312.zip\n.\nLib/site-packages\n../program\n'
                if target in files: raise ValueError('Duplicate file: '+target)
                files[target]=data
    if args.compare_payload:
        with zipfile.ZipFile(args.compare_payload) as original:
            expected={n for n in original.namelist() if n.startswith(('runtime/','webview/')) and not n.endswith('/')}
            if set(files)!=expected: raise ValueError('Input file set differs from previously tested runtime')
            for n,data in files.items():
                if sha(data)!=sha(original.read(n)): raise ValueError('Input differs: '+n)
        print('PASS: all reconstructed runtime and SDK files match previously tested payload')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n,data in sorted(files.items()):
            info=zipfile.ZipInfo(n,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
    print('Runtime input:',output,'SHA256:',sha(output.read_bytes()),'files:',len(files))

if __name__=='__main__':main()
