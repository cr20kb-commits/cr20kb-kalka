using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
internal static class ExtractResources {
    private static void Main(string[] args) {
        if(args.Length!=3||args[2]!="setup")throw new ArgumentException("Expected an installer and output directory.");
        var asm=Assembly.LoadFile(Path.GetFullPath(args[0]));string dir=Path.GetFullPath(args[1]);
        var items=new[]{new[]{"Kalka.bundle.manifest","previous-manifest.txt"},new[]{"Kalka.application","previous-application.exe"},new[]{"Kalka.uninstaller","previous-uninstaller.exe"}};
        foreach(var pair in items){
            using(var s=asm.GetManifestResourceStream(pair[0])){if(s==null)throw new InvalidDataException("Missing resource: "+pair[0]);
                string target=Path.Combine(dir,pair[1]);
                if(File.Exists(target)){using(var h=SHA256.Create())using(var f=File.OpenRead(target)){string a=BitConverter.ToString(h.ComputeHash(s)),b=BitConverter.ToString(h.ComputeHash(f));if(a!=b)throw new InvalidDataException("Existing resource differs: "+pair[0]);}continue;}
                using(var f=new FileStream(target,FileMode.CreateNew,FileAccess.Write,FileShare.None))s.CopyTo(f);}
        }
    }
}
