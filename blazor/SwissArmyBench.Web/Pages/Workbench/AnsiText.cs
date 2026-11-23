using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>
/// The terminal's colour codes (ANSI SGR) read into runs of coloured text (the classic workbenchOutputs.ts): the
/// sixteen colours as classes the theme colours, 256 and true colours as a style; bold, dim, italic, underline. A
/// carriage return starts its line over (a progress bar's next state), keeping the colour in effect. Other escapes
/// are dropped.
/// </summary>
public static partial class AnsiText
{
    // The xterm 256-colour cube: six steps a channel, then 24 greys.
    private const int Basic = 16;
    private const int Greys = 232;

    public static IReadOnlyList<AnsiPiece> Pieces(string text)
    {
        var style = new AnsiStyle();
        var lines = text.Replace("\r\n", "\n").Split('\n');
        return lines
            .SelectMany((line, i) => Line(line, style).Concat(i < lines.Length - 1 ? [new AnsiPiece("\n", string.Empty, string.Empty)] : []))
            .ToList();
    }

    private static List<AnsiPiece> Line(string line, AnsiStyle style)
    {
        var parts = new List<AnsiPiece>();
        var at = 0;
        void add(string piece)
        {
            var pieces = piece.Split('\r');
            for (var i = 0; i < pieces.Length; i++)
            {
                if (i > 0)
                {
                    parts.Clear(); // a carriage return: what follows writes over the line
                }
                if (pieces[i].Length > 0)
                {
                    parts.Add(style.Piece(pieces[i]));
                }
            }
        }
        foreach (Match m in Escape().Matches(line))
        {
            add(line[at..m.Index]);
            if (m.Groups[2].Value == "m")
            {
                Apply(style, m.Groups[1].Value);
            }
            at = m.Index + m.Length;
        }
        add(line[at..]);
        return parts;
    }

    private static void Apply(AnsiStyle style, string parameters)
    {
        var codes = parameters.Length == 0 ? [0] : parameters.Split(';').Select(p => int.TryParse(p, out var n) ? n : 0).ToArray();
        for (var i = 0; i < codes.Length; i++)
        {
            var c = codes[i];
            int at(int k) => i + k < codes.Length ? codes[i + k] : 0;
            switch (c)
            {
                case 0: style.Reset(); break;
                case 1: style.Bold = true; break;
                case 2: style.Dim = true; break;
                case 3: style.Italic = true; break;
                case 4: style.Underline = true; break;
                case 22: style.Bold = style.Dim = false; break;
                case 23: style.Italic = false; break;
                case 24: style.Underline = false; break;
                case >= 30 and <= 37: style.Fg = $"c{c - 30}"; break;
                case >= 90 and <= 97: style.Fg = $"c{c - 90 + 8}"; break;
                case 39: style.Fg = null; break;
                case >= 40 and <= 47: style.Bg = $"c{c - 40}"; break;
                case >= 100 and <= 107: style.Bg = $"c{c - 100 + 8}"; break;
                case 49: style.Bg = null; break;
                case 38 or 48 when at(1) == 5:
                    style.Set(c == 38, Xterm(at(2)));
                    i += 2;
                    break;
                case 38 or 48 when at(1) == 2:
                    style.Set(c == 38, $"rgb({at(2)},{at(3)},{at(4)})");
                    i += 4;
                    break;
                default: break;
            }
        }
    }

    private static string Xterm(int n)
    {
        if (n < Basic)
        {
            return $"c{n}";
        }
        if (n >= Greys)
        {
            var v = 8 + (n - Greys) * 10;
            return $"rgb({v},{v},{v})";
        }
        var i = n - Basic;
        static int step(int k) => k == 0 ? 0 : 55 + k * 40;
        return $"rgb({step(i / 36)},{step(i / 6 % 6)},{step(i % 6)})";
    }

    [GeneratedRegex(@"\x1b\[([0-9;?]*)([A-Za-z])|\x1b[()][A-Za-z0-9]|\x1b[=>]")]
    private static partial Regex Escape();
}
