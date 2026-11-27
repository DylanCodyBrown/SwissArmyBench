namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>Where an open file is after a module or a package moved (the code_file_moved notice).</summary>
public static class MovedFiles
{
    /// <summary>
    /// The path of <paramref name="path"/> now that <paramref name="from"/> (a file, or a folder: a package) is at
    /// <paramref name="to"/>: its new path; an empty text when it was deleted (no <paramref name="to"/>); null when
    /// the move does not touch it. Either separator, letters in any case.
    /// </summary>
    public static string? Follow(string path, string from, string? to)
    {
        var (file, moved) = (Plain(path), Plain(from));
        if (moved.Length == 0)
        {
            return null;
        }
        var same = string.Equals(file, moved, StringComparison.OrdinalIgnoreCase);
        var inside = file.StartsWith(moved + "/", StringComparison.OrdinalIgnoreCase);
        if (!same && !inside)
        {
            return null;
        }
        if (to is null)
        {
            return string.Empty;
        }
        return same ? to : Plain(to) + file[moved.Length..];
    }

    private static string Plain(string path) => path.Replace('\\', '/').TrimEnd('/');
}
