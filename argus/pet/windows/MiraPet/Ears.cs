using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;

namespace MiraPet
{
    // Her ears on winhvk: the beat of whatever is playing, so she dances on it (laphvk's twin is argus-companion's
    // ears.py, the same method). While Windows says something's playing, she listens to the speakers' own mix
    // (WASAPI loopback: what you hear, nothing from the microphone), turns each 10 ms into one loudness step, and
    // keeps a beat lock from the last 8 s of those. Nothing is recorded or kept. beat.json ({"bpm", "beat_at",
    // "at"}, unix seconds) goes to the companion for her other body; this body reads the lock directly.
    internal sealed class Ears : IDisposable
    {
        private const int Fps = 100;
        private const double Window = 8.0, Slowest = 70, Fastest = 180, Latency = 0.06;

        private readonly Func<bool> playing;
        private readonly string beatFile;
        private readonly Thread worker;
        private volatile bool stop;
        private readonly object gate = new object();
        private double bpm, beatAt;              // beat_at: unix seconds

        internal Ears(Func<bool> playing, string companion)
        {
            this.playing = playing;
            beatFile = Path.Combine(companion, "beat.json");
            worker = new Thread(Run) { IsBackground = true, Name = "Mira ears" };
            worker.SetApartmentState(ApartmentState.MTA);
            worker.Start();
        }

        internal static double UnixNow => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;

        internal bool Locked(out double b, out double at)
        {
            lock (gate) { b = bpm; at = beatAt; }
            return b > 0;
        }

        private void Run()
        {
            while (!stop)
            {
                if (!playing()) { Thread.Sleep(2000); continue; }
                try { Listen(); }
                catch (Exception) { Thread.Sleep(5000); }     // no device, or it changed: try again later
                lock (gate) { bpm = 0; beatAt = 0; }
                Write();
            }
        }

        // ---------------------------------------------------------------- WASAPI loopback

        [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] private class MMDeviceEnumerator { }

        [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        private interface IMMDeviceEnumerator
        {
            int EnumAudioEndpoints(int dataFlow, int stateMask, out IntPtr devices);
            int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device);
        }

        [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        private interface IMMDevice
        {
            int Activate(ref Guid iid, int clsCtx, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object iface);
        }

        [ComImport, Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        private interface IAudioClient
        {
            int Initialize(int shareMode, int streamFlags, long bufferDuration, long periodicity, IntPtr format, IntPtr sessionGuid);
            int GetBufferSize(out uint frames);
            int GetStreamLatency(out long latency);
            int GetCurrentPadding(out uint padding);
            int IsFormatSupported(int shareMode, IntPtr format, out IntPtr closest);
            int GetMixFormat(out IntPtr format);
            int GetDevicePeriod(out long defaultPeriod, out long minimumPeriod);
            int Start();
            int Stop();
            int Reset();
            int SetEventHandle(IntPtr handle);
            int GetService(ref Guid iid, [MarshalAs(UnmanagedType.IUnknown)] out object service);
        }

        [ComImport, Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        private interface IAudioCaptureClient
        {
            int GetBuffer(out IntPtr data, out uint frames, out uint flags, out ulong devicePosition, out ulong qpcPosition);
            int ReleaseBuffer(uint frames);
            int GetNextPacketSize(out uint frames);
        }

        private static void Check(int hr) { if (hr < 0) Marshal.ThrowExceptionForHR(hr); }

        private void Listen()
        {
            IMMDeviceEnumerator devices = (IMMDeviceEnumerator)new MMDeviceEnumerator();
            Check(devices.GetDefaultAudioEndpoint(0 /* render */, 1 /* multimedia */, out IMMDevice device));
            Guid audioClientId = typeof(IAudioClient).GUID;
            Check(device.Activate(ref audioClientId, 0x17 /* CLSCTX_ALL */, IntPtr.Zero, out object o));
            IAudioClient client = (IAudioClient)o;
            Check(client.GetMixFormat(out IntPtr format));
            try
            {
                int channels = Marshal.ReadInt16(format, 2);
                int rate = Marshal.ReadInt32(format, 4);
                int bits = Marshal.ReadInt16(format, 14);
                int tag = (ushort)Marshal.ReadInt16(format, 0);
                bool isFloat = tag == 3 || (tag == 0xFFFE && Marshal.ReadInt32(format, 24) == 3);
                if (!(isFloat && bits == 32) && !(!isFloat && bits == 16)) return;    // a mix format she can't read
                Check(client.Initialize(0 /* shared */, 0x00020000 /* loopback */, 10_000_000, 0, format, IntPtr.Zero));
                Guid captureId = typeof(IAudioCaptureClient).GUID;
                Check(client.GetService(ref captureId, out object c));
                IAudioCaptureClient capture = (IAudioCaptureClient)c;
                Check(client.Start());
                try { Hear(capture, channels, rate, isFloat); }
                finally { client.Stop(); Marshal.ReleaseComObject(capture); }
            }
            finally
            {
                Marshal.FreeCoTaskMem(format);
                Marshal.ReleaseComObject(client);
                Marshal.ReleaseComObject(device);
                Marshal.ReleaseComObject(devices);
            }
        }

        private void Hear(IAudioCaptureClient capture, int channels, int rate, bool isFloat)
        {
            int hop = rate / Fps;
            double low = 1 - Math.Exp(-2 * Math.PI * 150 / rate);
            double lp = 0, energy = 0, lowEnergy = 0, level = 0, lowLevel = 0;
            int inHop = 0;
            var onsets = new List<double>();
            int keep = (int)(Window * Fps);
            var lockOn = new Lock();
            double nextRead = UnixNow + 0.5, nextCheck = UnixNow + 2;
            while (!stop)
            {
                Thread.Sleep(20);
                Check(capture.GetNextPacketSize(out uint packet));
                while (packet > 0)
                {
                    Check(capture.GetBuffer(out IntPtr data, out uint frames, out uint flags, out ulong _, out ulong _));
                    bool silent = (flags & 0x2) != 0;
                    for (int f = 0; f < frames; f++)
                    {
                        double v = 0;
                        if (!silent)
                        {
                            for (int ch = 0; ch < channels; ch++)
                            {
                                int at = (f * channels + ch) * (isFloat ? 4 : 2);
                                v += isFloat ? BitConverter.Int32BitsToSingle(Marshal.ReadInt32(data, at)) * 32767.0 : Marshal.ReadInt16(data, at);
                            }
                            v /= channels;
                        }
                        lp += low * (v - lp);
                        energy += v * v;
                        lowEnergy += lp * lp;
                        if (++inHop == hop)
                        {
                            double now = Math.Log(1 + energy / hop / 1e4), nowLow = Math.Log(1 + lowEnergy / hop / 1e4);
                            onsets.Add(Math.Max(0, now - level) + Math.Max(0, nowLow - lowLevel));
                            level = now; lowLevel = nowLow;
                            energy = lowEnergy = 0; inHop = 0;
                        }
                    }
                    Check(capture.ReleaseBuffer(frames));
                    Check(capture.GetNextPacketSize(out packet));
                }
                if (onsets.Count > keep) onsets.RemoveRange(0, onsets.Count - keep);
                double t = UnixNow;
                if (t >= nextRead)
                {
                    nextRead = t + 0.5;
                    (double b, double ago) = Tempo(onsets);
                    lockOn.Take(b, ago, t);
                    lock (gate) { bpm = lockOn.Bpm; beatAt = lockOn.BeatAt; }
                    Write();
                }
                if (t >= nextCheck)
                {
                    nextCheck = t + 2;
                    if (!playing()) return;
                }
            }
        }

        // ---------------------------------------------------------------- the beat (as ears.py)

        internal static (double bpm, double ago) Tempo(List<double> onsets)
        {
            int n = onsets.Count;
            if (n < Fps * 3) return (0, 0);
            double mean = 0;
            foreach (double v in onsets) mean += v;
            mean /= n;
            double[] x = new double[n];
            double zero = 0;
            for (int i = 0; i < n; i++) { x[i] = onsets[i] - mean; zero += x[i] * x[i]; }
            if (zero <= 1e-9) return (0, 0);
            int lo = (int)(Fps * 60 / Fastest), hi = (int)(Fps * 60 / Slowest) + 1;
            var r = new Dictionary<int, double>();
            for (int lag = lo; lag < Math.Min(3 * hi + 3, n - 1); lag++)
            {
                double s = 0;
                for (int i = lag; i < n; i++) s += x[i] * x[i - lag];
                r[lag] = s / zero;
            }
            var scores = new Dictionary<int, double>();
            int best = lo;
            for (int lag = lo; lag <= hi; lag++)
            {
                double pulse = r[lag] + 0.5 * (r.TryGetValue(2 * lag, out double r2) ? r2 : 0) + 0.25 * (r.TryGetValue(3 * lag, out double r3) ? r3 : 0);
                double b = 60.0 * Fps / lag;
                double lean = Math.Log(b / 120.0, 2) / 0.9;
                scores[lag] = pulse * Math.Exp(-0.5 * lean * lean);
                if (scores[lag] > scores[best]) best = lag;
            }
            if (scores[best] < 0.1) return (0, 0);
            double left = scores.TryGetValue(best - 1, out double l) ? l : scores[best];
            double right = scores.TryGetValue(best + 1, out double rr) ? rr : scores[best];
            double bend = left - 2 * scores[best] + right;
            double period = best + (bend < 0 ? 0.5 * (left - right) / bend : 0);
            int whole = (int)Math.Round(period);
            int ago = 0;
            double most = -1;
            for (int offset = 0; offset < whole; offset++)
            {
                double total = 0;
                for (int k = 0; ; k++)
                {
                    int i = n - 1 - offset - (int)Math.Round(k * period);
                    if (i < 0) break;
                    total += onsets[i];
                }
                if (total > most) { most = total; ago = offset; }
            }
            return (60.0 * Fps / period, (double)ago / Fps);
        }

        private sealed class Lock
        {
            internal double Bpm, BeatAt;
            private double pending;
            private int misses;

            private static double Fold(double b)
            {
                while (b >= Fastest) b /= 2;
                while (b < Slowest) b *= 2;
                return b;
            }

            internal void Take(double b, double ago, double now)
            {
                if (b <= 0)
                {
                    if (++misses >= 8) { Bpm = 0; pending = 0; }
                    return;
                }
                misses = 0;
                b = Fold(b);
                double at = now - ago - Latency;
                if (Bpm > 0 && Math.Abs(b / Bpm - 1) < 0.04) { Bpm = Bpm * 0.8 + b * 0.2; BeatAt = at; }
                else if (pending > 0 && Math.Abs(b / pending - 1) < 0.04) { Bpm = b; BeatAt = at; pending = 0; }
                else pending = b;
            }
        }

        private void Write()
        {
            double b, at;
            lock (gate) { b = bpm; at = beatAt; }
            var data = b > 0
                ? new Dictionary<string, object> { ["bpm"] = Math.Round(b, 2), ["beat_at"] = Math.Round(at, 3), ["at"] = UnixNow }
                : new Dictionary<string, object> { ["at"] = 0 };
            try
            {
                string tmp = beatFile + ".tmp";
                File.WriteAllText(tmp, JsonSerializer.Serialize(data));
                File.Move(tmp, beatFile, true);
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }

        public void Dispose() { stop = true; }
    }
}
