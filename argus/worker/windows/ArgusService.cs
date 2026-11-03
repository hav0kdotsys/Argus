// ARGUS's worker on Windows: the ARGUS service (LocalSystem, automatic, restarts on failure).
//
// It keeps what runs on this PC matching %ProgramData%\ARGUS\argus.yaml, every 30 s and whenever someone logs on or
// unlocks. A service lives in session 0 and can't draw on the desktop, so MIRA's body and her companion are started in
// HavoK's own desktop session, as HavoK (WTSQueryUserToken + CreateProcessAsUser): they see and touch her desktop like
// any app she runs, and nothing they do runs as SYSTEM. body.enabled false brings the old body (the MIRA-Pet task)
// back, which is the whole rollback.
//
// C# 5 for .NET Framework 4.8's csc, like the body. Built by build.ps1, installed by install.ps1 (admin).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Management;
using System.Runtime.InteropServices;
using System.ServiceProcess;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

namespace Argus
{
    internal static class Program
    {
        private static int Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "--check")
            {
                // Reads the config the way the service will, and says what it asks for. Needs no admin.
                try { Console.WriteLine(Config.Load(args.Length > 1 ? args[1] : Config.DefaultPath).Describe()); return 0; }
                catch (Exception error) { Console.WriteLine("config: " + error.Message); return 1; }
            }
            ServiceBase.Run(new ArgusService());
            return 0;
        }
    }

    // argus.yaml's plain-YAML subset (as argus_worker.py reads it): two levels of "key: value", '#' comments.
    internal sealed class Config
    {
        internal static string DefaultPath { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "ARGUS", "argus.yaml"); } }

        internal string Host = "", User = "";
        internal bool BodyOn, CompanionOn = true;
        internal string BodyPath, CompanionCommand;

        internal static Config Load(string path)
        {
            Dictionary<string, string> values = new Dictionary<string, string>(StringComparer.Ordinal);
            string section = null;
            int number = 0;
            foreach (string raw in File.ReadAllLines(path, Encoding.UTF8))
            {
                number++;
                string line = raw.TrimStart().StartsWith("#", StringComparison.Ordinal) ? "" : Regex.Replace(raw, @"\s+#.*$", "").TrimEnd();
                if (line.Trim().Length == 0) continue;
                bool nested = char.IsWhiteSpace(line[0]);
                Match pair = Regex.Match(line.Trim(), @"^([A-Za-z_][\w.-]*)\s*:(?:\s+(.*))?$");
                if (line.Trim().StartsWith("-", StringComparison.Ordinal)) continue;       // lists (devices) are the worker's
                if (!pair.Success) throw new FormatException("line " + number + ": expected 'key: value'");
                string key = pair.Groups[1].Value, value = pair.Groups[2].Success ? pair.Groups[2].Value.Trim() : "";
                if (!nested) { section = value.Length == 0 ? key : null; if (value.Length > 0) values[key] = value; continue; }
                if (section == null) throw new FormatException("line " + number + ": indented under a setting that has a value");
                values[section + "." + key] = value;
            }
            Config config = new Config();
            config.Host = Get(values, "host") ?? "";
            config.User = Get(values, "user") ?? "";
            config.BodyOn = Flag(values, "body.enabled", false);
            config.CompanionOn = Flag(values, "companion.enabled", true);
            config.BodyPath = Get(values, "body.path");
            config.CompanionCommand = Get(values, "companion.command");
            if (config.BodyOn && string.IsNullOrEmpty(config.BodyPath)) throw new FormatException("body.enabled is true but body.path isn't set");
            if (config.CompanionOn && string.IsNullOrEmpty(config.CompanionCommand)) throw new FormatException("companion.enabled is true but companion.command isn't set");
            return config;
        }

        private static string Get(Dictionary<string, string> values, string key)
        {
            string value;
            if (!values.TryGetValue(key, out value) || value.Length == 0) return null;
            if (value.Length >= 2 && (value[0] == '"' || value[0] == '\'') && value[value.Length - 1] == value[0]) value = value.Substring(1, value.Length - 2);
            return value;
        }

        private static bool Flag(Dictionary<string, string> values, string key, bool otherwise)
        {
            string value = Get(values, key);
            if (value == null) return otherwise;
            switch (value.ToLowerInvariant())
            {
                case "true": case "yes": case "on": return true;
                case "false": case "no": case "off": return false;
            }
            throw new FormatException(key + ": should be true or false");
        }

        internal string Describe()
        {
            return (Host.Length > 0 ? Host : "this PC") + ": body " + (BodyOn ? "on (" + BodyPath + ")" : "off (MIRA-Pet)") +
                   ", companion " + (CompanionOn ? "on (" + CompanionCommand + ")" : "off");
        }

        internal bool Same(Config other)
        {
            return other != null && other.BodyOn == BodyOn && other.CompanionOn == CompanionOn && other.BodyPath == BodyPath && other.CompanionCommand == CompanionCommand;
        }
    }

    internal sealed class ArgusService : ServiceBase
    {
        private const string OldBodyTask = "MIRA-Pet";
        private readonly object gate = new object();
        private Timer timer;
        private Config seen;
        private string lastProblem;
        private bool? oldTaskOn;

        internal ArgusService()
        {
            ServiceName = "ARGUS";
            CanHandleSessionChangeEvent = true;
            CanShutdown = true;
        }

        protected override void OnStart(string[] args)
        {
            Log("ARGUS started");
            timer = new Timer(delegate { Tick(); }, null, 3000, 30000);
        }

        protected override void OnStop()
        {
            if (timer != null) timer.Dispose();
            Log("ARGUS stopped");
        }

        protected override void OnSessionChange(SessionChangeDescription change)
        {
            if (change.Reason == SessionChangeReason.SessionLogon || change.Reason == SessionChangeReason.SessionUnlock || change.Reason == SessionChangeReason.ConsoleConnect)
                ThreadPool.QueueUserWorkItem(delegate { Thread.Sleep(4000); Tick(); });
        }

        private void Tick()
        {
            if (!Monitor.TryEnter(gate)) return;
            try { Keep(); }
            catch (Exception error) { Problem("tick: " + error.Message); }
            finally { Monitor.Exit(gate); }
        }

        private void Keep()
        {
            Config config;
            try { config = Config.Load(Config.DefaultPath); }
            catch (Exception error) { Problem("config: " + error.Message + "; changing nothing until it's fixed"); return; }
            if (!config.Same(seen)) { Log(config.Describe()); seen = config; }
            uint session = Native.WTSGetActiveConsoleSessionId();
            if (session == 0xFFFFFFFF) return;
            IntPtr token;
            if (!Native.WTSQueryUserToken(session, out token)) return;      // nobody logged on at the console
            try
            {
                if (config.BodyOn)
                {
                    OldTask(false);
                    Kill(session, "MiraPet");
                    if (Processes(session, "Mira").Count == 0)
                    {
                        if (File.Exists(config.BodyPath)) Launch(token, "\"" + config.BodyPath + "\"", Path.GetDirectoryName(config.BodyPath), "her body");
                        else Problem("her body isn't at " + config.BodyPath);
                    }
                }
                else
                {
                    Kill(session, "Mira");
                    OldTask(true);
                    if (Processes(session, "MiraPet").Count == 0) Run("schtasks.exe", "/Run /TN \"" + OldBodyTask + "\"");
                }
                List<int> companions = Companions(session);
                if (config.CompanionOn && companions.Count == 0) Launch(token, config.CompanionCommand, Profile(token), "her companion");
                if (!config.CompanionOn) foreach (int id in companions) KillId(id);
            }
            finally { Native.CloseHandle(token); }
        }

        // The old body's logon task: off while her body runs, so it doesn't come back at the next logon; on for the rollback.
        private void OldTask(bool on)
        {
            if (oldTaskOn == on) return;
            Run("schtasks.exe", "/Change /TN \"" + OldBodyTask + "\" " + (on ? "/ENABLE" : "/DISABLE"));
            oldTaskOn = on;
        }

        private static List<Process> Processes(uint session, string name)
        {
            List<Process> found = new List<Process>();
            foreach (Process process in Process.GetProcessesByName(name))
            {
                if (process.SessionId == session) found.Add(process);
                else process.Dispose();
            }
            return found;
        }

        private void Kill(uint session, string name)
        {
            foreach (Process process in Processes(session, name))
            {
                using (process)
                {
                    try { process.Kill(); Log("stopped " + name + " (" + process.Id + ")"); }
                    catch (Exception error) { Problem("couldn't stop " + name + ": " + error.Message); }
                }
            }
        }

        private void KillId(int id)
        {
            try { using (Process process = Process.GetProcessById(id)) { process.Kill(); Log("stopped her companion (" + id + ")"); } }
            catch (Exception error) { Problem("couldn't stop her companion: " + error.Message); }
        }

        // Her companion running "companion run" in that session: ARGUS's Python process, or the conhost and PowerShell that
        // start it. Python only appears seconds after the launch, and a second pass in that gap (a timer tick and a logon
        // landing together after boot) would start her companion twice.
        private static List<int> Companions(uint session)
        {
            List<int> found = new List<int>();
            using (ManagementObjectSearcher search = new ManagementObjectSearcher("SELECT ProcessId, SessionId, CommandLine FROM Win32_Process WHERE Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'powershell.exe' OR Name = 'pwsh.exe' OR Name = 'conhost.exe'"))
            using (ManagementObjectCollection all = search.Get())
            {
                foreach (ManagementBaseObject each in all)
                {
                    using (each)
                    {
                        string line = each["CommandLine"] as string;
                        if (line != null && line.IndexOf("companion run", StringComparison.OrdinalIgnoreCase) >= 0 && Convert.ToUInt32(each["SessionId"]) == session)
                            found.Add(Convert.ToInt32(each["ProcessId"]));
                    }
                }
            }
            return found;
        }

        private static string Profile(IntPtr token)
        {
            StringBuilder path = new StringBuilder(260);
            int size = path.Capacity;
            return Native.GetUserProfileDirectory(token, path, ref size) ? path.ToString() : null;
        }

        // Starts a command in HavoK's session, as HavoK, with her own environment, hidden unless it draws its own windows.
        private void Launch(IntPtr token, string command, string folder, string what)
        {
            IntPtr primary = IntPtr.Zero, environment = IntPtr.Zero;
            try
            {
                if (!Native.DuplicateTokenEx(token, 0x02000000, IntPtr.Zero, 2, 1, out primary)) { Problem("couldn't start " + what + ": DuplicateTokenEx " + Marshal.GetLastWin32Error()); return; }
                if (!Native.CreateEnvironmentBlock(out environment, primary, false)) environment = IntPtr.Zero;
                Native.StartupInfo start = new Native.StartupInfo();
                start.cb = Marshal.SizeOf(typeof(Native.StartupInfo));
                start.lpDesktop = "winsta0\\default";
                Native.ProcessInformation started;
                if (!Native.CreateProcessAsUser(primary, null, new StringBuilder(command), IntPtr.Zero, IntPtr.Zero, false, 0x00000400, environment, folder, ref start, out started))
                {
                    Problem("couldn't start " + what + ": CreateProcessAsUser " + Marshal.GetLastWin32Error());
                    return;
                }
                Native.CloseHandle(started.hThread);
                Native.CloseHandle(started.hProcess);
                Log("started " + what + " (" + started.dwProcessId + ")");
                lastProblem = null;
            }
            finally
            {
                if (environment != IntPtr.Zero) Native.DestroyEnvironmentBlock(environment);
                if (primary != IntPtr.Zero) Native.CloseHandle(primary);
            }
        }

        private void Run(string file, string arguments)
        {
            try
            {
                using (Process process = Process.Start(new ProcessStartInfo(file, arguments) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true }))
                {
                    process.WaitForExit(30000);
                    if (process.ExitCode != 0) Problem(file + " " + arguments + ": " + process.StandardError.ReadToEnd().Trim());
                }
            }
            catch (Exception error) { Problem(file + ": " + error.Message); }
        }

        // A problem is logged once, not every 30 s, until something else happens.
        private void Problem(string text)
        {
            if (text == lastProblem) return;
            lastProblem = text;
            Log(text);
        }

        private static void Log(string text)
        {
            try
            {
                string folder = Path.GetDirectoryName(Config.DefaultPath);
                Directory.CreateDirectory(folder);
                string path = Path.Combine(folder, "service.log");
                if (File.Exists(path) && new FileInfo(path).Length > 1024 * 1024) File.Delete(path);
                File.AppendAllText(path, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + text + Environment.NewLine);
            }
            catch (Exception) { }
        }
    }

    internal static class Native
    {
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        internal struct StartupInfo
        {
            public int cb;
            public string lpReserved, lpDesktop, lpTitle;
            public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
            public short wShowWindow, cbReserved2;
            public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
        }

        [StructLayout(LayoutKind.Sequential)]
        internal struct ProcessInformation
        {
            public IntPtr hProcess, hThread;
            public int dwProcessId, dwThreadId;
        }

        [DllImport("kernel32.dll")] internal static extern uint WTSGetActiveConsoleSessionId();
        [DllImport("wtsapi32.dll", SetLastError = true)] internal static extern bool WTSQueryUserToken(uint session, out IntPtr token);
        [DllImport("advapi32.dll", SetLastError = true)] internal static extern bool DuplicateTokenEx(IntPtr token, uint access, IntPtr attributes, int impersonation, int type, out IntPtr duplicate);
        [DllImport("userenv.dll", SetLastError = true)] internal static extern bool CreateEnvironmentBlock(out IntPtr environment, IntPtr token, bool inherit);
        [DllImport("userenv.dll", SetLastError = true)] internal static extern bool DestroyEnvironmentBlock(IntPtr environment);
        [DllImport("userenv.dll", SetLastError = true, CharSet = CharSet.Unicode)] internal static extern bool GetUserProfileDirectory(IntPtr token, StringBuilder path, ref int size);
        [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        internal static extern bool CreateProcessAsUser(IntPtr token, string application, StringBuilder command, IntPtr processAttributes, IntPtr threadAttributes, bool inherit, uint flags, IntPtr environment, string folder, ref StartupInfo start, out ProcessInformation started);
        [DllImport("kernel32.dll", SetLastError = true)] internal static extern bool CloseHandle(IntPtr handle);
    }
}
