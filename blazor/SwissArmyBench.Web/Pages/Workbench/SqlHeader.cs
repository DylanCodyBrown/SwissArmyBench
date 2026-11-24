using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>
/// A .sql file's header line, the connection it runs on (domain/sql_files.py's rule, read and written the same way):
/// `-- connection: &lt;name&gt;` among the file's first comment lines; none is DuckDB over the open tables. The
/// dropdown beside Run file shows it and writes it, so the file reopens on the same connection.
/// </summary>
public static partial class SqlHeader
{
    /// <summary>The connection the header names; null: the open tables (DuckDB).</summary>
    public static string? Of(string text)
    {
        var lines = text.Replace("\r\n", "\n", StringComparison.Ordinal).Split('\n');
        return HeaderIndex(lines) is { } at && Header().Match(lines[at]) is { Success: true } found && found.Groups[1].Value.Trim() is { Length: > 0 } name
            ? name
            : null;
    }

    /// <summary>The text with its header naming the connection (put first when there is none), or without one
    /// (null or blank: the open tables). The file's line ends are kept.</summary>
    public static string With(string text, string? connection)
    {
        var end = text.Contains("\r\n", StringComparison.Ordinal) ? "\r\n" : "\n";
        var lines = text.Split(end).ToList();
        var header = connection is { } name && name.Trim().Length > 0 ? $"-- connection: {name.Trim()}" : null;
        if (HeaderIndex(lines) is { } at)
        {
            if (header is null)
            {
                lines.RemoveAt(at);
            }
            else
            {
                lines[at] = header;
            }
            return string.Join(end, lines);
        }
        return header is null ? text : $"{header}{end}{text}";
    }

    /// <summary>The table a run makes: the file's name without .sql, other characters as _ (orders_by_month).</summary>
    public static string TableOf(string? path)
    {
        if (path is null || path.Trim().Length == 0)
        {
            return "query";
        }
        var name = FilePaths.Name(path);
        var stem = name.EndsWith(".sql", StringComparison.OrdinalIgnoreCase) ? name[..^4] : name;
        var cleaned = NotTablePart().Replace(stem, "_").Trim('_');
        return cleaned.Length == 0 ? "query" : cleaned.Length > MaxTable ? cleaned[..MaxTable] : cleaned;
    }

    private const int MaxTable = 64;

    private static int? HeaderIndex(IReadOnlyList<string> lines)
    {
        for (var i = 0; i < lines.Count; i++)
        {
            if (!Comment().IsMatch(lines[i]))
            {
                return null;
            }
            if (Header().IsMatch(lines[i]))
            {
                return i;
            }
        }
        return null;
    }

    [GeneratedRegex(@"^\s*--\s*connection\s*:\s*(.*?)\s*$", RegexOptions.IgnoreCase)]
    private static partial Regex Header();

    [GeneratedRegex(@"^\s*(--.*)?$")]
    private static partial Regex Comment();

    [GeneratedRegex("[^A-Za-z0-9_-]+")]
    private static partial Regex NotTablePart();
}
