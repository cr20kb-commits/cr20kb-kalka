using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("CR20KB Калька Setup")]
[assembly: AssemblyProduct("CR20KB Калька")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

internal static class KalkaSetup {
    private static Label status;
    private static bool shortcutCreated;
    private static bool silentMode;
    private static string backupNotice;
    private static void Say(string message) { if(status!=null){status.Text=message;Application.DoEvents();} }
    private static string ResourceText(string name) { using(var s=Assembly.GetExecutingAssembly().GetManifestResourceStream(name)){if(s==null)return null;using(var r=new StreamReader(s,Encoding.ASCII))return r.ReadToEnd().Trim();} }
    private static void ShowTerms(Form parent) {
        using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("Kalka.runtime.terms"))
        using(var python=Assembly.GetExecutingAssembly().GetManifestResourceStream("Kalka.python.terms")) {
            if(stream==null||python==null)throw new InvalidDataException("Условия компонентов отсутствуют в установщике.");
            using(var reader=new StreamReader(stream,Encoding.UTF8))
            using(var pythonReader=new StreamReader(python,Encoding.UTF8))
            using(var dialog=new Form{Text="WebView2 и Python — условия компонентов",Width=860,Height=640,StartPosition=FormStartPosition.CenterParent}) {
                string content=reader.ReadToEnd()+"\n\n========== PYTHON WINDOWS BINARY LICENSE ==========\n\n"+pythonReader.ReadToEnd();
                var text=new TextBox{Dock=DockStyle.Fill,Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,WordWrap=true,Text=content.Replace("\r\n","\n").Replace("\n","\r\n")};
                dialog.Controls.Add(text);dialog.ShowDialog(parent);
            }
        }
    }
    [STAThread] private static int Main(string[] args) {
        bool silent=args.Length==2&&args[0]=="--silent"&&args[1]=="--accept-runtime-terms";
        silentMode=silent;
        if(args.Length>0&&!silent)return 1;
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        if(silent){try{Install();return 0;}catch(Exception ex){try{Console.Error.WriteLine(ex.Message);}catch{}return 1;}}
        int result=1;
        using(var form=new Form{Text="CR20KB Калька — установка 1.0.0",Width=720,Height=310,StartPosition=FormStartPosition.CenterScreen,FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false}){
            var text=new Label{Dock=DockStyle.Top,Height=90,Text="Калька будет установлена для текущего пользователя.\nИнтернет и права администратора не требуются.\nПользовательские проекты сохраняются.",Padding=new Padding(14)};
            status=new Label{Dock=DockStyle.Fill,Text="Папка: "+InstallSupport.Root(),Padding=new Padding(14)};
            var button=new Button{Dock=DockStyle.Bottom,Height=38,Text="Установить / обновить",Enabled=false};
            var consent=new CheckBox{Dock=DockStyle.Bottom,Height=34,Text="Я ознакомился и согласен с условиями компонентов WebView2 и Python",Padding=new Padding(14,0,0,0)};
            var show=new Button{Dock=DockStyle.Bottom,Height=32,Text="Прочитать условия компонентов WebView2 и Python (English)"};
            show.Click+=(s,e)=>{try{ShowTerms(form);}catch(Exception ex){MessageBox.Show(form,ex.Message,"CR20KB Калька",MessageBoxButtons.OK,MessageBoxIcon.Error);}};
            consent.CheckedChanged+=(s,e)=>button.Enabled=consent.Checked;
            button.Click+=(s,e)=>{button.Enabled=false;form.ControlBox=false;try{Install();result=0;string message=shortcutCreated?"Установка завершена. Запускайте «Калька» из меню Пуск.":"Установка завершена, но не удалось создать ярлык в меню Пуск. Запустите Kalka.exe из папки установки.";if(backupNotice!=null)message+="\n\nПредыдущие файлы сохранены: "+backupNotice+"\nРядом находится отчёт об обновлении.";MessageBox.Show(form,message,"CR20KB Калька",MessageBoxButtons.OK,shortcutCreated?MessageBoxIcon.Information:MessageBoxIcon.Warning);form.Close();}
                catch(Exception ex){form.ControlBox=true;button.Enabled=true;Say("Установка не завершена.");MessageBox.Show(form,ex.Message,"CR20KB Калька",MessageBoxButtons.OK,MessageBoxIcon.Error);}};
            form.Controls.Add(status);form.Controls.Add(consent);form.Controls.Add(show);form.Controls.Add(button);form.Controls.Add(text);Application.Run(form);
        }
        return result;
    }
    private static void Install() {
        using(var mutex=new Mutex(false,"Local\\CR20KB-Kalka-onefile-owner")){
            bool held=false;
            try {try{held=mutex.WaitOne(0);}catch(AbandonedMutexException){held=true;}if(!held)throw new IOException("Калька сейчас открыта. Закройте её и повторите установку.");
                string local=InstallSupport.Local(),root=InstallSupport.Root(),parent=Path.GetDirectoryName(root);
                InstallSupport.CheckNoReparse(local,parent);Directory.CreateDirectory(parent);InstallSupport.CheckNoReparse(local,parent);
                InstallSupport.CheckRegistration(root);
                var manifest=InstallSupport.Manifest();string launchHash=InstallSupport.ResourceHash("Kalka.application"),uninstallHash=InstallSupport.ResourceHash("Kalka.uninstaller");
                bool replacing=Directory.Exists(root),dataOnly=replacing&&InstallSupport.DataOnlyTree(root);string previousVersion=null;
                string installationKind=replacing&&!dataOnly?InstallSupport.InstallationKind(root,out previousVersion):"NEW OR DATA ONLY";
                bool approvedUnknown=false;
                if(installationKind=="UNKNOWN") {
                    if(silentMode||MessageBox.Show("Не удалось подтвердить принадлежность папки Кальке:\n"+root+"\n\nПродолжить установку, сохранив всю прежнюю папку в резервной копии рядом? Выберите «Нет», если не уверены.","CR20KB Калька — проверка папки",MessageBoxButtons.YesNo,MessageBoxIcon.Warning,MessageBoxDefaultButton.Button2)!=DialogResult.Yes)
                        throw new IOException("Принадлежность папки не подтверждена. Файлы сохранены; установка не выполнялась.");
                    approvedUnknown=true;
                }
                int? comparison=InstallSupport.CompareInstalledVersion(previousVersion);
                if(comparison.HasValue&&comparison.Value>0)throw new IOException("Установлена более новая версия Кальки ("+previousVersion+"). Используйте установщик этой или более новой версии.");
                if(File.Exists(root))throw new IOException("Путь установки занят файлом.");
                long required=64L*1024*1024;foreach(var e in manifest.Values)checked{required+=e.Size;}
                if(new DriveInfo(Path.GetPathRoot(root)).AvailableFreeSpace<required)throw new IOException("Недостаточно свободного места на диске для установки.");
                string staging=Path.Combine(parent,"Kalka.s-"+Guid.NewGuid().ToString("N").Substring(0,8));
                string backup=Path.Combine(parent,"Kalka.backup-"+Guid.NewGuid().ToString("N"));string report=backup+".txt";
                if(Directory.Exists(staging)||Directory.Exists(backup)||File.Exists(report))throw new IOException("Не удалось создать временную папку установки.");
                InstallSupport.CheckNoReparse(local,staging);Directory.CreateDirectory(staging);InstallSupport.CheckNoReparse(local,staging);
                bool movedOld=false,installed=false,movedData=false,hadData=false,reportCreated=false,committed=false;
                try{
                    Say("Установка и проверка компонентов… / Installing components…");
                    using(var input=Assembly.GetExecutingAssembly().GetManifestResourceStream("Kalka.bundle")){
                        if(input==null)throw new InvalidDataException("Комплект компонентов отсутствует.");
                        using(var zip=new ZipArchive(input,ZipArchiveMode.Read)){
                            var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);int count=0;
                            foreach(var item in zip.Entries){InstallSupport.Entry e;
                                if(!manifest.TryGetValue(item.FullName,out e)||!seen.Add(item.FullName)||item.Length!=e.Size)throw new InvalidDataException("Состав установщика повреждён.");
                                string file=InstallSupport.SafePath(staging,e.Name);Directory.CreateDirectory(Path.GetDirectoryName(file));InstallSupport.CheckNoReparse(staging,file);
                                using(var source=item.Open())using(var target=new FileStream(file,FileMode.CreateNew,FileAccess.Write,FileShare.None)){byte[] buffer=new byte[1024*1024];int n;long total=0;while((n=source.Read(buffer,0,buffer.Length))>0){total+=n;if(total>e.Size)throw new InvalidDataException("Превышен размер компонента: "+e.Name);target.Write(buffer,0,n);}if(total!=e.Size)throw new InvalidDataException("Неполный компонент: "+e.Name);}
                                if(new FileInfo(file).Length!=e.Size||InstallSupport.DigestFile(file)!=e.Hash)throw new InvalidDataException("Ошибка целостности: "+e.Name);
                                if(++count%10==0)Say("Установка компонентов: "+count+" / "+manifest.Count);
                            }
                            if(seen.Count!=manifest.Count)throw new InvalidDataException("Комплект компонентов неполон.");
                        }
                    }
                    InstallSupport.CopyResource("Kalka.application",Path.Combine(staging,InstallSupport.LauncherName));
                    InstallSupport.CopyResource("Kalka.uninstaller",Path.Combine(staging,InstallSupport.UninstallerName));
                    Say("Проверка установленного комплекта… / Verifying…");
                    if(!InstallSupport.ExactTree(staging,manifest,launchHash,uninstallHash))throw new InvalidDataException("Проверка компонентов установки не прошла.");
                    if(replacing){
                        InstallSupport.CheckNoReparse(local,root);
                        string data=Path.Combine(root,"KalkaData");
                        try { var attributes=File.GetAttributes(data);if((attributes&FileAttributes.Directory)!=0){InstallSupport.CheckNoReparse(root,data);hadData=true;} }
                        catch(FileNotFoundException) { } catch(DirectoryNotFoundException) { }
                        string ignored;string currentKind=InstallSupport.InstallationKind(root,out ignored);
                        if(dataOnly?!InstallSupport.DataOnlyTree(root):currentKind=="UNKNOWN"&&!approvedUnknown)throw new IOException("Не удалось подтвердить папку установки. Файлы сохранены.");
                        Directory.Move(root,backup);movedOld=true;
                    }
                    Directory.Move(staging,root);installed=true;
                    if(movedOld&&hadData) {
                        InstallSupport.CheckNoReparse(backup,Path.Combine(backup,"KalkaData"));
                        Directory.Move(Path.Combine(backup,"KalkaData"),Path.Combine(root,"KalkaData"));movedData=true;
                    }
                    if(movedOld) {
                        var unknown=InstallSupport.UnmanagedEntries(backup,manifest);
                        using(var stream=new FileStream(report,FileMode.CreateNew,FileAccess.Write,FileShare.None))
                        using(var writer=new StreamWriter(stream,new UTF8Encoding(false))) {
                            reportCreated=true;
                            writer.WriteLine("CR20KB Калька — отчёт установки/обновления");writer.WriteLine("Предыдущая версия: "+(String.IsNullOrWhiteSpace(previousVersion)?"не определена":previousVersion));
                            writer.WriteLine("Тип предыдущей установки: "+installationKind);
                            writer.WriteLine("Установленная версия: "+InstallSupport.Version);writer.WriteLine("Предыдущие файлы сохранены: "+backup);
                            writer.WriteLine("Папка KalkaData перенесена в установленную программу, если существовала.");
                            writer.WriteLine("Неизвестные или отсутствующие в новом манифесте файлы и ссылки сохранены в резервной папке:");
                            if(unknown.Count==0)writer.WriteLine("(не обнаружены)");
                            foreach(string item in unknown)writer.WriteLine(item.Replace("\r","\\r").Replace("\n","\\n"));
                        }
                    }
                    shortcutCreated=InstallSupport.Register(root);
                    committed=true;if(movedOld){backupNotice=backup;try{Console.WriteLine("Предыдущие файлы: "+backup+"; отчёт: "+report);}catch{}}
                    Say("Готово. / Ready.");
                } catch(Exception original) {
                    if(!committed&&movedOld) {
                        try {
                            if(movedData){Directory.Move(Path.Combine(root,"KalkaData"),Path.Combine(backup,"KalkaData"));movedData=false;}
                            if(installed){Directory.Move(root,staging);installed=false;}
                            if(Directory.Exists(root)||File.Exists(root))throw new IOException("Путь установки неожиданно занят.");
                            Directory.Move(backup,root);
                            movedOld=false;
                            if(reportCreated&&File.Exists(report))File.Delete(report);
                        } catch(Exception rollback) { throw new IOException("Не удалось полностью восстановить предыдущую установку. Файлы сохранены; проверьте: "+backup+" и "+root+". Причина: "+rollback.Message,original); }
                    }
                    throw;
                } finally {
                    if(!installed&&!movedOld&&Directory.Exists(staging))InstallSupport.DeleteOwned(staging,manifest,launchHash,uninstallHash);
                }
            } finally {if(held)mutex.ReleaseMutex();}
        }
    }
}
