using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;

internal static class ExtractReleaseResources {
    private static void Main(string[] args) {
        if(args.Length!=2) throw new ArgumentException("Expected setup EXE and new output directory.");
        string dir=Path.GetFullPath(args[1]);
        Directory.CreateDirectory(dir);
        var assembly=Assembly.LoadFile(Path.GetFullPath(args[0]));
        foreach(var pair in new[]{new[]{"Kalka.bundle","bundle.zip"},new[]{"Kalka.application","Kalka.exe"}}) {
            using(var input=assembly.GetManifestResourceStream(pair[0])) {
                if(input==null) throw new InvalidDataException("Missing resource: "+pair[0]);
                string target=Path.Combine(dir,pair[1]);
                if(File.Exists(target)) {
                    using(var hash=SHA256.Create()) using(var existing=File.OpenRead(target)) {
                        string sourceHash=BitConverter.ToString(hash.ComputeHash(input));
                        string existingHash=BitConverter.ToString(hash.ComputeHash(existing));
                        if(sourceHash!=existingHash) throw new IOException("Existing resource differs: "+target);
                    }
                } else using(var output=new FileStream(target,FileMode.CreateNew)) input.CopyTo(output);
            }
        }
    }
}
