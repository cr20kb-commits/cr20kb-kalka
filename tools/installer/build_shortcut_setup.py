"""Build a shortcut-only setup from the pinned existing Setup and Portable."""
import argparse
import hashlib
import importlib.util
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('kalka_installer_build', HERE/'build.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)
BASE_HASH = '9cf3fa98b99f35e68ce63d27272e103c163ebdfe46475fbce77b77f133291025'
PORTABLE_HASH = '4617a66749b9549f154948742c2360030f66f1e8776c3ff5c5e1705d89f3c91c'
EARLIER_HASH = 'fd31f4a9e9f71e2c049971e77b5b5e75334d6a3d75589f2f03a487b9f43cb6a6'
LEGACY_SETUPS = (
    (ROOT.parent/'build-public-test/free-1.0.5-rc/KalkaSetup.exe', '75c06265e7e31d9c142fcc9acb098417aea30680da6794ff4a5b0205a3568711'),
    (ROOT.parent/'build-public-test/windows-icon/KalkaSetup.exe', '26ca127c7623fb42ca492a9ec374a5d606c2b57397b58bd802035ea3499c95a5'),
)


def verify_payload(bundle, launcher, portable):
    with zipfile.ZipFile(bundle) as b, zipfile.ZipFile(portable) as p:
        actual = p.namelist()
        if len(actual)!=len(set(actual)): raise ValueError('Duplicate Portable entries')
        expected = {'KalkaPortable/'+n for n in b.namelist()} | {'KalkaPortable/Kalka.exe'}
        if set(actual)!=expected or len(b.namelist())!=len(set(b.namelist())):
            raise ValueError('Setup/Portable payload file sets differ')
        for name in b.namelist():
            left=hashlib.sha256();right=hashlib.sha256()
            with b.open(name) as x,p.open('KalkaPortable/'+name) as y:
                for chunk in iter(lambda:x.read(1024*1024),b''):left.update(chunk)
                for chunk in iter(lambda:y.read(1024*1024),b''):right.update(chunk)
            if left.digest()!=right.digest():raise ValueError('Setup/Portable payload differs: '+name)
        if hashlib.sha256(p.read('KalkaPortable/Kalka.exe')).hexdigest()!=installer.sha(launcher):
            raise ValueError('Setup/Portable launcher differs')
        print('PASS: retained Setup payload equals unchanged Portable:',len(actual),'files',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True);parser.add_argument('--portable',required=True)
    parser.add_argument('--earlier',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--version',default='1.0.5')
    parser.add_argument('--diagnostic-fail-after-data-move',action='store_true',help='Test-only fault injection; requires a diagnostic output name')
    args=parser.parse_args()
    if not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}',args.version):raise ValueError('Invalid version')
    base=Path(args.base).resolve(strict=True);portable=Path(args.portable).resolve(strict=True)
    earlier=Path(args.earlier).resolve(strict=True);out=Path(args.output).resolve()
    if args.diagnostic_fail_after_data_move and not out.name.endswith('-diagnostic.exe'):
        raise ValueError('Diagnostic setup must have an explicit -diagnostic.exe name')
    if out.exists():raise FileExistsError(out)
    if installer.sha(base)!=BASE_HASH or installer.sha(portable)!=PORTABLE_HASH or installer.sha(earlier)!=EARLIER_HASH:
        raise ValueError('Setup or Portable input hash mismatch')
    for legacy,digest in LEGACY_SETUPS:
        if installer.sha(legacy)!=digest:raise ValueError('Legacy Setup hash mismatch: '+str(legacy))
    for name,digest in installer.TEST_PREDECESSOR_HASHES.items():
        if installer.sha(ROOT/'upgrade/test-1.0.4'/name)!=digest:raise ValueError('Previous metadata hash mismatch: '+name)
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='kalka-shortcut-build-',dir=str(out.parent)) as scratch:
        tmp=Path(scratch);extractor=tmp/'extract-bundle.exe'
        subprocess.run([str(installer.CSC),'/nologo','/target:exe','/platform:x64','/out:'+str(extractor),str(HERE/'extract_setup_bundle.cs')],check=True)
        inputs=tmp/'base';subprocess.run([str(extractor),str(base),str(inputs)],check=True)
        verify_payload(inputs/'bundle.zip',inputs/'application.exe',portable)
        support=(HERE/'support.cs').read_text(encoding='utf-8').replace('Version = "1.0.0"','Version = "'+args.version+'"').replace(' — персональная сборка','').replace(' (персональная)','')
        support=support.replace('"CR20KB-Kalka.exe", UninstallerName','"Kalka.exe", UninstallerName')
        old='foreach(string sub in Directory.GetDirectories(d)){CheckNoReparse(root,sub);if(!allowedDirs.Contains(sub))return false;todo.Push(sub);}'
        new='foreach(string sub in Directory.GetDirectories(d)){CheckNoReparse(root,sub);if(String.Equals(sub,Path.Combine(root,"KalkaData"),StringComparison.OrdinalIgnoreCase))continue;if(!allowedDirs.Contains(sub))return false;todo.Push(sub);}'
        if support.count(old)!=1:raise ValueError('Unexpected installer tree check')
        (tmp/'support.cs').write_text(support.replace(old,new),encoding='utf-8')
        setup=(HERE/'setup.cs').read_text(encoding='utf-8').replace('1.0.0.0',args.version+'.0').replace('установка 1.0.0','установка '+args.version).replace('Персональная сборка Кальки','Калька').replace('Проекты и действующая лицензия сохраняются.','Пользовательские проекты сохраняются.')
        if args.diagnostic_fail_after_data_move:
            checkpoint='Directory.Move(Path.Combine(backup,"KalkaData"),Path.Combine(root,"KalkaData"));movedData=true;'
            if setup.count(checkpoint)!=1:raise ValueError('Diagnostic checkpoint missing')
            setup=setup.replace(checkpoint,checkpoint+'throw new IOException("KALKA_TEST_FAILURE_AFTER_DATA_MOVE");')
        (tmp/'setup.cs').write_text(setup,encoding='utf-8')
        launchhash=tmp/'launcher.hash';launchhash.write_text(installer.sha(inputs/'application.exe'),encoding='ascii')
        refs=['System.Windows.Forms.dll','System.Drawing.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','Microsoft.CSharp.dll']
        uninstaller=tmp/'Uninstall.exe'
        installer.compile_cs(uninstaller,[HERE/'uninstaller.cs',tmp/'support.cs'],[(inputs/'manifest.txt','Kalka.bundle.manifest'),(launchhash,'Kalka.launcher.hash')],refs)
        resources=[(inputs/'bundle.zip','Kalka.bundle'),(inputs/'manifest.txt','Kalka.bundle.manifest'),(inputs/'application.exe','Kalka.application'),(uninstaller,'Kalka.uninstaller'),(inputs/'runtime.terms','Kalka.runtime.terms'),(inputs/'python.terms','Kalka.python.terms')]
        prev=tmp/'earlier';subprocess.run([str(extractor),str(earlier),str(prev)],check=True)
        for i,folder in enumerate((inputs,prev)):
            prefix='Kalka.previous'+(str(i+1) if i else '')
            lh=tmp/(prefix+'.launcher.hash');uh=tmp/(prefix+'.uninstaller.hash')
            lh.write_text(installer.sha(folder/'application.exe'),encoding='ascii');uh.write_text(installer.sha(folder/'old-uninstaller.exe'),encoding='ascii')
            resources.extend([(folder/'manifest.txt',prefix+'.manifest'),(lh,prefix+'.launcher.hash'),(uh,prefix+'.uninstaller.hash')])
        previous=ROOT/'upgrade/test-1.0.4';prefix='Kalka.previous3'
        resources.extend([(previous/'manifest.txt',prefix+'.manifest'),(previous/'launcher.sha256',prefix+'.launcher.hash'),(previous/'uninstaller.sha256',prefix+'.uninstaller.hash')])
        for i,(legacy,_) in enumerate(LEGACY_SETUPS,1):
            folder=tmp/('legacy'+str(i));subprocess.run([str(extractor),str(legacy),str(folder)],check=True)
            resources.append((folder/'manifest.txt','Kalka.legacy'+str(i)+'.manifest'))
        installer.compile_cs(out,[tmp/'setup.cs',tmp/'support.cs'],resources,refs)
    print('Shortcut-only Setup:',out,'SHA-256:',installer.sha(out),flush=True)


if __name__=='__main__':main()
