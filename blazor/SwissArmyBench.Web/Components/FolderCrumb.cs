using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Components;

/// <summary>One part of a folder's breadcrumb and the path it opens (the classic fileChooser.ts crumbs).</summary>
public sealed partial record FolderCrumb(string Name, string Path)
{
    /// <summary>A folder's path as its breadcrumb's parts: a drive (C:\), a share (\\server\share) or / first.</summary>
    public static IReadOnlyList<FolderCrumb> Of(string path, string separator = "/")
    {
        var windows = separator == "\\" || DrivePath().IsMatch(path) || path.StartsWith(@"\\", StringComparison.Ordinal);
        var sep = windows ? "\\" : "/";
        var parts = Parts().Split(path).Where(p => p.Length > 0).ToList();
        if (parts.Count == 0)
        {
            return [new(sep, sep)];
        }
        string at;
        if (windows && DriveOnly().IsMatch(parts[0]))
        {
            at = $"{parts[0]}\\";
            parts.RemoveAt(0);
        }
        else if (windows && path.StartsWith(@"\\", StringComparison.Ordinal))
        {
            at = $@"\\{parts[0]}\{(parts.Count > 1 ? parts[1] : string.Empty)}";
            parts.RemoveRange(0, Math.Min(2, parts.Count));
        }
        else
        {
            at = "/";
        }
        var first = new FolderCrumb(at, at);
        // Each part's path is the one before it and the part: a running fold, kept as the list of crumbs.
        return parts.Aggregate(
            new List<FolderCrumb> { first },
            (made, part) =>
            {
                var before = made[^1].Path;
                made.Add(new(part, before.EndsWith(sep, StringComparison.Ordinal) ? $"{before}{part}" : $"{before}{sep}{part}"));
                return made;
            });
    }

    [GeneratedRegex(@"^[A-Za-z]:[\\/]")]
    private static partial Regex DrivePath();

    [GeneratedRegex(@"^[A-Za-z]:$")]
    private static partial Regex DriveOnly();

    [GeneratedRegex(@"[\\/]+")]
    private static partial Regex Parts();
}
