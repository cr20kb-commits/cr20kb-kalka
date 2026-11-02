using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Win32;

internal static class InstallSupport {
    [DllImport("shell32.dll", CharSet=CharSet.Unicode)]
    private static extern void SHChangeNotify(uint eventId,uint flags,string item1,string item2);
    internal sealed class Entry { internal string Name, Hash; internal long Size; }
    internal const string RegPath = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\CR20KB-Kalka";
    internal const string LauncherName = "CR20KB-Kalka.exe", UninstallerName = "Uninstall.exe";
    internal const string Version = "1.0.0";
    internal const string ApplicationId = "CR20KB.Kalka";
    internal const string OwnershipMarker = "CR20KB.Kalka/install-v1";
    internal static string Local() {
        string value=Environment.GetEnvironmentVariable("LOCALAPPDATA");
        if(String.IsNullOrWhiteSpace(value)||!Path.IsPathRooted(value)) throw new IOException("Недоступна папка LOCALAPPDATA.");
        return Path.GetFullPath(value).TrimEnd(Path.DirectorySeparatorChar);
    }
    internal static string Root() { return Path.Combine(Local(),"Programs","CR20KB","Kalka"); }
    internal static string Shortcut() {
        string value=Environment.GetEnvironmentVariable("APPDATA");
        if(String.IsNullOrWhiteSpace(value)||!Path.IsPathRooted(value)) throw new IOException("Недоступна папка меню пользователя.");
        return Path.Combine(Path.GetFullPath(value),"Microsoft","Windows","Start Menu","Programs","Калька.lnk");
    }
    internal static string Desktop() {
        string value=null;
        using(var key=Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",false))
            if(key!=null)value=Convert.ToString(key.GetValue("Desktop",null,RegistryValueOptions.DoNotExpandEnvironmentNames));
        if(!String.IsNullOrWhiteSpace(value))value=Environment.ExpandEnvironmentVariables(value);
        if(String.IsNullOrWhiteSpace(value)) {
            string profile=Environment.GetEnvironmentVariable("USERPROFILE");
            if(String.IsNullOrWhiteSpace(profile)||!Path.IsPathRooted(profile))return null;
            value=Path.Combine(profile,"Desktop");
        }
        return Path.IsPathRooted(value)?Path.GetFullPath(value):null;
    }
    private static string ShortcutTarget(string link) {
        if((File.GetAttributes(link)&FileAttributes.ReparsePoint)!=0)throw new IOException("Ссылка на ярлык не поддерживается.");
        dynamic shell=Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));dynamic shortcut=shell.CreateShortcut(link);
        return Convert.ToString(shortcut.TargetPath);
    }
    private static bool ShortcutFailure(Exception ex) {
        return ex is IOException || ex is UnauthorizedAccessException || ex is COMException || ex is ArgumentException || ex is NotSupportedException || ex is System.Security.SecurityException;
    }
    private static bool IsOwnedOrStaleShortcut(string link,string root) {
        try {
            try { var attrs=File.GetAttributes(link);if((attrs&(FileAttributes.ReparsePoint|FileAttributes.Directory))!=0)return false; }
            catch(FileNotFoundException) { return true; }
            catch(DirectoryNotFoundException) { return true; }
            string target=ShortcutTarget(link);
            if(String.IsNullOrWhiteSpace(target)||!Path.IsPathRooted(target)||target.StartsWith(@"\\"))return false;
            target=Path.GetFullPath(target);
            if(String.Equals(target,Path.Combine(root,LauncherName),StringComparison.OrdinalIgnoreCase)||
               String.Equals(target,Path.Combine(root,"CR20KB-Kalka.exe"),StringComparison.OrdinalIgnoreCase))return true;
            try { File.GetAttributes(target); }
            catch(FileNotFoundException) { return true; }
            catch(DirectoryNotFoundException) { return true; }
            string name=Path.GetFileName(target);
            if(!name.Equals("Kalka.exe",StringComparison.OrdinalIgnoreCase)&&!name.Equals("CR20KB-Kalka.exe",StringComparison.OrdinalIgnoreCase)&&!name.Equals("Калька.exe",StringComparison.OrdinalIgnoreCase))return false;
            string actual=DigestFile(target);
            foreach(string prefix in new[]{"Kalka.previous","Kalka.previous2","Kalka.previous3"}) {
                using(var s=Assembly.GetExecutingAssembly().GetManifestResourceStream(prefix+".launcher.hash")) {
                    if(s==null)continue;
                    using(var r=new StreamReader(s,Encoding.ASCII))if(String.Equals(actual,r.ReadToEnd().Trim(),StringComparison.OrdinalIgnoreCase))return true;
                }
            }
        } catch(Exception ex) { if(!ShortcutFailure(ex))throw; }
        return false;
    }
    private static bool WriteShortcut(string link,string root) {
        try {
            if(!IsOwnedOrStaleShortcut(link,root))return false;
            dynamic shell=Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));dynamic sc=shell.CreateShortcut(link);
            sc.TargetPath=Path.Combine(root,LauncherName);sc.WorkingDirectory=root;sc.Description="CR20KB Калька";sc.IconLocation=Path.Combine(root,LauncherName)+",0";sc.Save();
            SHChangeNotify(0x00002000,0x0005,link,null);return true;
        } catch(Exception ex) { if(!ShortcutFailure(ex))throw;return false; }
    }
    internal static string SafePath(string root,string name) {
        if(String.IsNullOrEmpty(name)||name.IndexOf('\\')>=0||name.StartsWith("/")||name.IndexOf(':')>=0) throw new InvalidDataException("Недопустимый путь компонента.");
        string p=Path.GetFullPath(Path.Combine(root,name.Replace('/',Path.DirectorySeparatorChar)));
        if(!p.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Путь выходит за папку приложения.");
        return p;
    }
    internal static void CheckNoReparse(string root,string path) {
        root=Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);path=Path.GetFullPath(path);
        if(!path.Equals(root,StringComparison.OrdinalIgnoreCase)&&!path.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new IOException("Путь выходит за папку пользователя.");
        string p=path;
        while(p.Length>=root.Length) {
            if((File.Exists(p)||Directory.Exists(p))&&(File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0) throw new IOException("Ссылки в папке установки не поддерживаются: "+p);
            if(String.Equals(p,root,StringComparison.OrdinalIgnoreCase)) break;
            p=Path.GetDirectoryName(p);if(p==null)throw new IOException("Недопустимый путь.");
        }
    }
    internal static string Digest(Stream stream) { using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(stream)).Replace("-","").ToLowerInvariant(); }
    internal static string DigestFile(string path) { using(var s=File.OpenRead(path))return Digest(s); }
    internal static string ResourceHash(string name) { using(var s=Assembly.GetExecutingAssembly().GetManifestResourceStream(name)){if(s==null)throw new InvalidDataException("Неполный установщик.");return Digest(s);} }
    internal static Dictionary<string,Entry> Manifest(string resource="Kalka.bundle.manifest") {
        byte[] data;using(var s=Assembly.GetExecutingAssembly().GetManifestResourceStream(resource)){if(s==null)throw new InvalidDataException("Нет манифеста.");using(var m=new MemoryStream()){s.CopyTo(m);data=m.ToArray();}}
        var entries=new Dictionary<string,Entry>(StringComparer.OrdinalIgnoreCase);
        foreach(string line in Encoding.ASCII.GetString(data).Split(new[]{'\n'},StringSplitOptions.RemoveEmptyEntries)) {
            string[] f=line.TrimEnd('\r').Split('\t');long n;
            if(f.Length!=3||f[0].Length!=64||!Int64.TryParse(f[1],out n)||n<0||entries.ContainsKey(f[2]))throw new InvalidDataException("Повреждён манифест.");
            SafePath(Root(),f[2]);entries.Add(f[2],new Entry{Name=f[2],Hash=f[0],Size=n});
        }
        if(entries.Count<300||!entries.ContainsKey("FixedRuntime/msedgewebview2.exe")||!entries.ContainsKey("app/runtime/python.exe"))throw new InvalidDataException("Комплект неполон.");
        return entries;
    }
    internal static void CopyResource(string name,string path) {
        using(var s=Assembly.GetExecutingAssembly().GetManifestResourceStream(name)) { if(s==null)throw new InvalidDataException("Неполный установщик.");using(var f=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.None))s.CopyTo(f); }
    }
    internal static void CheckRegistration(string root) {
        using(var key=Registry.CurrentUser.OpenSubKey(RegPath,false)) {
            if(key!=null&&!String.Equals(Convert.ToString(key.GetValue("InstallLocation")),root,StringComparison.OrdinalIgnoreCase)) throw new IOException("Уже существует другая запись Кальки. Установка не изменяла её.");
        }
    }
    internal static bool Register(string root) {
        CheckRegistration(root); string link=Shortcut();bool created=false;
        try {
            string folder=Path.GetDirectoryName(link);Directory.CreateDirectory(folder);
            for(int i=0;i<1000&&!created;i++) {
                string name=i==0?"Калька.lnk":i==1?"CR20KB Калька.lnk":"CR20KB Калька ("+i+").lnk";
                created=WriteShortcut(Path.Combine(folder,name),root);
            }
        } catch(Exception ex) { if(!ShortcutFailure(ex))throw; }
        try {
            string desktop=Desktop();
            if(desktop!=null&&Directory.Exists(desktop))foreach(string name in new[]{"Калька.lnk","CR20KB Калька.lnk"}) {
                string candidate=Path.Combine(desktop,name);
                if(File.Exists(candidate))WriteShortcut(candidate,root);
            }
        } catch(Exception ex) { if(!ShortcutFailure(ex))throw; }
        using(var key=Registry.CurrentUser.CreateSubKey(RegPath)) {
            key.SetValue("DisplayName","CR20KB Калька");key.SetValue("DisplayVersion",Version);key.SetValue("Publisher","CR20KB");
            key.SetValue("ApplicationId",ApplicationId);
            key.SetValue("OwnershipMarker",OwnershipMarker);
            key.SetValue("InstallLocation",root);key.SetValue("DisplayIcon","\""+Path.Combine(root,LauncherName)+"\",0");
            key.SetValue("UninstallString","\""+Path.Combine(root,UninstallerName)+"\"");key.SetValue("NoModify",1,RegistryValueKind.DWord);key.SetValue("NoRepair",1,RegistryValueKind.DWord);
        }
        SHChangeNotify(0x00002000,0x0005,Path.Combine(root,LauncherName),null);
        return created;
    }
    internal static void Unregister(string root) {
        var links=new List<string>();string folder=Path.GetDirectoryName(Shortcut());
        for(int i=0;i<1000;i++)links.Add(Path.Combine(folder,i==0?"Калька.lnk":i==1?"CR20KB Калька.lnk":"CR20KB Калька ("+i+").lnk"));
        try { string desktop=Desktop();if(desktop!=null)foreach(string name in new[]{"Калька.lnk","CR20KB Калька.lnk"})links.Add(Path.Combine(desktop,name)); }
        catch(Exception ex) { if(!ShortcutFailure(ex))throw; }
        foreach(string link in links)try { if(File.Exists(link)&&String.Equals(ShortcutTarget(link),Path.Combine(root,LauncherName),StringComparison.OrdinalIgnoreCase)){File.Delete(link);SHChangeNotify(0x00000004,0x0005,link,null);} }
            catch(Exception ex) { if(!ShortcutFailure(ex))throw; }
        using(var key=Registry.CurrentUser.OpenSubKey(RegPath,false)) {
            if(key==null)return;
            if(!String.Equals(Convert.ToString(key.GetValue("InstallLocation")),root,StringComparison.OrdinalIgnoreCase))return;
        }
        Registry.CurrentUser.DeleteSubKey(RegPath,false);
    }
    internal static bool DataOnlyTree(string root) {
        try {
            CheckNoReparse(Local(),root);
            if(Directory.GetFiles(root).Length!=0)return false;
            foreach(string dir in Directory.GetDirectories(root)) {
                CheckNoReparse(root,dir);
                if(!String.Equals(Path.GetFileName(dir),"KalkaData",StringComparison.OrdinalIgnoreCase))return false;
            }
            return true;
        } catch(IOException) { return false; } catch(UnauthorizedAccessException) { return false; }
    }
    internal static bool RegisteredInstallation(string root,out string version) {
        version=null;
        using(var key=Registry.CurrentUser.OpenSubKey(RegPath,false)) {
            if(key==null||!String.Equals(Convert.ToString(key.GetValue("InstallLocation")),root,StringComparison.OrdinalIgnoreCase))return false;
            string id=Convert.ToString(key.GetValue("ApplicationId"));
            string publisher=Convert.ToString(key.GetValue("Publisher"));
            if(!String.IsNullOrEmpty(id)&&!String.Equals(id,ApplicationId,StringComparison.Ordinal))return false;
            // Earlier installers did not write ApplicationId. Their dedicated
            // uninstall key, exact installation path and publisher identify them
            // even if the display name has changed between releases.
            bool legacy=String.Equals(publisher,"CR20KB",StringComparison.OrdinalIgnoreCase);
            if(!String.Equals(id,ApplicationId,StringComparison.Ordinal)&&!legacy)return false;
            version=Convert.ToString(key.GetValue("DisplayVersion"));return true;
        }
    }
    internal static bool KnownInstallationFile(string root) {
        foreach(var candidate in new[]{new[]{LauncherName,"launcher.hash","Kalka.application"},new[]{UninstallerName,"uninstaller.hash","Kalka.uninstaller"}}) {
            string file=Path.Combine(root,candidate[0]);
            try {
                CheckNoReparse(root,file);if(!File.Exists(file))continue;string digest=DigestFile(file);
                using(var current=Assembly.GetExecutingAssembly().GetManifestResourceStream(candidate[2]))
                    if(current!=null&&String.Equals(digest,Digest(current),StringComparison.OrdinalIgnoreCase))return true;
                foreach(string prefix in new[]{"Kalka.previous","Kalka.previous2","Kalka.previous3"})
                    using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream(prefix+"."+candidate[1])) {
                        if(stream==null)continue;using(var reader=new StreamReader(stream,Encoding.ASCII))
                            if(String.Equals(digest,reader.ReadToEnd().Trim(),StringComparison.OrdinalIgnoreCase))return true;
                    }
            } catch(IOException) { } catch(UnauthorizedAccessException) { }
        }
        return false;
    }
    // Old installed payloads had no ownership marker. Match multiple specific
    // application files against manifests extracted from pinned old Setups.
    internal static bool LegacyPayload(string root) {
        int matches=0;
        var names=new[]{"app/program/kalka_core.py","app/program/kalka_export.py","app/program/kalka_server.py","app/program/web/app.js","app/program/web/index.html"};
        var manifests=new List<Dictionary<string,Entry>>();
        foreach(string prefix in new[]{"Kalka.legacy1","Kalka.legacy2","Kalka.previous","Kalka.previous2","Kalka.previous3","Kalka.bundle"}) {
            using(var resource=Assembly.GetExecutingAssembly().GetManifestResourceStream(prefix+".manifest")) {
                if(resource!=null)manifests.Add(Manifest(prefix+".manifest"));
            }
        }
        foreach(string name in names) {
            string file=SafePath(root,name);
            try {
                CheckNoReparse(root,file);if(!File.Exists(file))continue;
                string digest=DigestFile(file);
                foreach(var manifest in manifests) { Entry entry;if(manifest.TryGetValue(name,out entry)&&String.Equals(entry.Hash,digest,StringComparison.OrdinalIgnoreCase)){matches++;break;} }
            } catch(IOException) {} catch(UnauthorizedAccessException) {}
        }
        bool launcher=File.Exists(Path.Combine(root,LauncherName))||File.Exists(Path.Combine(root,"CR20KB-Kalka.exe"));
        bool shortcut=false;
        var links=new List<string>();string folder=Path.GetDirectoryName(Shortcut());
        foreach(string name in new[]{"Калька.lnk","CR20KB Калька.lnk"}) {
            links.Add(Path.Combine(folder,name));string desktop=Desktop();if(desktop!=null)links.Add(Path.Combine(desktop,name));
        }
        foreach(string link in links)try {
            if(!File.Exists(link))continue;string target=ShortcutTarget(link);
            if(!String.IsNullOrWhiteSpace(target)&&Path.IsPathRooted(target)) {
                string full=Path.GetFullPath(target);
                if(String.Equals(full,Path.Combine(root,LauncherName),StringComparison.OrdinalIgnoreCase)||String.Equals(full,Path.Combine(root,"CR20KB-Kalka.exe"),StringComparison.OrdinalIgnoreCase)){shortcut=true;break;}
            }
        } catch(Exception ex) { if(!ShortcutFailure(ex))throw; }
        return launcher && (matches>=3 || (matches>=2 && shortcut));
    }
    internal static string InstallationKind(string root,out string version) {
        version=null;
        using(var key=Registry.CurrentUser.OpenSubKey(RegPath,false)) {
            if(key!=null) {
                string id=Convert.ToString(key.GetValue("ApplicationId"));
                if(!String.IsNullOrEmpty(id)&&!String.Equals(id,ApplicationId,StringComparison.Ordinal))return "UNKNOWN";
                if(String.Equals(Convert.ToString(key.GetValue("InstallLocation")),root,StringComparison.OrdinalIgnoreCase) &&
                   String.Equals(id,ApplicationId,StringComparison.Ordinal) &&
                   String.Equals(Convert.ToString(key.GetValue("OwnershipMarker")),OwnershipMarker,StringComparison.Ordinal)) {
                    version=Convert.ToString(key.GetValue("DisplayVersion"));return "CURRENT";
                }
            }
        }
        if(RegisteredInstallation(root,out version)||KnownInstallationFile(root)||LegacyPayload(root))return "LEGACY CR20KB KALKA INSTALL";
        return "UNKNOWN";
    }
    internal static int? CompareInstalledVersion(string previous) {
        System.Version a,b;
        if(!System.Version.TryParse(previous,out a)||!System.Version.TryParse(Version,out b))return null;
        var oldVersion=new System.Version(a.Major,a.Minor,Math.Max(a.Build,0),Math.Max(a.Revision,0));
        var newVersion=new System.Version(b.Major,b.Minor,Math.Max(b.Build,0),Math.Max(b.Revision,0));
        return oldVersion.CompareTo(newVersion);
    }
    internal static List<string> UnmanagedEntries(string root,Dictionary<string,Entry> entries) {
        var result=new List<string>();var pending=new Stack<string>();pending.Push(root);
        while(pending.Count>0) {
            string dir=pending.Pop();string[] children;
            try { children=Directory.GetFileSystemEntries(dir); }
            catch(IOException) { result.Add("Не прочитан каталог: "+dir.Substring(root.Length).TrimStart('\\'));continue; }
            catch(UnauthorizedAccessException) { result.Add("Нет доступа к каталогу: "+dir.Substring(root.Length).TrimStart('\\'));continue; }
            catch(System.Security.SecurityException) { result.Add("Нет доступа к каталогу: "+dir.Substring(root.Length).TrimStart('\\'));continue; }
            foreach(string path in children) {
                string relative=path.Substring(root.Length+1).Replace(Path.DirectorySeparatorChar,'/');
                try {
                    FileAttributes attributes=File.GetAttributes(path);
                    if((attributes&FileAttributes.ReparsePoint)!=0){result.Add(relative+" [ссылка, не раскрывалась]");continue;}
                    if((attributes&FileAttributes.Directory)!=0){pending.Push(path);continue;}
                    if(!entries.ContainsKey(relative)&&!relative.Equals(LauncherName,StringComparison.OrdinalIgnoreCase)&&!relative.Equals(UninstallerName,StringComparison.OrdinalIgnoreCase))result.Add(relative);
                } catch(IOException) { result.Add(relative+" [не прочитан]"); }
                  catch(UnauthorizedAccessException) { result.Add(relative+" [нет доступа]"); }
                  catch(System.Security.SecurityException) { result.Add(relative+" [нет доступа]"); }
            }
        }
        result.Sort(StringComparer.OrdinalIgnoreCase);return result;
    }
    internal static bool ExactTree(string root,Dictionary<string,Entry> entries,string launchHash,string uninstallHash) {
        try {
            CheckNoReparse(Local(),root);var allowedDirs=new HashSet<string>(StringComparer.OrdinalIgnoreCase){root};
            foreach(var e in entries.Values){string p=Path.GetDirectoryName(SafePath(root,e.Name));while(p.Length>=root.Length){allowedDirs.Add(p);if(p==root)break;p=Path.GetDirectoryName(p);}}
            var todo=new Stack<string>();todo.Push(root);int count=0;
            while(todo.Count>0){string d=todo.Pop();CheckNoReparse(root,d);foreach(string sub in Directory.GetDirectories(d)){CheckNoReparse(root,sub);if(!allowedDirs.Contains(sub))return false;todo.Push(sub);}
                foreach(string file in Directory.GetFiles(d)){CheckNoReparse(root,file);string rel=file.Substring(root.Length+1).Replace(Path.DirectorySeparatorChar,'/');Entry e;
                    if(entries.TryGetValue(rel,out e)){if(new FileInfo(file).Length!=e.Size||DigestFile(file)!=e.Hash)return false;}
                    else if(rel==LauncherName){if(DigestFile(file)!=launchHash)return false;}
                    else if(rel==UninstallerName){if(DigestFile(file)!=uninstallHash)return false;}
                    else return false;count++;}}
            return count==entries.Count+2;
        }catch(IOException){return false;}catch(UnauthorizedAccessException){return false;}
    }
    internal static int DeleteOwned(string root,Dictionary<string,Entry> entries,string launchHash,string uninstallHash) {
        int kept=0;var dirs=new HashSet<string>(StringComparer.OrdinalIgnoreCase){root};
        foreach(var e in entries.Values){string file=SafePath(root,e.Name);string d=Path.GetDirectoryName(file);while(d.Length>=root.Length){dirs.Add(d);if(d==root)break;d=Path.GetDirectoryName(d);}
            try{CheckNoReparse(root,file);if(file.EndsWith(".kalka",StringComparison.OrdinalIgnoreCase)){kept++;continue;}if(File.Exists(file)){if(new FileInfo(file).Length==e.Size&&DigestFile(file)==e.Hash)File.Delete(file);else kept++;}}
            catch(IOException){kept++;}catch(UnauthorizedAccessException){kept++;}}
        foreach(var item in new[]{new[]{LauncherName,launchHash},new[]{UninstallerName,uninstallHash}}){string file=Path.Combine(root,item[0]);
            try{CheckNoReparse(root,file);if(File.Exists(file)){if(DigestFile(file)==item[1])File.Delete(file);else kept++;}}catch(IOException){kept++;}catch(UnauthorizedAccessException){kept++;}}
        var ordered=new List<string>(dirs);ordered.Sort((a,b)=>b.Length.CompareTo(a.Length));
        foreach(string d in ordered){try{CheckNoReparse(root,d);if(Directory.Exists(d))Directory.Delete(d,false);}catch(IOException){}catch(UnauthorizedAccessException){}}
        if(Directory.Exists(root))kept++;
        return kept;
    }
}
