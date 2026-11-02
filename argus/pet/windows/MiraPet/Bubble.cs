using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.Windows.Forms;

namespace MiraPet
{
    // What she says, in a rounded bubble over her head: her face, then the words. Click-through, never takes focus.
    internal sealed class Bubble : Form
    {
        private readonly Image face;
        private readonly Font font = new Font("Segoe UI", 10.5f, FontStyle.Regular, GraphicsUnit.Point);
        private string text = "";

        internal Bubble(Image face)
        {
            this.face = face;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.Manual;
            TopMost = true;
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams p = base.CreateParams;
                p.ExStyle |= Native.WS_EX_LAYERED | Native.WS_EX_TOOLWINDOW | Native.WS_EX_TOPMOST | Native.WS_EX_NOACTIVATE
                             | 0x20;   // WS_EX_TRANSPARENT: clicks go straight through
                return p;
            }
        }

        protected override bool ShowWithoutActivation => true;

        internal bool Saying => Visible && text.Length > 0;

        // Show `words` near her head: centred over `head` (screen point), kept inside `area`.
        internal void Say(string words, Point head, Rectangle area)
        {
            text = words;
            const int maxText = 300, pad = 10, faceSize = 36;
            Size measured;
            using (Bitmap probe = new Bitmap(1, 1))
            using (Graphics g = Graphics.FromImage(probe))
                measured = Size.Ceiling(g.MeasureString(words, font, maxText));
            int w = Math.Min(maxText, measured.Width) + faceSize + pad * 3;
            int h = Math.Max(faceSize, measured.Height) + pad * 2;
            using (Bitmap canvas = new Bitmap(w, h, System.Drawing.Imaging.PixelFormat.Format32bppArgb))
            {
                using (Graphics g = Graphics.FromImage(canvas))
                {
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
                    g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                    using (GraphicsPath box = Rounded(new Rectangle(0, 0, w - 1, h - 1), 12))
                    using (SolidBrush fill = new SolidBrush(Color.FromArgb(238, 0x15, 0x0a, 0x1f)))
                    using (Pen edge = new Pen(Color.FromArgb(255, 0xc7, 0x7d, 0xff), 1.2f))
                    {
                        g.FillPath(fill, box);
                        g.DrawPath(edge, box);
                    }
                    if (face != null) g.DrawImage(face, new Rectangle(pad, (h - faceSize) / 2, faceSize, faceSize));
                    using (SolidBrush ink = new SolidBrush(Color.FromArgb(255, 0xf3, 0xe8, 0xff)))
                        g.DrawString(words, font, ink, new RectangleF(faceSize + pad * 2, pad, maxText, h - pad * 2));
                }
                int x = Math.Max(area.Left + 8, Math.Min(area.Right - w - 8, head.X - w / 2));
                int y = head.Y - h - 10 < area.Top + 8 ? head.Y + 20 : head.Y - h - 10;
                if (!Visible) Show();
                Native.Show(Handle, canvas, new Point(x, y));
            }
        }

        internal void Quiet()
        {
            text = "";
            if (Visible) Hide();
        }

        private static GraphicsPath Rounded(Rectangle r, int radius)
        {
            GraphicsPath p = new GraphicsPath();
            int d = radius * 2;
            p.AddArc(r.Left, r.Top, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Top, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.Left, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) font.Dispose();
            base.Dispose(disposing);
        }
    }
}
