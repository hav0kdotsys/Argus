using System;
using System.Threading;
using System.Windows.Forms;

namespace MiraPet
{
    internal static class Program
    {
        [STAThread]
        private static void Main(string[] args)
        {
            // One Mira per desktop session.
            using (Mutex one = new Mutex(true, @"Local\MiraPet", out bool first))
            {
                if (!first) return;
                Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new Pet());
            }
        }
    }
}
