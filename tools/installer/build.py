"""Build a local, unlicensed-for-distribution test installer from audited inputs.

The inputs are supplied explicitly and verified; this is not yet a release build.
"""
import argparse
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CSC = Path(r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe')
PAYLOAD_HASHES = {'f738893216868242270d1687abf8a229184f46a6f23b609b7a358ff2f25df9a8'}
FIXED_MANIFEST_HASHES = {'cfbe153d13f902077981f8ce52beb2bdfd4bd843f9e30e512d20531cb55c9eb9',
                         '8a06a99dcc622eca4fddc6a60dcbc56e5d9e33871d6f3b80ebe1e27d87949dc1'}
MSVC_CAB_SHA256 = '6e8ee73933678c55973e83366e48e948b394c7a36743a36b7224c95de979b13f'
MSVC_DLLS = {
    'concrt140.dll': '54716f0738af891f283d213b5c8d11b25896bb8ee3097d301eae718560cf974e',
    'msvcp140.dll': '7c26614e1d733892c2deac7e245ce115504b1d80592dd0a01b08e3e5a55f89ca',
    'msvcp140_codecvt_ids.dll': '8a65c7596ef2e6938731f5a1058e7e40145b6d97967cc649231a076b9a608d78',
    'vccorlib140.dll': '09f93d5ff96ae09767f3e1af3cdd43a5a58f2598654fc63089429bb6f9f4737f',
    'vcruntime140.dll': 'd1f4225df2cd877dbf130d5668a021dce3f94118455ff5ec952061c30afc9ce7',
    'vcruntime140_1.dll': 'a7146c08f89fe5b04541ab507cdb59ff7b44534d4ba3c668a426c6450a03434e',
}
TEST_PREDECESSOR_HASHES = {'manifest.txt': 'ae16c1fe086fe56fb43600a3cfb802944e5aaafe73c9496294764ca228162488',
                           'launcher.sha256': 'd3fc2323ae236a0d213b8752fb10acc56e3cfd50bfb82830220f365248fc7837',
                           'uninstaller.sha256': '041ace070a415b0a92a513740b9fa6fe61bed2287f26f3bca97c4217208b2aac'}

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''): h.update(part)
    return h.hexdigest()

def compile_cs(output, sources, resources=(), references=()):
    cmd = [str(CSC), '/nologo', '/target:winexe', '/platform:x64', '/win32manifest:' + str(HERE / 'as-invoker.manifest')]
    cmd += ['/win32icon:' + str(ROOT / 'assets/kalka.ico')]
    cmd += ['/reference:' + str(x) for x in references]
    cmd += ['/resource:' + str(path) + ',' + name for path, name in resources]
    subprocess.run(cmd + ['/out:' + str(output)] + [str(s) for s in sources], check=True)

def launcher_source(portable=False):
    s = (ROOT / 'tools/onefile/launcher.cs').read_text(encoding='utf-8')
    old = 'if(!manifest.ContainsKey(name)) return false;\n                    actual++;'
    new = 'if(!manifest.ContainsKey(name)) {\n                        if(name=="CR20KB-Kalka.exe"||name=="Uninstall.exe") continue;\n                        return false;\n                    }\n                    actual++;'
    assert s.count(old) == 1
    s = s.replace(old, new)
    old = 'if(selected.StartsWith(cache+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))'
    new = 'if(selected.StartsWith(cache+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||selected.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))'
    assert s.count(old) == 1
    s = s.replace(old, new)
    begin = s.index('    private static string Prepare() {')
    end = s.index('    [MethodImpl(MethodImplOptions.NoInlining)]', begin)
    replacement = '''    private static string Prepare() {
        byte[] data;
        using(Stream s=Assembly.GetExecutingAssembly().GetManifestResourceStream("Kalka.bundle.manifest")) {
            if(s==null) throw new InvalidDataException("В приложении нет манифеста.");
            using(var m=new MemoryStream()) { s.CopyTo(m); data=m.ToArray(); }
        }
        manifest=ParseManifest(data);
        string root=Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        SetStatus("Проверка компонентов… / Verifying components…");
        if(!CheckCache(root)) throw new InvalidDataException("Компоненты приложения изменены или отсутствуют.");
        return root;
    }
'''
    s = (s[:begin] + replacement + s[end:]).replace('home, cache, state, profile, temp, version;', 'home, cache, state, profile, temp;')
    if portable:
        old = '''                string local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
                if (String.IsNullOrWhiteSpace(local) || !Path.IsPathRooted(local)) throw new IOException("Недоступна папка профиля LOCALAPPDATA.");
                home = Path.Combine(local, "CR20KB", "Kalka");'''
        new = '''                string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                home = Path.Combine(root, "KalkaData");
                CheckNoReparse(root,home);'''
        if s.count(old) != 1: raise ValueError('Unexpected launcher profile code')
        s = s.replace(old, new)
        old = '                string path = Prepare();\n                Environment.SetEnvironmentVariable("WEBVIEW2_BROWSER_EXECUTABLE_FOLDER", Path.Combine(path, "FixedRuntime"));'
        new = '''                string path = Prepare();
                splash.Hide();
                if(!AcceptComponentTerms(path)) return;
                splash.Show();
                Environment.SetEnvironmentVariable("WEBVIEW2_BROWSER_EXECUTABLE_FOLDER", Path.Combine(path, "FixedRuntime"));'''
        if s.count(old) != 1: raise ValueError('Unexpected launcher startup flow')
        s = s.replace(old, new)
        old = 'foreach(string sub in Directory.GetDirectories(directory)) { CheckNoReparse(path,sub); directories.Push(sub); }'
        new = 'foreach(string sub in Directory.GetDirectories(directory)) { CheckNoReparse(path,sub); if(String.Equals(sub,Path.Combine(path,"KalkaData"),StringComparison.OrdinalIgnoreCase)) continue; directories.Push(sub); }'
        if s.count(old) != 1: raise ValueError('Unexpected launcher directory check')
        s = s.replace(old, new).replace('name=="CR20KB-Kalka.exe"||name=="Uninstall.exe"', 'name=="Kalka.exe"||name=="Uninstall.exe"')
        old = 'private static string home, cache, state, profile, temp;'
        new = 'private static string home, cache, state, profile, temp, sessionTemp;'
        if s.count(old) != 1: raise ValueError('Unexpected launcher variables')
        s = s.replace(old, new)
        old = 'CheckNoReparse(home,cache); CheckNoReparse(home,state); CheckNoReparse(home,profile); CheckNoReparse(home,temp);'
        new = '''CheckNoReparse(home,cache); CheckNoReparse(home,state); CheckNoReparse(home,profile); CheckNoReparse(home,temp);
                CleanupStaleSessions();
                sessionTemp=Path.Combine(temp,"run-"+Guid.NewGuid().ToString("N"));
                CheckNoReparse(home,sessionTemp);
                if(Directory.Exists(sessionTemp)||File.Exists(sessionTemp)) throw new IOException("Временная папка уже существует.");
                Directory.CreateDirectory(sessionTemp); CheckNoReparse(home,sessionTemp);
                File.WriteAllText(Path.Combine(sessionTemp,".kalka-temp-owner"),Path.GetFileName(sessionTemp)+"\\n"+Process.GetCurrentProcess().Id,Encoding.ASCII);'''
        if s.count(old) != 1: raise ValueError('Unexpected launcher temporary setup')
        s = s.replace(old, new)
        s = s.replace('info.EnvironmentVariables["TEMP"] = temp; info.EnvironmentVariables["TMP"] = temp;',
                      'info.EnvironmentVariables["TEMP"] = sessionTemp; info.EnvironmentVariables["TMP"] = sessionTemp;')
        old = '} finally { if(splash!=null) splash.Dispose(); if(held) mutex.ReleaseMutex(); }'
        new = '} finally { if(splash!=null) splash.Dispose(); CleanupSessionTemp(sessionTemp,true); CleanupStaleSessions(); if(held) mutex.ReleaseMutex(); }'
        if s.count(old) != 1: raise ValueError('Unexpected launcher cleanup')
        s = s.replace(old, new)
        helper = '''    private static bool AcceptComponentTerms(string root) {
        string webview=Path.Combine(root,@"third_party_licenses\\webview2-fixed\\Microsoft-WebView2-Fixed-terms-en.txt");
        string python=Path.Combine(root,@"third_party_licenses\\python\\LICENSE.txt");
        string webviewText=File.ReadAllText(webview,Encoding.UTF8),pythonText=File.ReadAllText(python,Encoding.UTF8);
        string user=System.Security.Principal.WindowsIdentity.GetCurrent().User.Value;
        string fingerprint;
        using(var h=SHA256.Create()) fingerprint=Hex(h.ComputeHash(Encoding.UTF8.GetBytes("kalka-terms-v1\\n"+user+"\\n"+webviewText+"\\n"+pythonText)));
        string marker=Path.Combine(state,"component-consent-"+fingerprint+".txt");
        string record="CR20KB Kalka component consent v1\\n"+fingerprint+"\\n";
        CheckNoReparse(state,marker);
        if(File.Exists(marker)) {
            if(File.ReadAllText(marker,Encoding.ASCII)!=record) throw new IOException("Не удалось проверить запись согласия с условиями компонентов.");
            return true;
        }
        using(var dialog=new Form{Text="Калька — условия компонентов",Width=900,Height=720,MinimumSize=new Size(640,480),StartPosition=FormStartPosition.CenterScreen,FormBorderStyle=FormBorderStyle.Sizable,MaximizeBox=true,MinimizeBox=false}) {
            var summary=new Label{Dock=DockStyle.Top,Height=92,Padding=new Padding(12),Text="Перед запуском ознакомьтесь с условиями WebView2 и Python.\\nMicrosoft Defender SmartScreen включён по умолчанию и может передавать сведения Microsoft. Подробнее: aka.ms/privacy и Microsoft Edge Privacy Whitepaper."};
            var terms=new TabControl{Dock=DockStyle.Fill};
            foreach(var item in new[]{new[]{"Microsoft WebView2 (English)",webviewText},new[]{"Python (English)",pythonText}}) {
                var page=new TabPage(item[0]); var box=new TextBox{Dock=DockStyle.Fill,Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Both,WordWrap=false,Text=item[1].Replace("\\r\\n","\\n").Replace("\\n","\\r\\n")}; page.Controls.Add(box); terms.TabPages.Add(page);
            }
            var buttons=new FlowLayoutPanel{Dock=DockStyle.Bottom,Height=48,FlowDirection=FlowDirection.RightToLeft,Padding=new Padding(8)};
            var cancel=new Button{Name="DeclineTerms",Text="Отмена / Cancel",AutoSize=true,DialogResult=DialogResult.Cancel};
            var accept=new Button{Name="AcceptTerms",Text="Продолжить / Continue",AutoSize=true,Enabled=false};
            var agree=new CheckBox{Name="AgreeTerms",Dock=DockStyle.Bottom,Height=42,Padding=new Padding(12,0,0,0),Text="Я ознакомился и согласен с условиями WebView2 и Python / I agree"};
            agree.CheckedChanged+=(sender,args)=>accept.Enabled=agree.Checked;
            accept.Click+=(sender,args)=>{if(agree.Checked){dialog.DialogResult=DialogResult.OK;dialog.Close();}};
            buttons.Controls.Add(cancel);buttons.Controls.Add(accept);dialog.Controls.Add(terms);dialog.Controls.Add(agree);dialog.Controls.Add(buttons);dialog.Controls.Add(summary);dialog.AcceptButton=accept;dialog.CancelButton=cancel;
            if(dialog.ShowDialog()!=DialogResult.OK) return false;
        }
        CheckNoReparse(state,marker);
        using(var f=new FileStream(marker,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
            byte[] data=Encoding.ASCII.GetBytes(record);f.Write(data,0,data.Length);
        }
        return true;
    }
    private static void CleanupStaleSessions() {
        try {
            if(String.IsNullOrEmpty(temp)||!Directory.Exists(temp)) return;
            CheckNoReparse(home,temp);
            foreach(string dir in Directory.GetDirectories(temp))
                if(System.Text.RegularExpressions.Regex.IsMatch(Path.GetFileName(dir),@"^run-[0-9a-f]{32}$")) CleanupSessionTemp(dir,false);
        } catch(IOException ex) { System.Diagnostics.Debug.WriteLine(ex.Message); }
          catch(UnauthorizedAccessException ex) { System.Diagnostics.Debug.WriteLine(ex.Message); }
    }
    private static void CleanupSessionTemp(string candidate,bool current) {
        // Only a marked directory made by this launch is eligible. Unknown files,
        // documents and reparse points are retained rather than recursively deleted.
        try {
            if(String.IsNullOrEmpty(candidate)||!Directory.Exists(candidate)) return;
            CheckNoReparse(home,candidate);
            string marker=Path.Combine(candidate,".kalka-temp-owner");
            if(!File.Exists(marker)) return;
            string[] owner=File.ReadAllText(marker,Encoding.ASCII).Split('\\n');int pid;
            if(owner.Length!=2||owner[0]!=Path.GetFileName(candidate)||!Int32.TryParse(owner[1],out pid)||pid<=0) return;
            if(current) { if(pid!=Process.GetCurrentProcess().Id) return; }
            else { try { using(var process=Process.GetProcessById(pid)) { if(!process.HasExited) return; } } catch(ArgumentException) {} catch(System.ComponentModel.Win32Exception) { return; } catch(InvalidOperationException) { return; } }
            var pending=new Stack<string>(); var dirs=new List<string>(); var files=new List<string>(); pending.Push(candidate);
            while(pending.Count>0) {
                string dir=pending.Pop();CheckNoReparse(candidate,dir);dirs.Add(dir);
                foreach(string sub in Directory.GetDirectories(dir)) {
                    CheckNoReparse(candidate,sub);string name=Path.GetFileName(sub);
                    if(name!="_avast_" && !System.Text.RegularExpressions.Regex.IsMatch(name,@"^CR20KB-Kalka-[a-z0-9_]{8}$")) return;
                    pending.Push(sub);
                }
                foreach(string file in Directory.GetFiles(dir)) {
                    CheckNoReparse(candidate,file);
                    if(!String.Equals(file,marker,StringComparison.OrdinalIgnoreCase)) {
                        if(!System.Text.RegularExpressions.Regex.IsMatch(Path.GetFileName(file),@"^[a-z0-9_]{8}$") || new FileInfo(file).Length!=4 || File.ReadAllText(file,Encoding.ASCII)!="blat") return;
                    }
                    files.Add(file);
                }
            }
            foreach(string file in files) File.Delete(file);
            dirs.Reverse();foreach(string dir in dirs) Directory.Delete(dir,false);
        } catch(IOException ex) { System.Diagnostics.Debug.WriteLine(ex.Message); }
          catch(UnauthorizedAccessException ex) { System.Diagnostics.Debug.WriteLine(ex.Message); }
    }

'''
        s = s.replace('    private static void SetStatus(string value)', helper+'    private static void SetStatus(string value)')
    return s

def build(args):
    out = Path(args.output).resolve()
    if out.exists(): raise FileExistsError(out)
    portable_dir = Path(args.portable_dir).resolve() if getattr(args, 'portable_dir', None) else None
    if portable_dir is not None and portable_dir.exists(): raise FileExistsError(portable_dir)
    if not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}', args.version): raise ValueError('Invalid version')
    payload, fixed, sdk = Path(args.payload), Path(args.fixed), Path(args.sdk)
    if len(args.previous_setup) != len(args.previous_sha256) or len(args.previous_setup)+len(args.previous_meta) > 3:
        raise ValueError('Provide up to three previous installers with matching SHA-256 values')
    for folder in args.previous_meta:
        for name, digest in TEST_PREDECESSOR_HASHES.items():
            if sha(Path(folder)/name) != digest: raise ValueError('Previous metadata hash mismatch: ' + name)
    for path, digest in zip(args.previous_setup, args.previous_sha256):
        if not re.fullmatch(r'[0-9a-fA-F]{64}', digest) or sha(path) != digest.lower():
            raise ValueError('Previous installer hash mismatch')
    upstream_runtime = getattr(args, 'upstream_runtime', False)
    msvc_cab = None if upstream_runtime else Path(args.msvc_cab).resolve(strict=True)
    if msvc_cab is not None and sha(msvc_cab) != MSVC_CAB_SHA256:
        raise ValueError('Microsoft VC++ Redistributable x64 14.51.36247 CAB hash mismatch')
    if sha(payload) not in PAYLOAD_HASHES or sha(fixed / 'SHA256SUMS.txt') not in FIXED_MANIFEST_HASHES: raise ValueError('Audited input hash mismatch')
    with zipfile.ZipFile(payload) as verified:
        for name in ('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll', 'WebView2Loader.dll'):
            if hashlib.sha256(verified.read('webview/' + name)).hexdigest() != sha(sdk / name):
                raise ValueError('SDK differs from audited payload: ' + name)
        pillow_license = verified.read('runtime/Lib/site-packages/pillow-13.0.0.dist-info/licenses/LICENSE')
        pillow_sbom = verified.read('runtime/Lib/site-packages/pillow-13.0.0.dist-info/sboms/pillow-13.0.0.cdx.json')
        pdfium_prefix = 'runtime/Lib/site-packages/pypdfium2-5.14.0.dist-info/licenses/data/windows_x64/BUILD_LICENSES/'
        pdfium_licenses = {name[len(pdfium_prefix):]: verified.read(name) for name in verified.namelist() if name.startswith(pdfium_prefix) and not name.endswith('/')}
        if len(pdfium_licenses) != 19 or any('/' in name or '\\' in name or name in ('.', '..') for name in pdfium_licenses):
            raise ValueError('Unexpected PDFium build license set')
    spec = importlib.util.spec_from_file_location('bridge', ROOT / 'tools/save_bridge.py')
    bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='kalka-public-build-', dir=str(out.parent)) as tmp:
        tmp = Path(tmp); archive = tmp / 'bundle.zip'; rows = []
        msvc = {}
        if not upstream_runtime:
            for name, digest in MSVC_DLLS.items():
                member = name + '_amd64'
                subprocess.run(['expand.exe', str(msvc_cab), '-F:' + member, str(tmp)], check=True, stdout=subprocess.DEVNULL)
                extracted = tmp / member
                if sha(extracted) != digest: raise ValueError('Microsoft Redist DLL hash mismatch: ' + name)
                msvc[name] = extracted.read_bytes()
        source = str(msvc_cab) if msvc_cab else 'Not used: upstream distribution files retained'
        profile = os.environ.get('USERPROFILE')
        if profile:
            source = re.sub(re.escape(profile.rstrip('\\/')), lambda _: '<user-profile>', source, flags=re.IGNORECASE)
        source = re.sub(r'(?i)([a-z]:[\\/]users[\\/])[^\\/]+', r'\1<user>', source)
        report = ['Windows runtime provenance',
                  'Release build date: ' + datetime.now().astimezone().isoformat(timespec='seconds'),
                  'Architecture: x64', 'Version: ' + ('original upstream components' if upstream_runtime else '14.51.36247.0'),
                  'Official source CAB: ' + source, 'Source CAB SHA-256: ' + (MSVC_CAB_SHA256 if msvc_cab else 'not applicable')]
        for name, digest in (MSVC_DLLS.items() if not upstream_runtime else []):
            report += ['', 'DLL: ' + name, 'Version: 14.51.36247.0', 'SHA-256: ' + digest,
                       'Absolute source: ' + source + ' [member: ' + name + '_amd64]',
                       'Release paths: ' + (('app/runtime/' + name + ', ') if name.startswith('vcruntime') else '') + 'FixedRuntime/' + name]
        if upstream_runtime:
            report += ['', 'CPython embedded input SHA-256: 4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3',
                       'Combined runtime input SHA-256: ' + sha(payload),
                       'Microsoft WebView2 Fixed CAB SHA-256: fcf0cd55f7c6e8efced05114372de8b8ffc9032c0296d16e060d260637dfe5f2',
                       'Each upstream input is retained without replacement of its runtime DLLs.']
        report = ('\n'.join(report) + '\n').encode('utf-8')
        def add(z, name, data):
            base = Path(name).name.lower()
            if not upstream_runtime and re.fullmatch(r'(?:vcruntime|msvcp|msvcr|concrt|vcomp|vcamp|vccorlib|mfc|mfcm|api-ms-win-crt|ucrtbase)[a-z0-9_.-]*\.dll', base) and base not in MSVC_DLLS:
                raise ValueError('Unverified VC++ runtime component: ' + name)
            rows.append((name, len(data), hashlib.sha256(data).hexdigest())); z.writestr(name, data)
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
            with zipfile.ZipFile(payload) as old:
                for info in old.infolist():
                    if not info.is_dir() and info.filename.startswith(('runtime/', 'webview/')):
                        data = msvc[Path(info.filename).name] if not upstream_runtime and info.filename in ('runtime/vcruntime140.dll', 'runtime/vcruntime140_1.dll') else old.read(info)
                        add(z, 'app/' + info.filename, data)
            for name in ['kalka_core.py','kalka_export.py','kalka_compare.py','kalka_server.py','web/index.html','web/app.css','web/app.js','vendor/archivarius/compare_layers.js','vendor/archivarius/document_pages.py','vendor/archivarius/trace_geometry.js']:
                data = (ROOT / name).read_bytes()
                if name == 'web/app.js': data = bridge.patch_save_bridge(data)
                add(z, 'app/program/' + name, data)
            count = 0
            for line in (fixed / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
                digest, name = line.split('  ', 1)
                if name.startswith(('FixedRuntime/', 'third_party_licenses/')) or name == 'THIRD_PARTY_NOTICES.md':
                    file = fixed / name
                    if sha(file) != digest: raise ValueError('Audited file mismatch: ' + name)
                    if name.startswith('third_party_licenses/pypdfium2/data/windows_x64/BUILD_LICENSES/'):
                        count += 1
                        continue
                    data = msvc[Path(name).name] if not upstream_runtime and name.startswith('FixedRuntime/') and Path(name).name in MSVC_DLLS else file.read_bytes()
                    if name == 'third_party_licenses/pillow/LICENSE': data = pillow_license
                    elif name == 'third_party_licenses/pillow/pillow-12.3.0.cdx.json':
                        name, data = 'third_party_licenses/pillow/pillow-13.0.0.cdx.json', pillow_sbom
                    elif name == 'THIRD_PARTY_NOTICES.md': data = (ROOT/'THIRD_PARTY_NOTICES.md').read_bytes()
                    add(z, name, data); count += 1
            if count != 286: raise ValueError('Unexpected runtime file count')
            for name, data in sorted(pdfium_licenses.items()):
                add(z, 'third_party_licenses/pypdfium2/data/windows_x64/BUILD_LICENSES/' + name, data)
            add(z, 'docs/licensing/MSVC_RUNTIME_BUILD_INFO.txt', report)
            runtime_doc = 'UPSTREAM_RUNTIME.md' if upstream_runtime else 'MSVC_RUNTIME.md'
            add(z, 'docs/licensing/MSVC_RUNTIME.md', (ROOT / 'docs/licensing' / runtime_doc).read_bytes())
            add(z, 'third_party_licenses/KALKA-ADDITIONS.txt', (ROOT / 'THIRD_PARTY_ADDITIONS.txt').read_bytes())
            add(z, 'third_party_licenses/webview2-fixed/Microsoft-WebView2-Fixed-terms-en.txt', (ROOT / 'audit/Microsoft-WebView2-Fixed-terms-en.txt').read_bytes())
            add(z, 'third_party_licenses/kalka/LICENSE.txt', (ROOT / 'LICENSE').read_bytes())
        if len({r[0].lower() for r in rows}) != len(rows): raise ValueError('Duplicate paths')
        manifest = tmp / 'manifest.txt'; manifest.write_text(''.join('%s\t%d\t%s\n' % (h,n,name) for name,n,h in sorted(rows)), encoding='ascii')
        launchsource = tmp / 'launcher.cs'; launchsource.write_text(launcher_source(portable_dir is not None), encoding='utf-8')
        launch = tmp / 'CR20KB-Kalka.exe'
        refs = ['System.Windows.Forms.dll','System.Drawing.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll',sdk/'Microsoft.Web.WebView2.Core.dll',sdk/'Microsoft.Web.WebView2.WinForms.dll']
        compile_cs(launch, [launchsource], [(manifest,'Kalka.bundle.manifest')], refs)
        launchhash = tmp / 'launcher.hash'; launchhash.write_text(sha(launch), encoding='ascii')
        support = tmp / 'support.cs'; s = (HERE/'support.cs').read_text(encoding='utf-8').replace('Version = "1.0.0"','Version = "'+args.version+'"').replace(' — персональная сборка','').replace(' (персональная)','')
        if portable_dir is not None:
            s = s.replace('"CR20KB-Kalka.exe", UninstallerName', '"Kalka.exe", UninstallerName')
            old = 'foreach(string sub in Directory.GetDirectories(d)){CheckNoReparse(root,sub);if(!allowedDirs.Contains(sub))return false;todo.Push(sub);}'
            new = 'foreach(string sub in Directory.GetDirectories(d)){CheckNoReparse(root,sub);if(String.Equals(sub,Path.Combine(root,"KalkaData"),StringComparison.OrdinalIgnoreCase))continue;if(!allowedDirs.Contains(sub))return false;todo.Push(sub);}'
            if s.count(old) != 1: raise ValueError('Unexpected installer tree check')
            s = s.replace(old, new)
        support.write_text(s,encoding='utf-8')
        setup = tmp / 'setup.cs'; s = (HERE/'setup.cs').read_text(encoding='utf-8').replace('1.0.0.0',args.version+'.0').replace('установка 1.0.0','установка '+args.version).replace('Персональная сборка Кальки','Калька').replace('Проекты и действующая лицензия сохраняются.','Пользовательские проекты сохраняются.')
        setup.write_text(s,encoding='utf-8')
        refs = ['System.Windows.Forms.dll','System.Drawing.dll','System.IO.Compression.dll','System.IO.Compression.FileSystem.dll','Microsoft.CSharp.dll']
        uninstall = tmp / 'Uninstall.exe'; compile_cs(uninstall,[HERE/'uninstaller.cs',support],[(manifest,'Kalka.bundle.manifest'),(launchhash,'Kalka.launcher.hash')],refs)
        resources = [(archive,'Kalka.bundle'),(manifest,'Kalka.bundle.manifest'),(launch,'Kalka.application'),(uninstall,'Kalka.uninstaller'),(ROOT/'audit/Microsoft-WebView2-Fixed-terms-en.txt','Kalka.runtime.terms'),(fixed/'third_party_licenses/python/LICENSE.txt','Kalka.python.terms')]
        if args.previous_setup:
            extractor=tmp/'extract.exe'
            subprocess.run([str(CSC),'/nologo','/target:exe','/platform:x64','/out:'+str(extractor),str(HERE/'extract_resources.cs')],check=True)
            for index, previous in enumerate(args.previous_setup):
                folder=tmp/('previous-'+str(index));folder.mkdir()
                subprocess.run([str(extractor),str(Path(previous).resolve()),str(folder),'setup'],check=True)
                launch_digest=folder/'previous-launcher.hash';launch_digest.write_text(sha(folder/'previous-application.exe'),encoding='ascii')
                uninstall_digest=folder/'previous-uninstaller.hash';uninstall_digest.write_text(sha(folder/'previous-uninstaller.exe'),encoding='ascii')
                prefix='Kalka.previous'+(str(index+1) if index else '')
                resources.extend([(folder/'previous-manifest.txt',prefix+'.manifest'),(launch_digest,prefix+'.launcher.hash'),(uninstall_digest,prefix+'.uninstaller.hash')])
        for index,folder in enumerate(args.previous_meta,start=len(args.previous_setup)):
            folder=Path(folder);prefix='Kalka.previous'+(str(index+1) if index else '')
            resources.extend([(folder/'manifest.txt',prefix+'.manifest'),(folder/'launcher.sha256',prefix+'.launcher.hash'),(folder/'uninstaller.sha256',prefix+'.uninstaller.hash')])
        compile_cs(out,[setup,support],resources,refs)
        if portable_dir is not None:
            portable_dir.mkdir(parents=True)
            with zipfile.ZipFile(archive) as z:
                for name, size, digest in rows:
                    if name.startswith('/') or '\\' in name or ':' in name or '..' in Path(name).parts:
                        raise ValueError('Unsafe payload path: ' + name)
                    target = portable_dir.joinpath(*name.split('/'))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(name) as source, target.open('xb') as dest: shutil.copyfileobj(source, dest)
                    if target.stat().st_size != size or sha(target) != digest: raise ValueError('Portable payload mismatch: ' + name)
            shutil.copyfile(launch, portable_dir/'Kalka.exe')
            if sha(portable_dir/'Kalka.exe') != sha(launch): raise ValueError('Portable launcher mismatch')
    print('TEST SETUP',out,'bytes',out.stat().st_size,'SHA256',sha(out))

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); p.add_argument('--version',required=True); p.add_argument('--payload',required=True); p.add_argument('--fixed',required=True); p.add_argument('--sdk',required=True); p.add_argument('--msvc-cab'); p.add_argument('--upstream-runtime',action='store_true'); p.add_argument('--portable-dir'); p.add_argument('--previous-setup',action='append',default=[]); p.add_argument('--previous-sha256',action='append',default=[]); p.add_argument('--previous-meta',action='append',default=[]); args=p.parse_args(); p.error('--msvc-cab is required unless --upstream-runtime is set') if not args.upstream_runtime and not args.msvc_cab else None; build(args)
