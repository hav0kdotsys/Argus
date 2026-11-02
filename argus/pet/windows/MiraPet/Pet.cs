using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Windows.Forms;

namespace MiraPet
{
    // Mira's body on Windows. The same life as argus/pet/mira-pet/shell.qml on laphvk - arrive glitching in, sit on
    // window tops or the taskbar, stand, walk, hop, lie down, sleep and wake, dance to music, dangle and fall, follow
    // her window, talk, blink, glitch, breathe - and the same companion protocol in %ARGUS_HOME%\companion:
    // say.json (what she says), body.json (her actions), event.json (pats, tosses, pokes, waking her) and
    // state.json (what she sees here: idle time, the foreground window, fullscreen, what's playing).
    internal sealed class Pet : Form
    {
        private static readonly string ArgusHome = Environment.GetEnvironmentVariable("ARGUS_HOME")
            ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "argus");
        private static readonly string Companion = Path.Combine(ArgusHome, "companion");
        private static readonly string Sprites = Path.Combine(ArgusHome, "sprites", "mira");
        private static readonly double[] Sizes = { 160, 200, 240, 300, 380 };
        private static readonly string[] SizeNames = { "Small", "Medium", "Large", "Huge", "Giant" };

        private readonly Sheets sheets;
        private readonly Senses senses = new Senses();
        private MiniPlayer player;
        private bool playerUp, playerOff, clickThrough;
        private readonly Bubble bubble;
        private readonly Image face;
        private readonly NotifyIcon tray;
        private readonly ContextMenuStrip menu;
        private readonly Timer clock = new Timer();
        private readonly Random rng = new Random();
        private readonly System.Diagnostics.Stopwatch watch = System.Diagnostics.Stopwatch.StartNew();

        // settings (pet-windows.json)
        private int sizeIndex = 1;
        private bool overGames;

        // state
        private double S => Sizes[sizeIndex];
        private string mode = "hidden";              // hidden, resting, walking, falling, dragging, hanging
        private string current = "idle";
        private bool oneShot;
        private Action after;
        private double clipStart;
        private int facing = 1;
        private double ax = 300, ay = 600;           // her square's top-left, screen pixels
        private Ledge ledge;
        private List<Ledge> spots = new List<Ledge>();
        private bool lying, sleeping, forcedSleep, floorSit, gameHidden, riding;
        private double danceUntil, nextWander, nextLie, lyingUntil, nextGlitch, nextPosture, hiddenUntil, nextLedges, nextState, nextFiles;
        private double vy, fallFrom, walkTo;
        private Ledge fallTo;
        private int lastCycle = -1;
        private string blinkWith = "";
        private string said = "";
        private double saidUntil;
        private string lastSay = "", lastBody = "";
        private bool filesRead;                     // the first read only notes what was already there
        private readonly Dictionary<string, double> told = new Dictionary<string, double>();
        private bool pressed;
        private Point down, grab;
        private readonly List<double> clicks = new List<double>();
        private readonly List<double> turns = new List<double>();
        private int petX, petWay;
        private double petAt = -60;
        private double lastTick;

        private double Now => watch.Elapsed.TotalSeconds;
        private bool Talking => said.Length > 0;
        private bool Grooving => (senses.Playing || danceUntil > Now) && !Talking;
        private bool Seated => ledge != null && mode == "resting" && (!ledge.Floor || floorSit);
        private bool Quiet => mode == "resting" && !oneShot && !Talking;

        internal Pet()
        {
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.Manual;
            TopMost = true;
            Text = "Mira";
            Directory.CreateDirectory(Companion);
            sheets = new Sheets(Path.Combine(Sprites, "grid"));
            string facePath = Path.Combine(Sprites, "face.png");
            face = File.Exists(facePath) ? Image.FromFile(facePath) : null;
            bubble = new Bubble(face);
            Load_();
            player = new MiniPlayer(senses) { Off = playerOff };
            player.Changed += () => { playerOff = player.Off; Save(); };
            menu = BuildMenu();
            tray = new NotifyIcon
            {
                Text = "Mira",
                Icon = face != null ? Icon.FromHandle(new Bitmap(face, 32, 32).GetHicon()) : SystemIcons.Application,
                ContextMenuStrip = menu,
                Visible = true,
            };
            tray.DoubleClick += (_, __) => Command(mode == "hidden" ? "show" : "hide");
            HandleCreated += (_, __) => Keys_(true);
            clock.Tick += (_, __) => Tick();
            clock.Interval = 33;
            clock.Start();
            lastTick = Now;
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams p = base.CreateParams;
                p.ExStyle |= Native.WS_EX_LAYERED | Native.WS_EX_TOOLWINDOW | Native.WS_EX_TOPMOST | Native.WS_EX_NOACTIVATE;
                return p;
            }
        }

        protected override bool ShowWithoutActivation => true;

        // Her keys, from anywhere, like Capri's: Ctrl+Alt+T type to her, Ctrl+Alt+H hide or show her, Ctrl+Alt+P quiet.
        private void Keys_(bool on)
        {
            (int id, Keys key)[] keys = { (1, Keys.T), (2, Keys.H), (3, Keys.P), (4, Keys.C) };
            foreach ((int id, Keys key) in keys)
            {
                if (on) Native.RegisterHotKey(Handle, id, Native.MOD_CONTROL | Native.MOD_ALT | Native.MOD_NOREPEAT, (int)key);
                else Native.UnregisterHotKey(Handle, id);
            }
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == Native.WM_HOTKEY)
            {
                switch ((int)m.WParam)
                {
                    case 1: TypeToHer(); break;
                    case 2: Command(mode == "hidden" ? "show" : "hide"); break;
                    case 3: ToggleQuiet(); break;
                    case 4: Command(riding ? "hop_off" : "ride"); break;
                }
                return;
            }
            base.WndProc(ref m);
        }

        private TypeBox typing;

        private void TypeToHer()
        {
            if (typing != null && !typing.IsDisposed) { typing.Activate(); return; }
            if (mode == "hidden") Command("show");
            typing = new TypeBox(text => WriteJson("ask.json", new Dictionary<string, object>
            {
                ["id"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds().ToString(), ["text"] = text, ["at"] = DateTimeOffset.UtcNow.ToString("o"),
            }));
            PointF hip = Hip();
            typing.Open(Point.Round(hip), Screen.FromPoint(Point.Round(hip)).WorkingArea);
        }

        private static string QuietFile => Path.Combine(Companion, "quiet");
        private bool QuietOn => File.Exists(QuietFile);

        private void ToggleQuiet()
        {
            try
            {
                if (QuietOn) File.Delete(QuietFile); else File.WriteAllText(QuietFile, DateTimeOffset.UtcNow.ToString("o"));
            }
            catch (IOException) { }
            ShowLine(QuietOn ? "Going quiet. Ctrl+Alt+P when you want me back." : "I'm back.");
        }

        // A line of her own in the bubble (not through the companion: her body's own acknowledgements).
        private void ShowLine(string text)
        {
            said = text;
            saidUntil = Now + 4;
            bubble.Say(said, Point.Round(Hip()), Screen.FromPoint(Point.Round(Hip())).WorkingArea);
        }

        // ---------------------------------------------------------------- clips

        private void Play(string name, Action then = null)
        {
            current = name;
            clipStart = Now;
            oneShot = true;
            after = then;
            lastCycle = -1;
        }

        private string LoopClip()
        {
            if (mode == "dragging" || mode == "falling" || mode == "hanging") return "dangle";
            if (mode == "walking") return "walk";
            if (Seated && lying) return sleeping ? "laydown_sleep" : (Talking ? "laydown_talk" : "laydown");
            if (Seated) return Talking ? "perch_talk" : (Grooving ? "perch_music" : "perch");
            if (sleeping) return "sleep";
            if (Grooving) return "dance";
            return "idle";
        }

        private string GlitchClip() { return Seated ? (lying ? "laydown_glitch" : "perch_glitch") : "glitch"; }

        private int FrameIndex(ClipInfo info) { return info == null ? 0 : (int)Math.Floor((Now - clipStart) * info.Fps); }

        private void Animate()
        {
            ClipInfo info = sheets.Info(current);
            if (info == null) return;
            int index = FrameIndex(info);
            if (oneShot)
            {
                int runs = current == "grin" ? 2 : 1;
                if (index >= info.Frames * runs)
                {
                    Action then = after;
                    oneShot = false;
                    after = null;
                    current = LoopClip();
                    clipStart = Now;
                    then?.Invoke();
                }
                return;
            }
            string want = LoopClip();
            if (want != current) { current = want; clipStart = Now; lastCycle = -1; return; }
            int cycle = index / info.Frames;
            if (cycle != lastCycle)
            {
                lastCycle = cycle;
                double roll = rng.NextDouble();
                string blink = current == "idle" ? "blink" : current == "perch" ? "perch_blink" : current == "laydown" ? "laydown_blink" : null;
                blinkWith = blink != null && !sleeping ? (roll < 0.1 ? blink + "_glitch" : roll < 0.55 ? blink : "") : "";
                if (Now >= nextGlitch && Quiet && !sleeping && (current == "idle" || current == "perch" || current == "laydown"))
                {
                    nextGlitch = Now + 30 + rng.NextDouble() * 30;
                    if (cycle > 0) Play(GlitchClip());
                }
            }
        }

        // ---------------------------------------------------------------- where she is

        private PointF Hip()
        {
            PointF h = Rules.HipShare(Rules.FamilyOf(current).Seated || Seated, facing);
            return new PointF((float)(ax + h.X * S), (float)(ay + h.Y * S));
        }

        private void PlaceOn(Ledge l, double x, bool sit)
        {
            // Lying along a floor, her hanging limbs would sink below it: lift her a little.
            double y = l.Floor && lying ? l.Y - S * 0.2 : l.Y;
            PointF a = Rules.AnchorFor(x, y, S, sit, facing);
            ax = a.X;
            ay = a.Y;
        }

        private void Settle(Ledge l, double x, bool sit = false)
        {
            ledge = l;
            mode = "resting";
            floorSit = l.Floor && sit;
            x = Rules.ClampX(l, x, S);
            Rectangle screen = Screen.FromPoint(new Point((int)x, l.Y - 1)).Bounds;
            facing = x > screen.Left + screen.Width / 2 ? -1 : 1;
            PlaceOn(l, x, !l.Floor || floorSit);
        }

        private Ledge RandomSpot(bool preferWindow)
        {
            List<Ledge> usable = spots.Where(l => l.X2 - l.X1 > S * 0.6).ToList();
            List<Ledge> windows = usable.Where(l => !l.Floor).ToList();
            if (preferWindow && windows.Count > 0 && rng.NextDouble() < 0.6) return windows[rng.Next(windows.Count)];
            List<Ledge> floors = usable.Where(l => l.Floor).ToList();
            Ledge primary = floors.FirstOrDefault(l => Screen.PrimaryScreen.WorkingArea.Contains(l.X1 + 20, l.Y - 2));
            return primary ?? floors.FirstOrDefault();
        }

        private void Appear()
        {
            Ledge l = RandomSpot(true);
            if (l == null) return;
            bool sit = l.Floor && rng.NextDouble() < 0.4;
            Settle(l, l.X1 + (l.X2 - l.X1) * rng.NextDouble(), sit);
            lying = false;
            Play(l.Floor && !sit ? "arrive" : "perch_arrive");
            nextWander = Now + 40 + rng.NextDouble() * 60;
            nextLie = Now + 90 + rng.NextDouble() * 240;
            nextGlitch = Now + 20 + rng.NextDouble() * 30;
            nextPosture = Now + 90 + rng.NextDouble() * 150;
            if (!Visible) Show();
        }

        private void Vanish(Action then = null)
        {
            lying = false;
            Play(Seated ? "perch_leave" : "leave", () => { mode = "hidden"; Hide(); bubble.Quiet(); then?.Invoke(); });
        }

        // Glitch over to the pointer and drop onto whatever is under it.
        private void ComeHere()
        {
            if (mode == "dragging") return;
            riding = false;
            Point c = Cursor.Position;
            Vanish(() =>
            {
                Show();
                Settle(new Ledge { X1 = c.X - 4, X2 = c.X + 4, Y = c.Y, Free = true }, c.X, false);
                Play("glitch", Fall);
            });
        }

        // "Sit on my Discord window": the ledge of the first window whose title or app name has the words in it.
        private void PerchOn(string what)
        {
            if (what.Length == 0) return;
            if (what == "taskbar" || what == "floor") { Command("floor"); return; }
            if (what == "player" || what == "mini player") { if (player.Visible) Teleport(player.AsLedge(), true); return; }
            Ledge l = spots.FirstOrDefault(x => !x.Floor && x.Window != IntPtr.Zero && Names(x.Window).IndexOf(what, StringComparison.OrdinalIgnoreCase) >= 0);
            if (l != null) Teleport(l, true);
        }

        private static string Names(IntPtr hwnd)
        {
            string title = Native.Text(hwnd);
            try
            {
                Native.GetWindowThreadProcessId(hwnd, out uint pid);
                return title + " " + System.Diagnostics.Process.GetProcessById((int)pid).ProcessName;
            }
            catch (Exception) { return title; }
        }

        private void Teleport(Ledge l, bool sit)
        {
            riding = false;
            Vanish(() => { Show(); Settle(l, l.X1 + (l.X2 - l.X1) * 0.4, sit); Play(l.Floor && !sit ? "arrive" : "perch_arrive"); });
        }

        private void Hop()
        {
            List<Ledge> others = spots.Where(l => l.X2 - l.X1 > S * 0.6 && (ledge == null || l.Window != ledge.Window || l.Floor != ledge.Floor)).ToList();
            if (others.Count == 0) return;
            Ledge l = others[rng.Next(others.Count)];
            bool sit = l.Floor && rng.NextDouble() < 0.4;
            Vanish(() => { Show(); Settle(l, l.X1 + (l.X2 - l.X1) * rng.NextDouble(), sit); Play(l.Floor && !sit ? "arrive" : "perch_arrive"); });
        }

        private void Walk()
        {
            if (ledge == null) return;
            PointF h = Hip();
            double target = Rules.ClampX(ledge, ledge.X1 + (ledge.X2 - ledge.X1) * rng.NextDouble(), S);
            if (Math.Abs(target - h.X) < S * 0.5) return;
            facing = target > h.X ? 1 : -1;
            lying = false;
            floorSit = false;
            mode = "walking";
            walkTo = target;
            PlaceOn(ledge, h.X, false);
        }

        private void EndWalk()
        {
            double x = Hip().X;
            mode = "resting";
            PlaceOn(ledge, x, !ledge.Floor);
            if (!ledge.Floor) Play("perch_glitch");
        }

        private void Fall()
        {
            lying = false;
            sleeping = false;
            PointF h = Hip();
            mode = "falling";
            ledge = null;
            vy = 0;
            fallFrom = h.Y;
            fallTo = Rules.Below(spots, h.X, h.Y, S);
        }

        private void Land(Ledge l)
        {
            PointF h = Hip();
            double drop = l.Y - fallFrom;
            Settle(l, h.X);
            Play(l.Floor ? "glitch" : "perch_glitch");
            if (drop > S * 2.2) Tell("tossed");
        }

        private void Posture(bool sit)
        {
            if (ledge == null || !ledge.Floor || floorSit == sit) return;
            double x = Hip().X;
            floorSit = sit;
            lying = false;
            PlaceOn(ledge, x, sit);
            Play(sit ? "perch_glitch" : "glitch");
        }

        private void LieDown(int f, double stay)
        {
            double x = Hip().X;
            facing = f;
            lying = true;
            PlaceOn(ledge, x, true);
            if (stay > 0) lyingUntil = Now + stay;
        }

        private void GetUp()
        {
            double x = Hip().X;
            lying = false;
            PlaceOn(ledge, x, true);
            Play("perch_glitch");
        }

        // ---------------------------------------------------------------- the world

        private void Physics(double dt)
        {
            if (mode == "falling")
            {
                vy += S * 11 * dt;
                ay += vy * dt;
                Ledge target = fallTo ?? spots.FirstOrDefault(l => l.Floor);
                if (target != null && Hip().Y >= target.Y) Land(target);
            }
            else if (mode == "walking")
            {
                double step = S * 0.42 * dt, x = Hip().X;
                if (Math.Abs(walkTo - x) <= step) { ax += walkTo - x; EndWalk(); }
                else ax += facing * step;
            }
        }

        private void Behave()
        {
            (string window, bool fullscreen, IntPtr fg) = Desk.Foreground();
            bool game = fullscreen && fg != Handle;
            if (mode == "hidden")
            {
                if (gameHidden && !game) { gameHidden = false; hiddenUntil = 0; }
                if (!gameHidden && (said.Length > 0 || Now >= hiddenUntil) && spots.Count > 0) Appear();
                return;
            }
            if (game && !overGames && mode == "resting" && !oneShot) { gameHidden = true; Vanish(); return; }
            if (mode != "resting" || ledge == null) return;
            if (!ledge.Floor && !ledge.Free)
            {
                Ledge c = spots.FirstOrDefault(l => l.Window == ledge.Window && !l.Floor && l.X2 > l.X1);
                if (c == null) { Play(GlitchClip(), Fall); return; }
                if (c.Y != ledge.Y || c.X1 != ledge.X1 || c.X2 != ledge.X2)
                {
                    double x = Hip().X + (c.X2 - c.X1 == ledge.X2 - ledge.X1 ? c.X1 - ledge.X1 : 0);
                    ledge = c;
                    PlaceOn(c, Rules.ClampX(c, x, S), true);
                }
                else ledge = c;
                if (Rules.Covered(c, Hip().X, spots)) { Play(GlitchClip(), Fall); return; }
            }
            bool sleepy = (Native.IdleSeconds() >= 300 || forcedSleep) && !Talking;
            if (sleepy && !sleeping && !oneShot)
            {
                sleeping = true;
                if (ledge.Floor && !floorSit && rng.NextDouble() < 0.5) { floorSit = true; PlaceOn(ledge, Hip().X, true); }
                if (Seated && !lying) { int f = Rules.LieFacing(ledge, Hip().X, S); if (f != 0) LieDown(f, 0); }
            }
            else if (!sleepy && sleeping)
            {
                sleeping = false;
                if (Seated && lying) lyingUntil = Now + 20 + rng.NextDouble() * 20;
                else Play("wake");
            }
            if (!Quiet || sleeping || ledge.Free) return;
            if (ledge.Floor && !lying && Now >= nextPosture)
            {
                nextPosture = Now + 90 + rng.NextDouble() * 150;
                Posture(!floorSit);
                return;
            }
            if (Seated && !lying && Now >= nextLie)
            {
                int f = Rules.LieFacing(ledge, Hip().X, S);
                nextLie = Now + 480 + rng.NextDouble() * 240;
                if (f != 0) LieDown(f, 120 + rng.NextDouble() * 120);
            }
            else if (lying && Now >= lyingUntil) GetUp();
            else if (!lying && Now >= nextWander)
            {
                nextWander = Now + 60 + rng.NextDouble() * 120;
                if (rng.NextDouble() < 0.5) Walk(); else Hop();
            }
        }

        private void Tick()
        {
            double now = Now, dt = Math.Min(0.05, now - lastTick);
            lastTick = now;
            if (now >= nextLedges)
            {
                nextLedges = now + 0.5;
                spots = Desk.Ledges(S, new[] { Handle, bubble.Handle, player.Handle });
                PlayerTick();
            }
            if (now >= nextFiles) { nextFiles = now + 0.5; ReadFiles(); }
            if (now >= nextState) { nextState = now + 2; WriteState(); }
            if (said.Length > 0 && now >= saidUntil) { said = ""; bubble.Quiet(); }
            if (riding != clickThrough)
            {
                // Riding: clicks pass through her to whatever is under the pointer (Ctrl+Alt+C or the menu hop off).
                clickThrough = riding;
                int ex = Native.GetWindowLong(Handle, Native.GWL_EXSTYLE);
                Native.SetWindowLong(Handle, Native.GWL_EXSTYLE, riding ? ex | Native.WS_EX_TRANSPARENT : ex & ~Native.WS_EX_TRANSPARENT);
            }
            if (riding && mode == "resting")
            {
                // Riding the cursor: her seat is just under the pointer's tip, wherever it goes.
                Point c = Cursor.Position;
                ledge = new Ledge { X1 = c.X - 4, X2 = c.X + 4, Y = c.Y + 18, Free = true };
                PlaceOn(ledge, c.X + 6, true);
            }
            Physics(dt);
            Behave();
            Animate();
            if (mode != "hidden") { Stroke(); Render(); }
            ClipInfo info = sheets.Info(current);
            bool fast = mode != "resting" || (info != null && info.Fps >= 24) || current.Contains("glitch") || current.Contains("arrive") || current.Contains("leave");
            clock.Interval = mode == "hidden" ? 250 : fast ? 33 : 66;
        }

        // ---------------------------------------------------------------- drawing

        private Bitmap canvas;
        private int canvasFor;
        private static readonly ImageAttributes Red = Tint(1.0f, 0.16f, 0.43f, 0.45f), Cyan = Tint(0.02f, 0.85f, 0.91f, 0.45f),
                                                 Glow = Tint(0.78f, 0.49f, 1.0f, 0.35f);

        private static ImageAttributes Tint(float r, float g, float b, float a)
        {
            ImageAttributes at = new ImageAttributes();
            at.SetColorMatrix(new ColorMatrix(new[]
            {
                new float[] { 0, 0, 0, 0, 0 }, new float[] { 0, 0, 0, 0, 0 }, new float[] { 0, 0, 0, 0, 0 },
                new float[] { 0, 0, 0, a, 0 }, new float[] { r, g, b, 0, 1 },
            }));
            return at;
        }

        private void Render()
        {
            int key = (int)S;
            if (canvas == null || canvasFor != key)
            {
                canvas?.Dispose();
                canvas = new Bitmap((int)(S * 1.9), (int)(S * 1.7), PixelFormat.Format32bppArgb);
                canvasFor = key;
            }
            double ox = S * 0.45, oy = S * 0.35;                  // her square's place in the canvas
            string baseName = Rules.SheetFor(current, facing, sheets);
            ClipInfo info = sheets.Info(baseName);
            Bitmap sheet = sheets.Sheet(baseName);
            if (info == null || sheet == null) return;
            int index = FrameIndex(info);
            int cell = oneShot ? Math.Min(index, info.Frames - 1) : index % info.Frames;
            bool settled = current is "idle" or "perch" or "laydown" or "perch_music" or "dance" or "perch_talk" or "laydown_talk";
            double breathe = settled ? Math.Sin(Now * 1.75) * 2.2 * S / 240 : 0;
            double tilt = settled ? Math.Sin(Now * 0.95) * 0.65 : 0;
            RectangleF box = Rules.Box(current, info, S, facing);
            box.Offset((float)ox, (float)(oy + breathe));
            // blink: its frames replace the loop's for a few cells
            (int from, int n) rule = current == "idle" ? (9, 4) : current == "perch" || current == "laydown" ? (28, 8) : (-1, 0);
            string blinkName = rule.from >= 0 && blinkWith.Length > 0 && cell >= rule.from && cell < rule.from + rule.n
                ? Rules.SheetFor(blinkWith, facing, sheets) : null;
            Bitmap drawSheet = sheet;
            Rectangle src = info.Cell(cell);
            if (blinkName != null && sheets.Has(blinkName))
            {
                drawSheet = sheets.Sheet(blinkName);
                src = sheets.Info(blinkName).Cell(cell - rule.from);
            }
            bool glitching = current.Contains("glitch") || current.Contains("arrive") || current.Contains("leave") || (blinkName ?? "").Contains("glitch");
            using (Graphics g = Graphics.FromImage(canvas))
            {
                g.Clear(Color.Transparent);
                g.InterpolationMode = InterpolationMode.HighQualityBilinear;
                g.PixelOffsetMode = PixelOffsetMode.Half;
                g.SmoothingMode = SmoothingMode.AntiAlias;
                // a soft shadow where she meets her ledge
                if (mode == "resting")
                {
                    PointF hip = Rules.HipShare(Seated, facing);
                    float sx = (float)(ox + hip.X * S), sy = (float)(oy + hip.Y * S + (Seated ? 2 : -2));
                    using (GraphicsPath shadow = new GraphicsPath())
                    {
                        shadow.AddEllipse(sx - (float)S * 0.22f, sy - (float)S * 0.03f, (float)S * 0.44f, (float)S * 0.06f);
                        using (PathGradientBrush b = new PathGradientBrush(shadow) { CenterColor = Color.FromArgb(90, 0, 0, 0), SurroundColors = new[] { Color.FromArgb(0, 0, 0, 0) } })
                            g.FillPath(b, shadow);
                    }
                }
                g.TranslateTransform((float)(ox + S / 2), (float)(oy + S / 2));
                g.RotateTransform((float)tilt);
                g.TranslateTransform((float)-(ox + S / 2), (float)-(oy + S / 2));
                if (Talking) Draw(g, drawSheet, src, Grow(box, 0.04f), Glow);
                if (glitching)
                {
                    Draw(g, drawSheet, src, Shift(box, -(float)(2 + rng.NextDouble() * 3)), Red);
                    Draw(g, drawSheet, src, Shift(box, (float)(2 + rng.NextDouble() * 3)), Cyan);
                }
                Draw(g, drawSheet, src, box, null);
                if (Talking && current == "idle" && blinkName == null && sheets.Has("mouth"))
                    Draw(g, sheets.Sheet("mouth"), sheets.Info("mouth").Cell((int)(Now * 12)), box, null);
            }
            Native.Show(Handle, canvas, new Point((int)Math.Round(ax - ox), (int)Math.Round(ay - oy)));
            if (said.Length > 0 && bubble.Saying)
                bubble.Say(said, new Point((int)(ax - ox + box.X + box.Width / 2), (int)(ay - oy + box.Y)), Screen.FromPoint(Point.Round(Hip())).WorkingArea);
        }

        private static RectangleF Grow(RectangleF r, float by) { r.Inflate(r.Width * by, r.Height * by); return r; }
        private static RectangleF Shift(RectangleF r, float dx) { r.Offset(dx, 0); return r; }

        // Draw a cell into a box, mirrored when she faces left.
        private void Draw(Graphics g, Bitmap sheet, Rectangle src, RectangleF box, ImageAttributes attrs)
        {
            if (sheet == null) return;
            PointF[] corners = facing < 0
                ? new[] { new PointF(box.Right, box.Top), new PointF(box.Left, box.Top), new PointF(box.Right, box.Bottom) }
                : new[] { new PointF(box.Left, box.Top), new PointF(box.Right, box.Top), new PointF(box.Left, box.Bottom) };
            g.DrawImage(sheet, corners, src, GraphicsUnit.Pixel, attrs);
        }

        // ---------------------------------------------------------------- touch

        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            if (e.Button == MouseButtons.Right) { menu.Show(Cursor.Position); return; }
            if (e.Button == MouseButtons.Middle) { TypeToHer(); return; }
            if (e.Button != MouseButtons.Left) return;
            pressed = true;
            down = Cursor.Position;
            grab = new Point(down.X - (int)ax, down.Y - (int)ay);
            Capture = true;
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            if (!pressed) return;
            Point at = Cursor.Position;
            int dx = at.X - down.X, dy = at.Y - down.Y;
            if (mode != "dragging" && dx * dx + dy * dy < 36) return;
            if (mode != "dragging")
            {
                mode = "dragging"; ledge = null; lying = false; sleeping = false; forcedSleep = false; riding = false;
                oneShot = false; current = "dangle"; clipStart = Now;
                bubble.Quiet(); said = "";
            }
            ax = at.X - grab.X;
            ay = at.Y - grab.Y;
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            base.OnMouseUp(e);
            if (e.Button != MouseButtons.Left || !pressed) return;
            pressed = false;
            Capture = false;
            if (mode == "dragging")
            {
                // Like Capri: Shift sits her right where she's let go, Ctrl leaves her hanging there.
                if ((ModifierKeys & Keys.Shift) != 0) SitHere();
                else if ((ModifierKeys & Keys.Control) != 0) { mode = "hanging"; current = "dangle"; clipStart = Now; }
                else Fall();
            }
            else React();
        }

        protected override void OnMouseDoubleClick(MouseEventArgs e)
        {
            base.OnMouseDoubleClick(e);
            if (e.Button == MouseButtons.Left) Command(riding ? "hop_off" : "ride");
        }

        private void SitHere()
        {
            PointF h = Hip();
            Ledge seat = new Ledge { X1 = (int)h.X - 4, X2 = (int)h.X + 4, Y = (int)h.Y, Free = true };
            ledge = seat;
            mode = "resting";
            floorSit = false;
            PlaceOn(seat, h.X, true);
            Play("perch_glitch");
        }

        private void React()
        {
            double now = Now;
            if (mode == "hanging") { Play("glitch", Fall); return; }
            clicks.RemoveAll(t => now - t > 4);
            clicks.Add(now);
            if (clicks.Count >= 3) { clicks.Clear(); Tell("poked"); }
            if (said.Length > 0) { said = ""; bubble.Quiet(); return; }
            if (sleeping)
            {
                sleeping = false; forcedSleep = false; Tell("woke");
                if (!lying) Play("wake"); else lyingUntil = now + 30;
                return;
            }
            Play(GlitchClip());
        }

        // Pats: the cursor rubbed back and forth over her - four turns inside 1.5 s.
        private void Stroke()
        {
            Point c = Cursor.Position;
            RectangleF box = Rules.Box(current, sheets.Info(Rules.SheetFor(current, facing, sheets)), S, facing);
            box.Offset((float)ax, (float)ay);
            if (pressed || riding || mode != "resting" || !box.Contains(c)) { turns.Clear(); petWay = 0; petX = c.X; return; }
            int dx = c.X - petX;
            if (Math.Abs(dx) < 6) return;
            int way = Math.Sign(dx);
            petX = c.X;
            double now = Now;
            if (petWay != 0 && way != petWay) { turns.RemoveAll(t => now - t > 1.5); turns.Add(now); }
            petWay = way;
            if (turns.Count >= 4 && now - petAt > 20)
            {
                turns.Clear();
                petAt = now;
                if (Seated) blinkWith = lying ? "laydown_blink" : "perch_blink";
                else Play("grin");
                Tell("pat");
            }
        }

        // ---------------------------------------------------------------- the companion

        private void Tell(string kind)
        {
            if (told.TryGetValue(kind, out double at) && Now - at < 60) return;
            told[kind] = Now;
            WriteJson("event.json", new Dictionary<string, object>
            {
                ["id"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds().ToString(), ["kind"] = kind, ["at"] = DateTimeOffset.UtcNow.ToString("o"),
            });
        }

        private void WriteState()
        {
            (string window, bool fullscreen, IntPtr _) = Desk.Foreground();
            double idle = Native.IdleSeconds();
            WriteJson("state.json", new Dictionary<string, object>
            {
                ["idle_since"] = idle >= 60 ? DateTimeOffset.UtcNow.ToUnixTimeSeconds() - (long)idle : null,
                ["window"] = window.Length > 160 ? window.Substring(0, 160) : window,
                ["fullscreen"] = fullscreen,
                ["playing"] = senses.Track,
                ["machine"] = Environment.MachineName.ToLowerInvariant(),
                ["at"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            });
        }

        private static void WriteJson(string name, Dictionary<string, object> data)
        {
            try
            {
                string path = Path.Combine(Companion, name), tmp = path + ".tmp";
                File.WriteAllText(tmp, JsonSerializer.Serialize(data));
                File.Move(tmp, path, true);
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }

        private static JsonElement? ReadJson(string name)
        {
            try
            {
                string path = Path.Combine(Companion, name);
                if (!File.Exists(path)) return null;
                using (JsonDocument doc = JsonDocument.Parse(File.ReadAllText(path))) return doc.RootElement.Clone();
            }
            catch (Exception) { return null; }
        }

        private void ReadFiles()
        {
            JsonElement? say = ReadJson("say.json");
            if (say is JsonElement s && s.ValueKind == JsonValueKind.Object)
            {
                string text = s.TryGetProperty("text", out JsonElement t) ? (t.GetString() ?? "").Trim() : "";
                string id = s.TryGetProperty("id", out JsonElement i) ? i.ToString() : text;
                if (!filesRead) lastSay = id;                               // what was there before she started isn't news
                else if (text.Length > 0 && id != lastSay)
                {
                    lastSay = id;
                    said = text.Length > 400 ? text.Substring(0, 400) : text;
                    saidUntil = Now + Math.Max(8, Math.Min(25, said.Length * 0.08));
                    if (mode == "hidden") { gameHidden = false; hiddenUntil = 0; }
                    else if (mode == "resting" && !oneShot) Play(GlitchClip());
                    bubble.Say(said, Point.Round(Hip()), Screen.FromPoint(Point.Round(Hip())).WorkingArea);
                }
            }
            JsonElement? body = ReadJson("body.json");
            if (body is JsonElement b && b.ValueKind == JsonValueKind.Object)
            {
                string id = b.TryGetProperty("id", out JsonElement i) ? i.ToString() : "";
                string what = b.TryGetProperty("do", out JsonElement d) ? d.GetString() ?? "" : "";
                if (!filesRead) lastBody = id;
                else if (id.Length > 0 && id != lastBody) { lastBody = id; Command(what); }
            }
            filesRead = true;
        }

        private void Command(string what)
        {
            string arg = "";
            int space = what.IndexOf(' ');
            if (space > 0) { arg = what.Substring(space + 1).Trim(); what = what.Substring(0, space); }
            switch (what)
            {
                case "come_here": ComeHere(); break;
                case "perch": PerchOn(arg); break;
                case "floor": { Ledge f = spots.FirstOrDefault(l => l.Floor && l.X1 <= Cursor.Position.X && Cursor.Position.X <= l.X2) ?? spots.FirstOrDefault(l => l.Floor); if (f != null) Teleport(f, false); } break;
                case "show": if (mode == "hidden") { hiddenUntil = 0; gameHidden = false; Appear(); } break;
                case "hide": if (mode != "hidden") Vanish(() => hiddenUntil = Now + 900); break;
                case "hop": if (mode == "resting") Hop(); break;
                case "walk": if (mode == "resting") Walk(); break;
                case "drop": if (mode == "resting") { ay -= S * 1.5; Fall(); } break;
                case "lie": if (Seated && !lying) { int f = Rules.LieFacing(ledge, Hip().X, S); if (f != 0) LieDown(f, 180); } break;
                case "sit": if (lying) GetUp(); else Posture(true); break;
                case "stand": if (lying) GetUp(); Posture(false); break;
                case "sleep": if (mode == "resting") { sleeping = true; forcedSleep = true; } break;
                case "wake": if (sleeping) { sleeping = false; forcedSleep = false; if (!lying) Play("wake"); } break;
                case "dance": danceUntil = Now + 45; break;
                case "stop_dancing": danceUntil = 0; break;
                case "glitch": if (mode == "resting") Play(GlitchClip()); break;
                case "ride": if (mode == "resting" || mode == "hanging") { riding = true; lying = false; sleeping = false; mode = "resting"; Play("perch_glitch"); } break;
                case "hop_off": if (riding) { riding = false; Play("perch_glitch", Fall); } break;
                case "grin": if (mode == "resting" && !Seated) Play("grin"); else if (Seated) blinkWith = lying ? "laydown_blink" : "perch_blink"; break;
            }
        }

        // ---------------------------------------------------------------- tray, menu, settings

        private ContextMenuStrip BuildMenu()
        {
            ContextMenuStrip m = new ContextMenuStrip();
            m.Items.Add("Talk to Mira…   Ctrl+Alt+T", null, (_, __) => TypeToHer());
            m.Items.Add("Show / hide   Ctrl+Alt+H", null, (_, __) => Command(mode == "hidden" ? "show" : "hide"));
            ToolStripMenuItem quiet = new ToolStripMenuItem("Quiet   Ctrl+Alt+P");
            quiet.Click += (_, __) => ToggleQuiet();
            m.Opening += (_, __) => quiet.Checked = QuietOn;
            m.Items.Add(quiet);
            m.Items.Add("Dance", null, (_, __) => Command(danceUntil > Now ? "stop_dancing" : "dance"));
            m.Items.Add("Nap / wake up", null, (_, __) => Command(sleeping ? "wake" : "sleep"));
            m.Items.Add("Go somewhere else", null, (_, __) => Command("hop"));
            m.Items.Add("Ride my cursor / hop off   Ctrl+Alt+C", null, (_, __) => Command(riding ? "hop_off" : "ride"));
            m.Items.Add("Coach my chess (on / off)", null, (_, __) => { told.Remove("coach"); Tell("coach"); });
            m.Items.Add("Play a game with her…", null, (_, __) => { told.Remove("play"); Tell("play"); });
            ToolStripMenuItem size = new ToolStripMenuItem("Size");
            for (int i = 0; i < Sizes.Length; i++)
            {
                int pick = i;
                ToolStripMenuItem item = new ToolStripMenuItem(SizeNames[i]) { Checked = i == sizeIndex };
                item.Click += (_, __) =>
                {
                    double x = Hip().X;
                    sizeIndex = pick;
                    foreach (ToolStripMenuItem o in size.DropDownItems) o.Checked = o == item;
                    if (ledge != null) PlaceOn(ledge, x, Seated);
                    Save();
                };
                size.DropDownItems.Add(item);
            }
            m.Items.Add(size);
            ToolStripMenuItem games = new ToolStripMenuItem("Stay over games") { Checked = overGames, CheckOnClick = true };
            games.CheckedChanged += (_, __) => { overGames = games.Checked; Save(); };
            m.Items.Add(games);
            ToolStripMenuItem mini = new ToolStripMenuItem("Mini player") { Checked = !playerOff, CheckOnClick = true };
            mini.CheckedChanged += (_, __) => { playerOff = !mini.Checked; player.Off = playerOff; Save(); };
            m.Items.Add(mini);
            m.Items.Add(new ToolStripSeparator());
            m.Items.Add("Quit", null, (_, __) => { tray.Visible = false; Application.Exit(); });
            return m;
        }

        // The mini player: her seat while it's up, and the first time it comes up she hops onto it (like Capri),
        // unless she's somewhere Hannah put her (a Shift-drop seat, her cursor) or busy being carried.
        private void PlayerTick()
        {
            player.Suppressed = mode == "hidden" || gameHidden;
            bool up = player.Visible;
            if (up) spots.Insert(0, player.AsLedge());
            if (up && !playerUp && mode == "resting" && !riding && !(ledge?.Free ?? false) && !sleeping && !Talking)
            {
                Ledge seat = player.AsLedge();
                Vanish(() => { Show(); Settle(seat, seat.X1 + (seat.X2 - seat.X1) * 0.3, true); Play("perch_arrive"); });
            }
            playerUp = up;
        }

        private void Load_()
        {
            JsonElement? s = ReadJson("pet-windows.json");
            if (s is JsonElement e && e.ValueKind == JsonValueKind.Object)
            {
                if (e.TryGetProperty("size", out JsonElement z) && z.TryGetInt32(out int i)) sizeIndex = Math.Max(0, Math.Min(Sizes.Length - 1, i));
                if (e.TryGetProperty("over_games", out JsonElement g)) overGames = g.ValueKind == JsonValueKind.True;
                if (e.TryGetProperty("mini_player_off", out JsonElement mp)) playerOff = mp.ValueKind == JsonValueKind.True;
            }
        }

        private void Save()
        {
            WriteJson("pet-windows.json", new Dictionary<string, object>
            {
                ["size"] = sizeIndex, ["over_games"] = overGames, ["mini_player_off"] = playerOff,
            });
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                Keys_(false);
                clock.Dispose();
                senses.Dispose();
                player?.Dispose();
                tray.Dispose();
                bubble.Dispose();
                canvas?.Dispose();
                face?.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
