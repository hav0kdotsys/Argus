using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Text.Json;
using System.Windows.Forms;

namespace MiraPet
{
    // The engine's move as an arrow over the coached board (arrow.json from her chess coach: the board's squares on
    // the screen, the move's squares, which way up the board is). A click-through layered window just over the board;
    // gone when the position changes, coaching stops, or it's ten minutes old.
    internal sealed class Arrow : Form
    {
        private string shownId = "";

        internal Arrow()
        {
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
                p.ExStyle |= Native.WS_EX_LAYERED | Native.WS_EX_TOOLWINDOW | Native.WS_EX_TOPMOST | Native.WS_EX_NOACTIVATE | 0x20;
                return p;
            }
        }

        protected override bool ShowWithoutActivation => true;

        internal void Take(JsonElement? file)
        {
            if (!(file is JsonElement a) || a.ValueKind != JsonValueKind.Object || !a.TryGetProperty("at", out JsonElement at)
                || at.ValueKind != JsonValueKind.Number || Ears.UnixNow - at.GetDouble() > 600
                || !a.TryGetProperty("box", out JsonElement box) || box.ValueKind != JsonValueKind.Array || box.GetArrayLength() != 4
                || !a.TryGetProperty("from", out JsonElement from) || !a.TryGetProperty("to", out JsonElement to))
            {
                if (Visible) Hide();
                shownId = "";
                return;
            }
            string id = a.TryGetProperty("id", out JsonElement i) ? i.ToString() : "";
            if (id == shownId && Visible) return;
            shownId = id;
            Rectangle r = Rectangle.FromLTRB(box[0].GetInt32(), box[1].GetInt32(), box[2].GetInt32(), box[3].GetInt32());
            bool whiteBottom = !a.TryGetProperty("white_bottom", out JsonElement wb) || wb.ValueKind != JsonValueKind.False;
            if (r.Width < 64 || r.Height < 64) return;
            using (Bitmap canvas = Paint(r.Size, from.GetString() ?? "", to.GetString() ?? "", whiteBottom))
            {
                if (!Visible) Show();
                Native.Show(Handle, canvas, r.Location);
            }
        }

        private static PointF Centre(Size s, string sq, bool whiteBottom)
        {
            int f = sq[0] - 'a', rank = sq[1] - '1';
            int col = whiteBottom ? f : 7 - f, row = whiteBottom ? 7 - rank : rank;
            return new PointF((col + 0.5f) * s.Width / 8f, (row + 0.5f) * s.Height / 8f);
        }

        private static Bitmap Paint(Size size, string from, string to, bool whiteBottom)
        {
            Bitmap b = new Bitmap(size.Width, size.Height, PixelFormat.Format32bppArgb);
            if (from.Length < 2 || to.Length < 2) return b;
            float sq = Math.Min(size.Width, size.Height) / 8f;
            PointF p = Centre(size, from, whiteBottom), q = Centre(size, to, whiteBottom);
            double ang = Math.Atan2(q.Y - p.Y, q.X - p.X);
            float head = sq * 0.42f, wide = sq * 0.17f;
            PointF end = new PointF(q.X - (float)Math.Cos(ang) * head * 0.8f, q.Y - (float)Math.Sin(ang) * head * 0.8f);
            Color pink = Color.FromArgb(205, 255, 42, 109), glow = Color.FromArgb(80, 255, 42, 109), cyan = Color.FromArgb(220, 5, 217, 232);
            using (Graphics g = Graphics.FromImage(b))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                using (Pen halo = new Pen(glow, wide * 2.2f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                    g.DrawLine(halo, p, end);
                using (Pen shaft = new Pen(pink, wide) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                    g.DrawLine(shaft, p, end);
                using (SolidBrush fill = new SolidBrush(pink))
                    g.FillPolygon(fill, new[]
                    {
                        q,
                        new PointF(q.X - (float)Math.Cos(ang - 0.5) * head, q.Y - (float)Math.Sin(ang - 0.5) * head),
                        new PointF(q.X - (float)Math.Cos(ang + 0.5) * head, q.Y - (float)Math.Sin(ang + 0.5) * head),
                    });
                using (Pen ring = new Pen(cyan, Math.Max(2f, wide * 0.18f)))
                    g.DrawEllipse(ring, p.X - sq * 0.2f, p.Y - sq * 0.2f, sq * 0.4f, sq * 0.4f);
            }
            return b;
        }
    }
}
