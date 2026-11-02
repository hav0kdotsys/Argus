using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;

namespace MiraPet
{
    // The Windows calls her body needs: per-pixel-alpha (layered) windows, window enumeration and true frame bounds,
    // cloaking (windows on other virtual desktops or UWP ghosts), idle time and the foreground window.
    internal static class Native
    {
        internal const int WS_EX_LAYERED = 0x80000, WS_EX_TOOLWINDOW = 0x80, WS_EX_TOPMOST = 0x8, WS_EX_NOACTIVATE = 0x8000000;
        internal const int GWL_EXSTYLE = -20, GWL_STYLE = -16;
        internal const int WS_VISIBLE = 0x10000000, WS_CHILD = 0x40000000;
        internal const int ULW_ALPHA = 2;
        internal const byte AC_SRC_OVER = 0, AC_SRC_ALPHA = 1;
        internal const int DWMWA_EXTENDED_FRAME_BOUNDS = 9, DWMWA_CLOAKED = 14;

        [StructLayout(LayoutKind.Sequential)] internal struct POINT { public int X, Y; public POINT(int x, int y) { X = x; Y = y; } }
        [StructLayout(LayoutKind.Sequential)] internal struct SIZE { public int W, H; public SIZE(int w, int h) { W = w; H = h; } }
        [StructLayout(LayoutKind.Sequential)] internal struct RECT { public int Left, Top, Right, Bottom; }
        [StructLayout(LayoutKind.Sequential, Pack = 1)]
        internal struct BLENDFUNCTION { public byte BlendOp, BlendFlags, SourceConstantAlpha, AlphaFormat; }
        [StructLayout(LayoutKind.Sequential)] internal struct LASTINPUTINFO { public uint cbSize, dwTime; }

        [DllImport("user32.dll", SetLastError = true)]
        internal static extern bool UpdateLayeredWindow(IntPtr hwnd, IntPtr hdcDst, ref POINT pptDst, ref SIZE psize, IntPtr hdcSrc,
                                                        ref POINT pprSrc, int crKey, ref BLENDFUNCTION pblend, int dwFlags);
        internal const int WM_HOTKEY = 0x0312, MOD_ALT = 0x1, MOD_CONTROL = 0x2, MOD_NOREPEAT = 0x4000;
        [DllImport("user32.dll")] internal static extern bool RegisterHotKey(IntPtr hwnd, int id, int mods, int key);
        [DllImport("user32.dll")] internal static extern bool UnregisterHotKey(IntPtr hwnd, int id);
        [DllImport("user32.dll")] internal static extern IntPtr GetDC(IntPtr hwnd);
        [DllImport("user32.dll")] internal static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);
        [DllImport("gdi32.dll")] internal static extern IntPtr CreateCompatibleDC(IntPtr hdc);
        [DllImport("gdi32.dll")] internal static extern bool DeleteDC(IntPtr hdc);
        [DllImport("gdi32.dll")] internal static extern IntPtr SelectObject(IntPtr hdc, IntPtr obj);
        [DllImport("gdi32.dll")] internal static extern bool DeleteObject(IntPtr obj);

        internal delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);
        [DllImport("user32.dll")] internal static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
        [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr hwnd);
        [DllImport("user32.dll")] internal static extern bool IsIconic(IntPtr hwnd);
        [DllImport("user32.dll")] internal static extern int GetWindowLong(IntPtr hwnd, int index);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] internal static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int max);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] internal static extern int GetClassName(IntPtr hwnd, StringBuilder text, int max);
        [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
        [DllImport("user32.dll")] internal static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] internal static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
        [DllImport("user32.dll")] internal static extern bool GetLastInputInfo(ref LASTINPUTINFO info);
        [DllImport("dwmapi.dll")] internal static extern int DwmGetWindowAttribute(IntPtr hwnd, int attr, out RECT value, int size);
        [DllImport("dwmapi.dll")] internal static extern int DwmGetWindowAttribute(IntPtr hwnd, int attr, out int value, int size);

        internal static string Text(IntPtr hwnd)
        {
            StringBuilder b = new StringBuilder(256);
            GetWindowText(hwnd, b, b.Capacity);
            return b.ToString();
        }

        internal static string Class(IntPtr hwnd)
        {
            StringBuilder b = new StringBuilder(128);
            GetClassName(hwnd, b, b.Capacity);
            return b.ToString();
        }

        // The window's visible frame (without the invisible resize borders Windows 10/11 add), or its rect.
        internal static Rectangle Frame(IntPtr hwnd)
        {
            if (DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, out RECT r, Marshal.SizeOf<RECT>()) != 0)
                GetWindowRect(hwnd, out r);
            return Rectangle.FromLTRB(r.Left, r.Top, r.Right, r.Bottom);
        }

        internal static bool Cloaked(IntPtr hwnd)
        {
            return DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, out int c, sizeof(int)) == 0 && c != 0;
        }

        // Seconds since the last keyboard or mouse input in this session.
        internal static double IdleSeconds()
        {
            LASTINPUTINFO info = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf<LASTINPUTINFO>() };
            if (!GetLastInputInfo(ref info)) return 0;
            return unchecked((uint)Environment.TickCount - info.dwTime) / 1000.0;
        }

        // Draw a 32-bit ARGB bitmap as the layered window's whole content at screen point `at`.
        internal static void Show(IntPtr hwnd, Bitmap canvas, Point at)
        {
            IntPtr screen = GetDC(IntPtr.Zero);
            IntPtr mem = CreateCompatibleDC(screen);
            IntPtr bmp = canvas.GetHbitmap(Color.FromArgb(0));
            IntPtr old = SelectObject(mem, bmp);
            try
            {
                SIZE size = new SIZE(canvas.Width, canvas.Height);
                POINT src = new POINT(0, 0), dst = new POINT(at.X, at.Y);
                BLENDFUNCTION blend = new BLENDFUNCTION { BlendOp = AC_SRC_OVER, SourceConstantAlpha = 255, AlphaFormat = AC_SRC_ALPHA };
                UpdateLayeredWindow(hwnd, screen, ref dst, ref size, mem, ref src, 0, ref blend, ULW_ALPHA);
            }
            finally
            {
                SelectObject(mem, old);
                DeleteObject(bmp);
                DeleteDC(mem);
                ReleaseDC(IntPtr.Zero, screen);
            }
        }
    }
}
