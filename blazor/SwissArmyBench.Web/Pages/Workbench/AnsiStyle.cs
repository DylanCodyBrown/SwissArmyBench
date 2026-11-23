namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>The colour codes in effect while a text is read (AnsiText): a colour is "c3" (one of the sixteen, a
/// class) or an rgb(...) colour.</summary>
public sealed class AnsiStyle
{
    public string? Fg { get; set; }

    public string? Bg { get; set; }

    public bool Bold { get; set; }

    public bool Dim { get; set; }

    public bool Italic { get; set; }

    public bool Underline { get; set; }

    public void Reset() => (Fg, Bg, Bold, Dim, Italic, Underline) = (null, null, false, false, false, false);

    public void Set(bool foreground, string colour)
    {
        if (foreground)
        {
            Fg = colour;
        }
        else
        {
            Bg = colour;
        }
    }

    /// <summary>A piece of text as it is drawn now.</summary>
    public AnsiPiece Piece(string text)
    {
        var classes = new[]
        {
            Fg is ['c', ..] ? $"ansi-fg-{Fg[1..]}" : null,
            Bg is ['c', ..] ? $"ansi-bg-{Bg[1..]}" : null,
            Bold ? "ansi-bold" : null,
            Dim ? "ansi-dim" : null,
            Italic ? "ansi-italic" : null,
            Underline ? "ansi-underline" : null,
        };
        var style = string.Concat(
            Fg is ['r', ..] ? $"color:{Fg};" : string.Empty,
            Bg is ['r', ..] ? $"background-color:{Bg};" : string.Empty);
        return new AnsiPiece(text, string.Join(' ', classes.OfType<string>()), style);
    }
}
