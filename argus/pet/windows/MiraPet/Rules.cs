using System;
using System.Collections.Generic;
using System.Drawing;

namespace MiraPet
{
    // Somewhere she can sit or stand: a window's top edge, or a screen's floor (the top of the taskbar).
    internal sealed class Ledge
    {
        public int X1, X2, Y;
        public IntPtr Window;            // IntPtr.Zero for a floor
        public bool Floor;
        public Rectangle Bounds;         // the window's frame (a floor: its screen's working area)
        public int Z;                    // z-order, 0 = topmost
    }

    // The same rules as argus/pet/mira-pet/pet.js: every clip is drawn in a box centred on her S x S square, `h` x S
    // tall, shifted by (sx, sy) x S; her hip (on the ledge) is at SIT of the square seated and STAND on her feet;
    // facing left draws the `_flipped` art mirrored (her limbs are asymmetric), or the plain clip mirrored.
    internal static class Rules
    {
        internal static readonly PointF Sit = new PointF(0.30f, 0.79f), Stand = new PointF(0.50f, 0.99f);
        internal const double PerchTop = 0.17;
        internal const double LieScale = 0.85;
        internal static readonly double LieH = 250.0 / 384 * LieScale;
        internal static readonly double LieSy = (0.79 - 0.5) * (1 - LieScale) + 94.0 / 384 * LieScale;
        internal static readonly double LieReach = 0.78 * LieScale;

        internal struct Family { public double H, Sx, Sy; public bool Seated; }

        internal static Family FamilyOf(string clip)
        {
            if (clip.StartsWith("laydown")) return new Family { H = LieH, Sx = 0, Sy = LieSy, Seated = true };
            if (clip.StartsWith("perch")) return new Family { H = 1, Sx = -26.0 / 384, Sy = 36.0 / 384, Seated = true };
            return new Family { H = 1.11, Sx = 0, Sy = 0, Seated = false };
        }

        internal static string SheetFor(string clip, int facing, Sheets sheets)
        {
            return facing < 0 && sheets.Has(clip + "_flipped") ? clip + "_flipped" : clip;
        }

        // The box a clip is drawn in, relative to her square's top-left.
        internal static RectangleF Box(string clip, ClipInfo info, double s, int facing)
        {
            Family f = FamilyOf(clip);
            double tall = s * f.H;
            double wide = info != null ? tall * info.Cw / info.Ch : tall * 0.6;
            double sx = (facing < 0 ? -f.Sx : f.Sx) * s;
            return new RectangleF((float)(s / 2 - wide / 2 + sx), (float)(s / 2 - tall / 2 + f.Sy * s), (float)wide, (float)tall);
        }

        internal static PointF HipShare(bool seated, int facing)
        {
            PointF p = seated ? Sit : Stand;
            return new PointF(facing < 0 ? 1 - p.X : p.X, p.Y);
        }

        internal static PointF AnchorFor(double hipX, double hipY, double s, bool seated, int facing)
        {
            PointF h = HipShare(seated, facing);
            return new PointF((float)(hipX - h.X * s), (float)(hipY - h.Y * s));
        }

        // Is x on the ledge hidden under a window above it in z-order?
        internal static bool Covered(Ledge l, double x, List<Ledge> all)
        {
            if (l.Floor) return false;
            foreach (Ledge o in all)
            {
                if (o.Floor || o.Window == l.Window || o.Z >= l.Z) continue;
                if (x >= o.Bounds.Left && x <= o.Bounds.Right && l.Y > o.Bounds.Top && l.Y < o.Bounds.Bottom) return true;
            }
            return false;
        }

        // The ledge she lands on falling from (hx, hy): the nearest below that holds her and isn't covered there; a
        // floor of the screen she's over always catches her.
        internal static Ledge Below(List<Ledge> all, double hx, double hy, double s)
        {
            Ledge best = null, floor = null;
            foreach (Ledge l in all)
            {
                if (l.Floor && hx >= l.X1 && hx <= l.X2) floor = l;
                if (l.Y < hy - 2) continue;
                if (hx < l.X1 + s * 0.15 || hx > l.X2 - s * 0.45) continue;
                if (Covered(l, hx, all)) continue;
                if (best == null || l.Y < best.Y) best = l;
            }
            if (best != null) return best;
            if (floor != null) return floor;
            foreach (Ledge l in all) if (l.Floor) return l;
            return null;
        }

        internal static double ClampX(Ledge l, double x, double s)
        {
            double lo = l.X1 + s * 0.15, hi = l.X2 - s * 0.45;
            return hi < lo ? (l.X1 + l.X2) / 2.0 : Math.Max(lo, Math.Min(hi, x));
        }

        // Room to lie down from hip x: 1 (head to the left, the art as drawn), -1 (mirrored), 0 (no room).
        internal static int LieFacing(Ledge l, double hx, double s)
        {
            double reach = LieReach * s;
            if (hx - l.X1 >= reach) return 1;
            if (l.X2 - hx >= reach) return -1;
            return 0;
        }
    }
}
