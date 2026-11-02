using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;

internal static class ExtractSetupBundle {
    private static void Main(string[] args) {
        if(args.Length!=2)throw new ArgumentException("Expected setup and empty output directory.");
        string dir=Path.GetFullPath(args[1]);
        var assembly=Assembly.LoadFile(Path.GetFullPath(args[0]));
        Directory.CreateDirectory(dir);
        foreach(var pair in new[]{new[]{"Kalka.bundle","bundle.zip"},new[]{"Kalka.bundle.manifest","manifest.txt"},
                                  new[]{"Kalka.application","application.exe"},new[]{"Kalka.uninstaller","old-uninstaller.exe"},
                                  new[]{"Kalka.runtime.terms","runtime.terms"},new[]{"Kalka.python.terms","python.terms"}}) {
            using(var source=assembly.GetManifestResourceStream(pair[0])) {
                if(source==null)throw new InvalidDataException("Missing setup resource: "+pair[0]);
                string path=Path.Combine(dir,pair[1]);
                if(File.Exists(path)) {
                    using(var hash=SHA256.Create())using(var existing=File.OpenRead(path)) {
                        if(!String.Equals(BitConverter.ToString(hash.ComputeHash(source)),BitConverter.ToString(hash.ComputeHash(existing)),StringComparison.Ordinal))
                            throw new InvalidDataException("Existing extracted resource differs: "+pair[0]);
                    }
                } else using(var target=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.None))source.CopyTo(target);
            }
        }
    }
}
