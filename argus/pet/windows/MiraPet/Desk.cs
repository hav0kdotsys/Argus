using System;
using System.Collections.Generic;
using System.Drawing;
using System.Windows.Forms;

namespace MiraPet
{
    // The desktop as ledges: every visible top-level window's top edge (top of z-order first) and each screen's
    // floor, the top of its taskbar.
    internal static class Desk
    {
        private static readonly HashSet<string> Shell = new HashSet<string>
        {
            "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow",
            "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland", "XamlExplorerHostIslandWindow",
        };

        internal static List<Ledge> Ledges(double s, ICollection<IntPtr> ours)
        {
            List<Ledge> found = new List<Ledge>();
            int z = 0;
            Native.EnumWindows((hwnd, _) =>
            {
                if (ours.Contains(hwnd) || !Native.IsWindowVisible(hwnd) || Native.IsIconic(hwnd) || Native.Cloaked(hwnd)) return true;
                int ex = Native.GetWindowLong(hwnd, Native.GWL_EXSTYLE);
                if ((ex & Native.WS_EX_TOOLWINDOW) != 0 || Shell.Contains(Native.Class(hwnd)) || Native.Text(hwnd).Length == 0) return true;
                Rectangle r = Native.Frame(hwnd);
                if (r.Width < 120 || r.Height < 80) return true;
                int myZ = z++;
                // Room above for her to sit, and wide enough for her.
                if (r.Width < s * 0.6 || r.Top - s * (Rules.Sit.Y - Rules.PerchTop) < ScreenTop(r)) return true;
                found.Add(new Ledge { X1 = r.Left, X2 = r.Right, Y = r.Top, Window = hwnd, Bounds = r, Z = myZ });
                return true;
            }, IntPtr.Zero);
            // Windows that only cover others still count for cover: re-walk with every window in z-order.
            List<Ledge> covers = new List<Ledge>();
            z = 0;
            Native.EnumWindows((hwnd, _) =>
            {
                if (ours.Contains(hwnd) || !Native.IsWindowVisible(hwnd) || Native.IsIconic(hwnd) || Native.Cloaked(hwnd)) return true;
                int ex = Native.GetWindowLong(hwnd, Native.GWL_EXSTYLE);
                if ((ex & Native.WS_EX_TOOLWINDOW) != 0 || Shell.Contains(Native.Class(hwnd)) || Native.Text(hwnd).Length == 0) return true;
                Rectangle r = Native.Frame(hwnd);
                if (r.Width < 120 || r.Height < 80) return true;
                int myZ = z++;
                if (!found.Exists(l => l.Window == hwnd))
                    covers.Add(new Ledge { X1 = r.Left, X2 = r.Right, Y = r.Top, Window = hwnd, Bounds = r, Z = myZ, Floor = false });
                return true;
            }, IntPtr.Zero);
            foreach (Screen screen in Screen.AllScreens)
            {
                Rectangle w = screen.WorkingArea;
                found.Add(new Ledge { X1 = w.Left + 8, X2 = w.Right - 8, Y = w.Bottom, Floor = true, Bounds = w, Z = int.MaxValue });
            }
            // Cover-only windows go last and are never landed on (their tops fail the room test).
            foreach (Ledge c in covers) { c.X2 = c.X1; found.Add(c); }
            return found;
        }

        private static int ScreenTop(Rectangle r)
        {
            return Screen.FromRectangle(r).Bounds.Top;
        }

        // The foreground window, as "process - title", and whether it fills its screen (a game or a video).
        internal static (string window, bool fullscreen, IntPtr hwnd) Foreground()
        {
            IntPtr fg = Native.GetForegroundWindow();
            if (fg == IntPtr.Zero) return ("", false, fg);
            string title = Native.Text(fg);
            string proc = "";
            try
            {
                Native.GetWindowThreadProcessId(fg, out uint pid);
                proc = System.Diagnostics.Process.GetProcessById((int)pid).ProcessName;
            }
            catch (Exception) { }
            string cls = Native.Class(fg);
            Native.GetWindowRect(fg, out Native.RECT r);
            Rectangle rect = Rectangle.FromLTRB(r.Left, r.Top, r.Right, r.Bottom);
            bool full = !Shell.Contains(cls) && rect == Screen.FromHandle(fg).Bounds;
            return ((proc.Length > 0 ? proc + " - " : "") + title, full, fg);
        }
    }
}
