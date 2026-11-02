using System;
using System.Threading;
using System.Threading.Tasks;
using Windows.Media.Control;

namespace MiraPet
{
    // What's playing, from Windows' media session (Spotify, browsers, MusicBee... whatever shows in the volume
    // flyout). Polled on a background task so a slow app never stalls her frames.
    internal sealed class Senses : IDisposable
    {
        private readonly CancellationTokenSource stop = new CancellationTokenSource();
        private volatile bool playing;
        private volatile string track = "";

        internal bool Playing => playing;
        internal string Track => track;

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
                    GlobalSystemMediaTransportControlsSession session = manager.GetCurrentSession();
                    if (session == null) { playing = false; track = ""; }
                    else
                    {
                        GlobalSystemMediaTransportControlsSessionPlaybackInfo info = session.GetPlaybackInfo();
                        bool on = info.PlaybackStatus == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing;
                        GlobalSystemMediaTransportControlsSessionMediaProperties media = await session.TryGetMediaPropertiesAsync();
                        string what = media == null ? "" : (string.IsNullOrEmpty(media.Artist) ? media.Title : media.Artist + " - " + media.Title);
                        playing = on;
                        track = string.IsNullOrEmpty(what) ? "" : what + (on ? " [Playing]" : " [Paused]");
                    }
                }
                catch (Exception) { playing = false; manager = null; }
                try { await Task.Delay(2000, stop.Token); } catch (TaskCanceledException) { break; }
            }
        }

        public void Dispose() { stop.Cancel(); }
    }
}
