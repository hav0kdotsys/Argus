using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text.Json;

namespace MiraPet
{
    // One clip's grid (argus/pet/build_sheets.py): its frames laid out in rows of `Cols` cells of Cw x Ch pixels.
    internal sealed class ClipInfo
    {
        public string Name;
        public int Frames, Cols, Rows, Cw, Ch;
        public double Fps;

        public Rectangle Cell(int index)
        {
            index = ((index % Frames) + Frames) % Frames;
            return new Rectangle(index % Cols * Cw, index / Cols * Ch, Cw, Ch);
        }
    }

    // Her sheets from %ARGUS_HOME%\sprites\mira\grid, loaded when first needed and kept only while recently used.
    internal sealed class Sheets
    {
        private const int Keep = 10;
        private readonly string folder;
        private readonly Dictionary<string, ClipInfo> clips = new Dictionary<string, ClipInfo>();
        private readonly Dictionary<string, Bitmap> loaded = new Dictionary<string, Bitmap>();
        private readonly LinkedList<string> recent = new LinkedList<string>();

        internal Sheets(string folder)
        {
            this.folder = folder;
            using (JsonDocument doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "grid.json"))))
                foreach (JsonProperty p in doc.RootElement.GetProperty("clips").EnumerateObject())
                {
                    JsonElement c = p.Value;
                    clips[p.Name] = new ClipInfo
                    {
                        Name = p.Name, Frames = c.GetProperty("frames").GetInt32(), Fps = c.GetProperty("fps").GetDouble(),
                        Cols = c.GetProperty("cols").GetInt32(), Rows = c.GetProperty("rows").GetInt32(),
                        Cw = c.GetProperty("cw").GetInt32(), Ch = c.GetProperty("ch").GetInt32(),
                    };
                }
        }

        internal bool Has(string name) { return name != null && clips.ContainsKey(name); }

        internal ClipInfo Info(string name) { return Has(name) ? clips[name] : null; }

        internal Bitmap Sheet(string name)
        {
            if (!Has(name)) return null;
            if (loaded.TryGetValue(name, out Bitmap bmp))
            {
                recent.Remove(name);
                recent.AddFirst(name);
                return bmp;
            }
            string path = Path.Combine(folder, name + ".png");
            if (!File.Exists(path)) return null;
            using (Bitmap file = new Bitmap(path)) bmp = new Bitmap(file);   // a copy, so the file isn't held open
            loaded[name] = bmp;
            recent.AddFirst(name);
            while (recent.Count > Keep)
            {
                string old = recent.Last.Value;
                recent.RemoveLast();
                loaded[old].Dispose();
                loaded.Remove(old);
            }
            return bmp;
        }
    }
}
