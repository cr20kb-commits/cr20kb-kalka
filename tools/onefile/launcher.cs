using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.WinForms;
using Microsoft.Web.WebView2.Core;

internal static class OneFileLauncher {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern bool SetDllDirectory(string path);
    private sealed class Entry { public string Hash; public long Size; public string Name; }
    private sealed class GateBlockedException : Exception { }
    private static string home, cache, state, profile, temp, version;
    private static Form splash;
    private static Label status;
    private static Dictionary<string, Entry> manifest;
    private static readonly List<Dictionary<string, Entry>> trustedCleanup = new List<Dictionary<string, Entry>>();

    [STAThread]
    private static void Main() {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        using (var mutex = new Mutex(false, "Local\\CR20KB-Kalka-onefile-owner")) {
            bool held = false;
            try {
                try { held = mutex.WaitOne(0); } catch (AbandonedMutexException) { held = true; }
                if (!held) throw new IOException("Калька уже открыта. Закройте её перед повторным запуском.");
                string local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
                if (String.IsNullOrWhiteSpace(local) || !Path.IsPathRooted(local)) throw new IOException("Недоступна папка профиля LOCALAPPDATA.");
                home = Path.Combine(local, "CR20KB", "Kalka");
                cache = Path.Combine(home, "cache"); state = Path.Combine(home, "license");
                profile = Path.Combine(home, "WebViewProfile"); temp = Path.Combine(home, "temp");
                Directory.CreateDirectory(cache); Directory.CreateDirectory(state); Directory.CreateDirectory(profile); Directory.CreateDirectory(temp);
                CheckNoReparse(home,cache); CheckNoReparse(home,state); CheckNoReparse(home,profile); CheckNoReparse(home,temp);
                splash = new Form { Text="CR20KB Калька — подготовка / Preparing", Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath), Width=560, Height=150, StartPosition=FormStartPosition.CenterScreen, FormBorderStyle=FormBorderStyle.FixedDialog, MaximizeBox=false, MinimizeBox=false, ControlBox=false };
                status = new Label { AutoSize=false, Dock=DockStyle.Fill, TextAlign=ContentAlignment.MiddleCenter, Text="Подготовка программы… / Preparing…" };
                splash.Controls.Add(status); splash.Show(); Application.DoEvents();
                string path = Prepare();
                Environment.SetEnvironmentVariable("WEBVIEW2_BROWSER_EXECUTABLE_FOLDER", Path.Combine(path, "FixedRuntime"));
                Environment.SetEnvironmentVariable("WEBVIEW2_USER_DATA_FOLDER", profile);
                SetStatus("Запуск приложения… / Starting application…");
                string libraries = Path.Combine(path, "app", "webview");
                AppDomain.CurrentDomain.AssemblyResolve += (sender, args) => {
                    string name = new AssemblyName(args.Name).Name;
                    if (name != "Microsoft.Web.WebView2.Core" && name != "Microsoft.Web.WebView2.WinForms") return null;
                    return Assembly.LoadFrom(Path.Combine(libraries, name + ".dll"));
                };
                if (!SetDllDirectory(libraries)) throw new IOException("Не удалось загрузить компоненты WebView2.");
                string python = Path.Combine(path, "app", "runtime", "python.exe");
                string program = Path.Combine(path, "app", "program");
                var info = new ProcessStartInfo(python, "-u \"" + Path.Combine(program, "kalka_server.py") + "\" --native") { UseShellExecute=false, CreateNoWindow=true, RedirectStandardOutput=true, RedirectStandardError=true, WorkingDirectory=program };
                info.EnvironmentVariables["KALKA_APP_DIR"] = state;
                info.EnvironmentVariables["TEMP"] = temp; info.EnvironmentVariables["TMP"] = temp;
                info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                using (Process child = Process.Start(info)) {
                    if (child == null) throw new IOException("Не удалось запустить внутренний сервер.");
                    child.ErrorDataReceived += (s,e) => { }; child.BeginErrorReadLine();
                    string url = child.StandardOutput.ReadLine(); Uri address;
                    if (!Uri.TryCreate(url, UriKind.Absolute, out address) || address.Host != "127.0.0.1" || address.Scheme != "http") throw new IOException("Не удалось запустить локальный сервер.");
                    try { splash.Hide(); ShowWindow(path, address, child); }
                    finally {
                        try {
                            var req=(HttpWebRequest)WebRequest.Create(new Uri(address.GetLeftPart(UriPartial.Authority)+"/api/shutdown"));
                            req.Method="POST"; req.Timeout=3000; req.Headers["X-Kalka-Token"]=address.Fragment.TrimStart('#');
                            byte[] data=Encoding.UTF8.GetBytes("{}"); req.ContentLength=data.Length;
                            using(Stream output=req.GetRequestStream()) output.Write(data,0,data.Length);
                            using(WebResponse response=req.GetResponse()) { }
                        } catch { }
                        if (!child.WaitForExit(5000)) { child.Kill(); child.WaitForExit(); }
                    }
                }
            } catch (Exception ex) {
                MessageBox.Show("Не удалось подготовить или запустить Кальку. Проверьте свободное место, доступ к папке профиля и целостность EXE.\n\n" + ex.Message,
                    "CR20KB Калька", MessageBoxButtons.OK, MessageBoxIcon.Error);
            } finally { if(splash!=null) splash.Dispose(); if(held) mutex.ReleaseMutex(); }
        }
    }

    private static void SetStatus(string value) { status.Text=value; Application.DoEvents(); }
    private static string Hex(byte[] data) { return BitConverter.ToString(data).Replace("-", "").ToLowerInvariant(); }
    private static string Digest(Stream stream) { using(var hash=SHA256.Create()) return Hex(hash.ComputeHash(stream)); }
    private static string DigestFile(string path) { using(var stream=File.OpenRead(path)) return Digest(stream); }
    private static string SafePath(string basePath, string name) {
        if (name.IndexOf('\\')>=0 || name.StartsWith("/") || name.IndexOf(':')>=0) throw new InvalidDataException("Недопустимый путь в комплекте.");
        string p=Path.GetFullPath(Path.Combine(basePath,name.Replace('/',Path.DirectorySeparatorChar)));
        if (!p.StartsWith(basePath+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Недопустимый путь в комплекте.");
        return p;
    }
    private static void CheckNoReparse(string root, string path) {
        string p=path;
        while (p.Length>=root.Length) {
            if ((File.Exists(p)||Directory.Exists(p)) && (File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0) throw new IOException("Ссылки в служебном кэше не поддерживаются.");
            if (String.Equals(p,root,StringComparison.OrdinalIgnoreCase)) break;
            p=Path.GetDirectoryName(p); if(p==null) throw new IOException("Недопустимый путь кэша.");
        }
    }
    private static bool CheckCache(string path) {
        if(!Directory.Exists(path)) return false;
        try {
            var directories=new Stack<string>(); directories.Push(path); int actual=0;
            while(directories.Count>0) {
                string directory=directories.Pop(); CheckNoReparse(path,directory);
                foreach(string sub in Directory.GetDirectories(directory)) { CheckNoReparse(path,sub); directories.Push(sub); }
                foreach(string file in Directory.GetFiles(directory)) {
                    CheckNoReparse(path,file);
                    string name=file.Substring(path.Length+1).Replace(Path.DirectorySeparatorChar,'/');
                    if(!manifest.ContainsKey(name)) return false;
                    actual++;
                }
            }
            if(actual!=manifest.Count) return false;
            int index=0;
            foreach(var e in manifest.Values) {
                string file=SafePath(path,e.Name); CheckNoReparse(path,file);
                if(!File.Exists(file) || new FileInfo(file).Length!=e.Size || DigestFile(file)!=e.Hash) return false;
                if((++index%20)==0) SetStatus("Проверка кэша: " + index + " / " + manifest.Count);
            }
            return true;
        } catch(IOException) { return false; } catch(UnauthorizedAccessException) { return false; }
    }
    private static void CleanTrackedCache(string directory) {
        // Only complete files matching an embedded, trusted manifest may be removed.
        // Partial, modified and unknown files are left at their existing paths.
        try {
            CheckNoReparse(cache,directory);
            foreach(var known in trustedCleanup) foreach(var e in known.Values) {
                string file=SafePath(directory,e.Name);
                try {
                    CheckNoReparse(directory,file);
                    if(file.EndsWith(".kalka",StringComparison.OrdinalIgnoreCase)) continue;
                    if(File.Exists(file) && new FileInfo(file).Length==e.Size && DigestFile(file)==e.Hash) File.Delete(file);
                } catch(IOException) { } catch(UnauthorizedAccessException) { }
            }
            var pending=new Stack<string>(); var visited=new List<string>(); pending.Push(directory);
            while(pending.Count>0) {
                string p=pending.Pop(); CheckNoReparse(directory,p); visited.Add(p);
                foreach(string sub in Directory.GetDirectories(p)) { CheckNoReparse(directory,sub); pending.Push(sub); }
            }
            visited.Reverse(); foreach(string p in visited) { try { Directory.Delete(p,false); } catch(IOException) { } }
        } catch(IOException) { } catch(UnauthorizedAccessException) { }
    }
    private static void CleanOldCaches(string current) {
        foreach(string dir in Directory.GetDirectories(cache)) {
            string n=Path.GetFileName(dir);
            if(String.Equals(dir,current,StringComparison.OrdinalIgnoreCase)) continue;
            if(System.Text.RegularExpressions.Regex.IsMatch(n,@"^(v-[0-9a-f]{16}(-[0-9a-f]{8})?|s-[0-9a-f]{8}-[0-9a-f]{8}|rejected-[0-9a-f]{32})$")) CleanTrackedCache(dir);
        }
    }
    private static Dictionary<string,Entry> ParseManifest(byte[] data) {
        var result=new Dictionary<string,Entry>(StringComparer.OrdinalIgnoreCase);
        foreach(string line in Encoding.ASCII.GetString(data).Split(new[]{'\n'},StringSplitOptions.RemoveEmptyEntries)) {
            string[] f=line.TrimEnd('\r').Split('\t'); long size;
            if(f.Length!=3 || f[0].Length!=64 || !Int64.TryParse(f[1],out size) || size<0 || result.ContainsKey(f[2])) throw new InvalidDataException("Повреждён манифест комплекта.");
            SafePath(cache,f[2]); result.Add(f[2],new Entry{Hash=f[0],Size=size,Name=f[2]});
        }
        return result;
    }
    private static string Prepare() {
        byte[] data;
        using(Stream s=Assembly.GetExecutingAssembly().GetManifestResourceStream("Kalka.bundle.manifest")) {
            if(s==null) throw new InvalidDataException("В комплекте нет манифеста.");
            using(var m=new MemoryStream()) { s.CopyTo(m); data=m.ToArray(); }
        }
        using(var hash=SHA256.Create()) version=Hex(hash.ComputeHash(data));
        manifest=ParseManifest(data); trustedCleanup.Clear(); trustedCleanup.Add(manifest);
        foreach(string name in Assembly.GetExecutingAssembly().GetManifestResourceNames()) {
            if(!name.StartsWith("Kalka.cleanup.",StringComparison.Ordinal)) continue;
            byte[] old;
            using(Stream s=Assembly.GetExecutingAssembly().GetManifestResourceStream(name)) using(var m=new MemoryStream()) { s.CopyTo(m); old=m.ToArray(); }
            string digest; using(var hash=SHA256.Create()) digest=Hex(hash.ComputeHash(old));
            if(name!="Kalka.cleanup."+digest) throw new InvalidDataException("Повреждён манифест старого кэша.");
            trustedCleanup.Add(ParseManifest(old));
        }
        if(manifest.Count<300 || !manifest.ContainsKey("FixedRuntime/msedgewebview2.exe") || !manifest.ContainsKey("app/runtime/python.exe")) throw new InvalidDataException("Комплект неполон.");
        string prefix="v-"+version.Substring(0,16), final=Path.Combine(cache,prefix);
        foreach(string existing in Directory.GetDirectories(cache)) {
            string name=Path.GetFileName(existing);
            if((name==prefix || System.Text.RegularExpressions.Regex.IsMatch(name,"^"+prefix+"-[0-9a-f]{8}$")) && CheckCache(existing)) {
                CleanOldCaches(existing); return existing;
            }
        }
        CleanOldCaches(final);
        SetStatus("Первый запуск: распаковка и проверка… / Preparing and verifying…");
        string staging=Path.Combine(cache,"s-"+version.Substring(0,8)+"-"+Guid.NewGuid().ToString("N").Substring(0,8)); Directory.CreateDirectory(staging);
        var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        using(Stream input=Assembly.GetExecutingAssembly().GetManifestResourceStream("Kalka.bundle")) {
            if(input==null) throw new InvalidDataException("Комплект компонентов отсутствует.");
            using(var zip=new ZipArchive(input,ZipArchiveMode.Read)) {
                int count=0;
                foreach(ZipArchiveEntry item in zip.Entries) {
                    Entry expected;
                    if(!manifest.TryGetValue(item.FullName,out expected) || !seen.Add(item.FullName) || item.Length!=expected.Size) throw new InvalidDataException("Повреждён состав комплекта.");
                    string file=SafePath(staging,item.FullName); Directory.CreateDirectory(Path.GetDirectoryName(file));
                    string partial=file+".part";
                    using(Stream source=item.Open()) using(var output=new FileStream(partial,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {
                        byte[] buffer=new byte[1024*1024]; int n; long total=0;
                        while((n=source.Read(buffer,0,buffer.Length))>0) { total+=n; if(total>expected.Size) throw new InvalidDataException("Повреждён размер компонента."); output.Write(buffer,0,n); }
                        if(total!=expected.Size) throw new InvalidDataException("Неполный компонент.");
                    }
                    if(DigestFile(partial)!=expected.Hash) throw new InvalidDataException("Ошибка целостности: "+item.FullName);
                    File.Move(partial,file);
                    SetStatus("Подготовка компонентов: "+(++count)+" / "+manifest.Count);
                }
            }
        }
        if(seen.Count!=manifest.Count || !CheckCache(staging)) throw new InvalidDataException("Комплект распакован не полностью.");
        if(Directory.Exists(final)) {
            CheckNoReparse(cache,final);
            final=Path.Combine(cache,prefix+"-"+Guid.NewGuid().ToString("N").Substring(0,8));
        }
        Directory.Move(staging,final);
        CleanOldCaches(final);
        return final;
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void ShowWindow(string root, Uri address, Process child) {
        string fixedRuntime=Path.Combine(root,"FixedRuntime");
        var form=new Form { Text="CR20KB — Калька", Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath), Width=1450, Height=900, MinimumSize=new Size(900,600), StartPosition=FormStartPosition.CenterScreen };
        var menu=new MenuStrip(); var about=new ToolStripMenuItem("О программе / About / 关于");
        var licenses=new ToolStripMenuItem("Лицензии / Licenses / 许可");
        licenses.Click+=(s,e)=>ShowLicenses(form,root); about.DropDownItems.Add(licenses);
        menu.Items.Add(about);
        var view=new WebView2 { Dock=DockStyle.Fill };
        form.Controls.Add(view); form.Controls.Add(menu); form.MainMenuStrip=menu;
        child.EnableRaisingEvents=true; child.Exited+=(s,e)=>{try{if(!form.IsDisposed && form.IsHandleCreated) form.BeginInvoke((Action)(()=>form.Close()));}catch(InvalidOperationException){}};
        form.Shown+=async(s,e)=>{
            try {
                var environment=await CoreWebView2Environment.CreateAsync(fixedRuntime,profile);
                await view.EnsureCoreWebView2Async(environment);
                view.CoreWebView2.Settings.AreDevToolsEnabled=false; view.CoreWebView2.Settings.AreDefaultContextMenusEnabled=false;
                view.CoreWebView2.NavigationStarting+=(a,b)=>{Uri dest; if(!Uri.TryCreate(b.Uri,UriKind.Absolute,out dest)||dest.GetLeftPart(UriPartial.Authority)!=address.GetLeftPart(UriPartial.Authority)) b.Cancel=true;};
                view.CoreWebView2.NewWindowRequested+=(a,b)=>{b.Handled=true;};
                view.CoreWebView2.DownloadStarting+=(a,b)=>{b.Cancel=true;};
                view.CoreWebView2.WebMessageReceived+=async(a,b)=>{
                    string job=null, temporary=null;
                    try {
                        Uri origin;
                        if(!Uri.TryCreate(b.Source,UriKind.Absolute,out origin) || origin.GetLeftPart(UriPartial.Authority)!=address.GetLeftPart(UriPartial.Authority)) return;
                        string[] parts=b.TryGetWebMessageAsString().Split('\t');
                        if(parts.Length!=3 || parts[0]!="save" || !System.Text.RegularExpressions.Regex.IsMatch(parts[1],@"^[0-9a-f]{32}$")) return;
                        job=parts[1]; string name=Path.GetFileName(parts[2]);
                        if(String.IsNullOrWhiteSpace(name) || name!=parts[2] || name.IndexOfAny(Path.GetInvalidFileNameChars())>=0 || !(name.EndsWith(".kalka",StringComparison.OrdinalIgnoreCase)||name.EndsWith(".png",StringComparison.OrdinalIgnoreCase))) throw new InvalidDataException("Недопустимое имя результата.");
                        string selected;
                        using(var dialog=new SaveFileDialog { FileName=name, AddExtension=true, OverwritePrompt=true, DefaultExt=Path.GetExtension(name).TrimStart('.'), Filter=name.EndsWith(".kalka",StringComparison.OrdinalIgnoreCase)?"Проект Калька (*.kalka)|*.kalka":"PNG (*.png)|*.png" }) {
                            if(dialog.ShowDialog(form)!=DialogResult.OK) { view.CoreWebView2.PostWebMessageAsString("save-result\t"+job+"\tCANCEL"); return; }
                            selected=Path.GetFullPath(dialog.FileName);
                        }
                        if(selected.StartsWith(cache+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new IOException("Выберите папку вне служебного кэша.");
                        temporary=Path.Combine(Path.GetDirectoryName(selected),".kalka-save-"+Guid.NewGuid().ToString("N")+".tmp");
                        string target=temporary;
                        await Task.Run(()=>CopyJobResult(address,job,target));
                        if(File.Exists(selected)) File.Replace(temporary,selected,null); else File.Move(temporary,selected);
                        temporary=null;
                        view.CoreWebView2.PostWebMessageAsString("save-result\t"+job+"\tOK");
                    } catch(Exception ex) {
                        if(temporary!=null) { try { File.Delete(temporary); } catch { } }
                        if(ex is GateBlockedException) { if(job!=null) view.CoreWebView2.PostWebMessageAsString("save-result\t"+job+"\tGATE"); }
                        else { MessageBox.Show(form,"Не удалось сохранить файл.\n\n"+ex.Message,"CR20KB Калька",MessageBoxButtons.OK,MessageBoxIcon.Error); if(job!=null) view.CoreWebView2.PostWebMessageAsString("save-result\t"+job+"\tERROR\tНе удалось сохранить файл."); }
                    }
                };
                view.Source=address;
            } catch(Exception ex) { MessageBox.Show(form,"WebView2: "+ex.Message,"CR20KB Калька",MessageBoxButtons.OK,MessageBoxIcon.Error); form.Close(); }
        };
        Application.Run(form); view.Dispose(); form.Dispose();
    }
    private static void CopyJobResult(Uri address,string job,string target) {
        var request=(HttpWebRequest)WebRequest.Create(new Uri(address.GetLeftPart(UriPartial.Authority)+"/api/result"));
        request.Proxy=null; request.Method="POST"; request.Timeout=30000; request.ReadWriteTimeout=30000;
        request.ContentType="application/json"; request.Headers["X-Kalka-Token"]=address.Fragment.TrimStart('#');
        byte[] body=Encoding.ASCII.GetBytes("{\"job\":\""+job+"\"}"); request.ContentLength=body.Length;
        using(Stream output=request.GetRequestStream()) output.Write(body,0,body.Length);
        try { using(var response=(HttpWebResponse)request.GetResponse()) using(Stream input=response.GetResponseStream()) using(var file=new FileStream(target,FileMode.CreateNew,FileAccess.Write,FileShare.None)) input.CopyTo(file); }
        catch(WebException ex) { using(var response=ex.Response as HttpWebResponse) { if(response!=null && response.StatusCode==HttpStatusCode.Forbidden) throw new GateBlockedException(); } throw; }
    }
    private static void ShowLicenses(Form parent,string root) {
        using(var box=new Form { Text="Лицензии / Licenses / 许可", Width=1000, Height=700, StartPosition=FormStartPosition.CenterParent }) {
            var list=new ListBox { Dock=DockStyle.Left, Width=310, HorizontalScrollbar=true }; var text=new TextBox { Dock=DockStyle.Fill, Multiline=true, ReadOnly=true, ScrollBars=ScrollBars.Vertical, WordWrap=true, Font=new Font(FontFamily.GenericMonospace,9) };
            var credits=new Button { Dock=DockStyle.Bottom, Height=34, Text="WebView2: уведомления Chromium / third-party credits" };
            string notices=Path.Combine(root,"third_party_licenses");
            list.Items.Add("THIRD_PARTY_NOTICES.md");
            foreach(string file in Directory.GetFiles(notices,"*",SearchOption.AllDirectories)) list.Items.Add(file.Substring(root.Length+1));
            foreach(string name in new[]{@"FixedRuntime\Trust Protection Lists\Mu\LICENSE",@"FixedRuntime\Trust Protection Lists\Sigma\LICENSE",@"FixedRuntime\WidevineCdm\LICENSE"}) if(File.Exists(Path.Combine(root,name))) list.Items.Add(name);
            list.SelectedIndexChanged+=(s,e)=>{string name=(string)list.SelectedItem; string p=Path.Combine(root,name); string content=File.ReadAllText(p,Encoding.UTF8).Replace("\r\n","\n").Replace("\n","\r\n"); if(name=="THIRD_PARTY_NOTICES.md") content="Тексты из комплекта доступны в этом окне. Для WebView2 нажмите кнопку Credits ниже.\r\nAll included notices are available here; use the Credits button for WebView2.\r\n\r\n"+content; text.Text=content; text.SelectionStart=0; text.ScrollToCaret();};
            credits.Click+=(s,e)=>{try { if(!CheckCache(root)) throw new InvalidDataException("Служебные компоненты изменены. Закройте и снова откройте программу для восстановления."); Process.Start(new ProcessStartInfo(Path.Combine(root,"FixedRuntime","msedgewebview2.exe"),"--embedded-browser-webview=show-credits --user-data-dir=\""+Path.Combine(profile,"Credits")+"\""){UseShellExecute=false}); } catch(Exception ex){MessageBox.Show(box,ex.Message);} };
            box.Controls.Add(text); box.Controls.Add(list); box.Controls.Add(credits); list.SelectedIndex=0; box.ShowDialog(parent);
        }
    }
}
