namespace SwissArmyBench.Web;

/// <summary>
/// A path's parts as the user's computer writes it. The app runs in the browser, where .NET follows Linux's rules
/// and does not take <c>\</c> as a folder separator, so <see cref="System.IO.Path"/> would hand back a whole Windows
/// path as its file name. These split on both <c>\</c> and <c>/</c> (the owner's screenshot, 2026-11-23: a script's
/// tab named <c>C:\Repos\...\edp.blade.py</c>).
/// </summary>
public static class FilePaths
{
    private static readonly char[] _separators = ['\\', '/'];

    /// <summary>The last part: <c>C:\Repos\edp.blade.py</c> is <c>edp.blade.py</c>.</summary>
    public static string Name(string? path)
    {
        var trimmed = (path ?? string.Empty).TrimEnd(_separators);
        return trimmed[(trimmed.LastIndexOfAny(_separators) + 1)..];
    }

    /// <summary>The folder holding it (<c>C:\Repos</c>; a drive's own root keeps its separator: <c>C:\</c>), or
    /// null when the path names no folder.</summary>
    public static string? Folder(string? path)
    {
        var trimmed = (path ?? string.Empty).TrimEnd(_separators);
        var at = trimmed.LastIndexOfAny(_separators);
        if (at < 0)
        {
            return null;
        }
        var folder = trimmed[..at];
        return folder.Length == 0 || folder.EndsWith(':') ? trimmed[..(at + 1)] : folder;
    }

    /// <summary>The name without its last extension: <c>orders.csv</c> is <c>orders</c>.</summary>
    public static string Stem(string? path)
    {
        var name = Name(path);
        var dot = name.LastIndexOf('.');
        return dot > 0 ? name[..dot] : name;
    }

    /// <summary>The path's last <paramref name="parts"/> parts behind an ellipsis, for a place too narrow for the
    /// whole of it: <c>/home/me/work/projects/sales</c> with 2 is <c>…/projects/sales</c>. A path that short
    /// already is given as it is. The whole path stays the caller's title and what is copied.</summary>
    public static string Short(string? path, int parts)
    {
        var whole = path ?? string.Empty;
        var separator = whole.Contains('\\') && !whole.Contains('/') ? '\\' : '/';
        var names = whole.Split(_separators, StringSplitOptions.RemoveEmptyEntries);
        return names.Length <= parts ? whole : $"…{separator}{string.Join(separator, names[^parts..])}";
    }
}
