using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace MiraPet
{
    // Her mini player (Capri's, in her colours): while anything plays, a small black plate with a pink-to-cyan neon
    // edge in the bottom-left of the main screen - the song, the artist, time, a seek bar, previous/play/next, a menu
    // and an X - and its top edge is a ledge she can sit on. Drag it by its body; it keeps that spot.
    // Shows while playing and for a minute after a pause; X puts it away until nothing has played for 10 s.
    internal sealed class MiniPlayer : Form
    {
        private static readonly Color Pink = Color.FromArgb(255, 42, 109), Cyan = Color.FromArgb(5, 217, 232);
        private const int W = 360, H = 92, Cut = 12;
        private readonly Senses senses;
        private readonly Timer timer = new Timer { Interval = 250 };
        private readonly Font titleFont = new Font("Consolas", 10.5f, FontStyle.Bold), smallFont = new Font("Consolas", 8.5f);
        private readonly Font glyphs = new Font("Segoe MDL2 Assets", 13f);
        private Rectangle prevBox, playBox, nextBox, closeBox, menuBox, seekBox;
        private DateTime lastPlaying = DateTime.MinValue;
        private bool putAway, dragging;
        private Point dragFrom;
        private double flicker;

        internal bool Off;                      // turned off from its menu (persisted by the pet)
        internal bool Suppressed;               // fullscreen game/video, or she's hidden
        internal event Action Changed;          // turned off/on from its own menu

        internal MiniPlayer(Senses senses)
        {
            this.senses = senses;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            Size = new Size(W, H);
            BackColor = Color.FromArgb(1, 1, 1);
            TransparencyKey = BackColor;
            DoubleBuffered = true;
            Text = "MIRA mini player";
            Rectangle area = Screen.PrimaryScreen.WorkingArea;
            Location = new Point(area.Left + 16, area.Bottom - H - 16);
            timer.Tick += (_, __) => Step();
            timer.Start();
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= 0x80 | 0x08000000;    // a tool window (no taskbar/alt-tab), never takes focus
                return cp;
            }
        }

        protected override bool ShowWithoutActivation => true;

        private void Step()
        {
            Senses.NowPlaying n = senses.Now;
            DateTime t = DateTime.Now;
            bool has = n != null && n.Title.Length > 0;
            if (has && n.Playing) lastPlaying = t;
            if (putAway && (t - lastPlaying).TotalSeconds > 10) putAway = false;
            bool want = !Off && !Suppressed && !putAway && has && (t - lastPlaying).TotalSeconds < 60;
            if (want && !Visible) Show();
            else if (!want && Visible) Hide();
            if (Visible) { flicker = (flicker + 0.25) % 1000; Invalidate(); }
        }

        private static string Clock(TimeSpan t) => t.TotalHours >= 1 ? t.ToString(@"h\:mm\:ss") : t.ToString(@"m\:ss");

        private TimeSpan Position(Senses.NowPlaying n)
        {
            TimeSpan p = n.Position;
            if (n.Playing && n.Read != default) p += DateTimeOffset.Now - n.Read;
            return n.Length > TimeSpan.Zero && p > n.Length ? n.Length : (p < TimeSpan.Zero ? TimeSpan.Zero : p);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
            Point[] plate =
            {
                new Point(Cut, 1), new Point(W - 2, 1), new Point(W - 2, H - Cut), new Point(W - Cut, H - 2),
                new Point(1, H - 2), new Point(1, Cut),
            };
            using (SolidBrush black = new SolidBrush(Color.FromArgb(14, 12, 18))) g.FillPolygon(black, plate);
            using (LinearGradientBrush edge = new LinearGradientBrush(new Point(0, 0), new Point(W, H), Pink, Cyan))
            using (Pen pen = new Pen(edge, 2f)) g.DrawPolygon(pen, plate);
            Senses.NowPlaying n = senses.Now;
            if (n == null) return;
            // a little glitch in the title now and then, like her
            int jitter = (int)(flicker * 4) % 97 == 0 ? 2 : 0;
            Rectangle text = new Rectangle(16, 10, W - 80, 20);
            TextRenderer.DrawText(g, n.Title, titleFont, new Rectangle(text.X + jitter, text.Y, text.Width, text.Height), Color.White,
                TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
            TextRenderer.DrawText(g, n.Artist, smallFont, new Rectangle(16, 30, W - 80, 16), Cyan,
                TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
            menuBox = new Rectangle(W - 58, 8, 20, 20);
            closeBox = new Rectangle(W - 32, 8, 20, 20);
            TextRenderer.DrawText(g, "", glyphs, menuBox, Color.Gainsboro);
            TextRenderer.DrawText(g, "", glyphs, closeBox, Color.Gainsboro);
            seekBox = new Rectangle(16, 54, W - 32, 6);
            using (SolidBrush track = new SolidBrush(Color.FromArgb(50, 50, 60))) g.FillRectangle(track, seekBox);
            if (n.Length > TimeSpan.Zero)
            {
                TimeSpan p = Position(n);
                int fill = (int)(seekBox.Width * Math.Min(1.0, p.TotalSeconds / n.Length.TotalSeconds));
                using (LinearGradientBrush bar = new LinearGradientBrush(seekBox, Pink, Cyan, 0f)) g.FillRectangle(bar, seekBox.X, seekBox.Y, Math.Max(1, fill), seekBox.Height);
                TextRenderer.DrawText(g, Clock(p) + " / " + Clock(n.Length), smallFont, new Rectangle(W - 140, 64, 124, 18), Color.Gray,
                    TextFormatFlags.Right);
            }
            prevBox = new Rectangle(16, 64, 24, 22);
            playBox = new Rectangle(46, 64, 24, 22);
            nextBox = new Rectangle(76, 64, 24, 22);
            TextRenderer.DrawText(g, "", glyphs, prevBox, Color.White);
            TextRenderer.DrawText(g, n.Playing ? "" : "", glyphs, playBox, Pink);
            TextRenderer.DrawText(g, "", glyphs, nextBox, Color.White);
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right) { ShowMenu(e.Location); return; }
            if (e.Button != MouseButtons.Left) return;
            if (prevBox.Contains(e.Location)) senses.Previous();
            else if (playBox.Contains(e.Location)) senses.PlayPause();
            else if (nextBox.Contains(e.Location)) senses.Next();
            else if (closeBox.Contains(e.Location)) { putAway = true; Hide(); }
            else if (menuBox.Contains(e.Location)) ShowMenu(e.Location);
            else if (Rectangle.Inflate(seekBox, 0, 6).Contains(e.Location)) SeekTo(e.X);
            else { dragging = true; dragFrom = e.Location; }
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (dragging) Location = new Point(Left + e.X - dragFrom.X, Top + e.Y - dragFrom.Y);
            else if (e.Button == MouseButtons.Left && Rectangle.Inflate(seekBox, 0, 6).Contains(e.Location)) SeekTo(e.X);
        }

        protected override void OnMouseUp(MouseEventArgs e) { dragging = false; }

        private void SeekTo(int x)
        {
            Senses.NowPlaying n = senses.Now;
            if (n == null || !n.CanSeek || n.Length <= TimeSpan.Zero) return;
            double share = Math.Max(0, Math.Min(1, (x - seekBox.X) / (double)seekBox.Width));
            senses.Seek(TimeSpan.FromSeconds(n.Length.TotalSeconds * share));
        }

        private void ShowMenu(Point at)
        {
            ContextMenuStrip m = new ContextMenuStrip();
            Senses.NowPlaying n = senses.Now;
            if (n != null && n.App.Length > 0)
                m.Items.Add("Open " + AppName(n.App), null, (_, __) => OpenApp(n.App));
            m.Items.Add("Hide for now", null, (_, __) => { putAway = true; Hide(); });
            m.Items.Add("Turn off mini player", null, (_, __) => { Off = true; Hide(); Changed?.Invoke(); });
            m.Show(this, at);
        }

        private static string AppName(string aumid)
        {
            string name = aumid.Split('!')[0];
            int dot = name.LastIndexOf('.');
            name = dot >= 0 && !name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ? name.Substring(dot + 1) : name;
            name = name.Replace(".exe", "").Replace("_", " ");
            return name.Length > 0 ? char.ToUpper(name[0]) + name.Substring(1) : "the player";
        }

        private static void OpenApp(string aumid)
        {
            try { Process.Start(new ProcessStartInfo("explorer.exe", "shell:AppsFolder\\" + aumid) { UseShellExecute = true }); }
            catch (Exception) { }
        }

        // Her seat on it: the plate's top edge.
        internal Ledge AsLedge() => new Ledge { X1 = Left + Cut, X2 = Right - Cut, Y = Top + 1, Window = Handle, Bounds = Bounds, Z = 0 };

        protected override void Dispose(bool disposing)
        {
            if (disposing) { timer.Dispose(); titleFont.Dispose(); smallFont.Dispose(); glyphs.Dispose(); }
            base.Dispose(disposing);
        }
    }
}
