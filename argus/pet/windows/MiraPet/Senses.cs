using System;
using System.Threading;
using System.Threading.Tasks;
using Windows.Media.Control;

namespace MiraPet
{
    // What's playing, from Windows' media session (Spotify, browsers, MusicBee... whatever shows in the volume
    // flyout), and its transport for the mini player. Polled on a background task so a slow app never stalls her.
    internal sealed class Senses : IDisposable
    {
        internal sealed class NowPlaying
        {
            public string Title = "", Artist = "", App = "";
            public bool Playing, CanSeek;
            public TimeSpan Position, Length;
            public DateTimeOffset Read;     // when Position was true (it advances by itself while playing)
        }

        private readonly CancellationTokenSource stop = new CancellationTokenSource();
        private volatile NowPlaying now;
        private GlobalSystemMediaTransportControlsSession session;

        internal bool Playing => now?.Playing ?? false;
        internal NowPlaying Now => now;
        internal string Track
        {
            get
            {
                NowPlaying n = now;
                if (n == null || n.Title.Length == 0) return "";
                return (n.Artist.Length == 0 ? n.Title : n.Artist + " - " + n.Title) + (n.Playing ? " [Playing]" : " [Paused]");
            }
        }

        internal Senses()
        {
            Task.Run(Watch);
        }

        private async Task Watch()
        {
            GlobalSystemMediaTransportControlsSessionManager manager = null;
            while (!stop.IsCancellationRequested)
            {
                try
                {
                    manager ??= await GlobalSystemMediaTransportControlsSessionManager.RequestAsync();
                    GlobalSystemMediaTransportControlsSession s = manager.GetCurrentSession();
                    session = s;
                    if (s == null) now = null;
                    else
                    {
                        GlobalSystemMediaTransportControlsSessionPlaybackInfo info = s.GetPlaybackInfo();
                        GlobalSystemMediaTransportControlsSessionMediaProperties media = await s.TryGetMediaPropertiesAsync();
                        GlobalSystemMediaTransportControlsSessionTimelineProperties time = s.GetTimelineProperties();
                        now = new NowPlaying
                        {
                            Title = media?.Title ?? "", Artist = media?.Artist ?? "", App = s.SourceAppUserModelId ?? "",
                            Playing = info.PlaybackStatus == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing,
                            CanSeek = info.Controls.IsPlaybackPositionEnabled,
                            Position = time.Position, Length = time.EndTime - time.StartTime, Read = time.LastUpdatedTime,
                        };
                    }
                }
                catch (Exception) { now = null; manager = null; }
                try { await Task.Delay(1000, stop.Token); } catch (TaskCanceledException) { break; }
            }
        }

        // The mini player's buttons, sent to whichever app is playing.
        internal void PlayPause() { Try(s => s.TryTogglePlayPauseAsync().AsTask()); }
        internal void Next() { Try(s => s.TrySkipNextAsync().AsTask()); }
        internal void Previous() { Try(s => s.TrySkipPreviousAsync().AsTask()); }
        internal void Seek(TimeSpan to) { Try(s => s.TryChangePlaybackPositionAsync(to.Ticks).AsTask()); }

        private void Try(Func<GlobalSystemMediaTransportControlsSession, Task<bool>> act)
        {
            GlobalSystemMediaTransportControlsSession s = session;
            if (s == null) return;
            Task.Run(async () => { try { await act(s); } catch (Exception) { } });
        }

        public void Dispose() { stop.Cancel(); }
    }
}
