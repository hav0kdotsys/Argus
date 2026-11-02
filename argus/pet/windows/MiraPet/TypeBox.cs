using System;
using System.Drawing;
using System.Windows.Forms;

namespace MiraPet
{
    // Typing to her: a small dark box by her, Enter sends (the companion answers in her bubble), Esc closes.
    internal sealed class TypeBox : Form
    {
        private readonly TextBox input = new TextBox();
        private readonly Action<string> send;

        internal TypeBox(Action<string> send)
        {
            this.send = send;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.Manual;
            TopMost = true;
            BackColor = Color.FromArgb(0xc7, 0x7d, 0xff);
            Padding = new Padding(1);
            Size = new Size(360, 38);
            input.BorderStyle = BorderStyle.None;
            input.BackColor = Color.FromArgb(0x15, 0x0a, 0x1f);
            input.ForeColor = Color.FromArgb(0xf3, 0xe8, 0xff);
            input.Font = new Font("Segoe UI", 11f);
            input.PlaceholderText = "Say something to Mira…";
            Panel inner = new Panel { Dock = DockStyle.Fill, BackColor = input.BackColor, Padding = new Padding(10, 8, 10, 6) };
            input.Dock = DockStyle.Fill;
            inner.Controls.Add(input);
            Controls.Add(inner);
            input.KeyDown += (_, e) =>
            {
                if (e.KeyCode == Keys.Escape) { e.SuppressKeyPress = true; Close(); }
                else if (e.KeyCode == Keys.Enter)
                {
                    e.SuppressKeyPress = true;
                    string text = input.Text.Trim();
                    Close();
                    if (text.Length > 0) send(text);
                }
            };
            Deactivate += (_, __) => Close();
        }

        // Open by her: under her feet when there's room, else above her, kept on her screen.
        internal void Open(Point near, Rectangle area)
        {
            int x = Math.Max(area.Left + 8, Math.Min(area.Right - Width - 8, near.X - Width / 2));
            int y = near.Y + 12 + Height < area.Bottom ? near.Y + 12 : near.Y - Height - 24;
            Location = new Point(x, y);
            Show();
            Activate();
            input.Focus();
        }
    }
}
