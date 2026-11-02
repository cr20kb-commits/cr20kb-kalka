using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("CR20KB Калька — удаление")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

internal static class KalkaUninstaller {
    // The worker cannot delete its own mapped EXE. A system command retries
    // deletion of this one randomly named temporary copy after the worker exits.
    private static void RemoveWorkerOnExit() {
        string self=Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
        string temp=Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar);
        if(!String.Equals(Path.GetDirectoryName(self),temp,StringComparison.OrdinalIgnoreCase) ||
           !Regex.IsMatch(Path.GetFileName(self),@"^kalka-uninstall-[0-9a-f]{32}\.exe$",RegexOptions.IgnoreCase)) return;
        var start=new ProcessStartInfo(Path.Combine(Environment.SystemDirectory,"cmd.exe"),
            "/d /v:off /c \"for /L %i in (1,1,10000) do @if exist \"%KALKA_CLEANUP_HELPER%\" (del /f /q \"%KALKA_CLEANUP_HELPER%\" 2>nul) else (exit /b 0)\"") { UseShellExecute=false,CreateNoWindow=true };
        start.EnvironmentVariables["KALKA_CLEANUP_HELPER"]=self;
        using(var p=Process.Start(start)) if(p==null) throw new IOException("Не удалось запустить очистку временного файла удаления.");
    }
    [STAThread] private static int Main(string[] args) {
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        bool worker=args.Length>=2&&args[0]=="--perform",silent=(worker?args.Length==3&&args[2]=="--silent":args.Length==1&&args[0]=="--silent");
        try {
            string root=InstallSupport.Root();InstallSupport.CheckNoReparse(InstallSupport.Local(),root);
            if(!worker){
                string self=Assembly.GetExecutingAssembly().Location;
                if(!String.Equals(Path.GetFullPath(self),Path.Combine(root,InstallSupport.UninstallerName),StringComparison.OrdinalIgnoreCase))throw new IOException("Удаление доступно только из установленной папки.");
                using(var mutex=new Mutex(false,"Local\\CR20KB-Kalka-onefile-owner")){bool held=false;try{try{held=mutex.WaitOne(0);}catch(AbandonedMutexException){held=true;}if(!held)throw new IOException("Калька открыта. Закройте её перед удалением.");}finally{if(held)mutex.ReleaseMutex();}}
                if(!silent&&MessageBox.Show("Удалить установленную Кальку? Проекты и настройки останутся.","CR20KB Калька",MessageBoxButtons.YesNo,MessageBoxIcon.Question)!=DialogResult.Yes)return 0;
                string temp=Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar);InstallSupport.CheckNoReparse(temp,temp);
                string helper=Path.Combine(temp,"kalka-uninstall-"+Guid.NewGuid().ToString("N")+".exe");File.Copy(self,helper,false);
                string options="--perform "+Process.GetCurrentProcess().Id+(silent?" --silent":"");
                using(var started=Process.Start(new ProcessStartInfo(helper,options){UseShellExecute=false,CreateNoWindow=silent}))if(started==null)throw new IOException("Не удалось запустить удаление.");
                return 0;
            }
            int parent;if(!Int32.TryParse(args[1],out parent)||parent<=0)throw new IOException("Недопустимый процесс удаления.");
            try{using(var p=Process.GetProcessById(parent)){if(!p.WaitForExit(15000))throw new IOException("Не удалось закрыть программу удаления.");}}catch(ArgumentException){}
            using(var mutex=new Mutex(false,"Local\\CR20KB-Kalka-onefile-owner")){
                bool held=false;try{try{held=mutex.WaitOne(0);}catch(AbandonedMutexException){held=true;}if(!held)throw new IOException("Калька открыта. Закройте её перед удалением.");
                    var manifest=InstallSupport.Manifest();string launchHash;
                    using(var s=Assembly.GetExecutingAssembly().GetManifestResourceStream("Kalka.launcher.hash"))using(var r=new StreamReader(s,Encoding.ASCII)){launchHash=r.ReadToEnd().Trim();}
                    string uninstallHash=InstallSupport.DigestFile(Assembly.GetExecutingAssembly().Location);
                    int kept=Directory.Exists(root)?InstallSupport.DeleteOwned(root,manifest,launchHash,uninstallHash):0;
                    InstallSupport.Unregister(root);
                    if(!silent)MessageBox.Show(kept==0?"Калька удалена. Проекты и настройки сохранены.":"Калька удалена. Изменённые или посторонние файлы оставлены в папке установки; проекты и настройки сохранены.","CR20KB Калька",MessageBoxButtons.OK,MessageBoxIcon.Information);
                    return 0;
                }finally{if(held)mutex.ReleaseMutex();}
            }
        }catch(Exception ex){if(!silent)MessageBox.Show(ex.Message,"CR20KB Калька",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
        finally { if(worker) { try { RemoveWorkerOnExit(); } catch(Exception ex) { try { Console.Error.WriteLine(ex.Message); } catch {} } } }
    }
}
