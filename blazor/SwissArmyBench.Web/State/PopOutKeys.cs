using System.Web;

namespace SwissArmyBench.Web.State;

/// <summary>
/// What an address of this app shows, as pop-out keys (domain/pop_outs.py): its page (page:connections; Home's
/// page:home; the old grids as tables), the table in front of the Tables page (table:&lt;grid&gt;) and the document
/// in front of the Notebooks or Scripts page (doc:&lt;path&gt;).
/// </summary>
public static class PopOutKeys
{
    public const string Page = "page";
    public const string Table = "table";
    public const string Document = "doc";

    private const string Home = "home";
    private const string Tables = "tables";
    private const string OldTables = "grids";

    /// <summary>The kind of window an address makes: its first word.</summary>
    public static string KindOf(string relativePath)
    {
        var first = relativePath.Split('?', '#')[0].Split('/')[0];
        return first.Length == 0 ? Home : first == OldTables ? Tables : first;
    }

    public static string PageKey(string relativePath) => $"{Page}:{KindOf(relativePath)}";

    public static string TableKey(string grid) => $"{Table}:{grid}";

    public static string DocumentKey(string path) => $"{Document}:{path}";

    /// <summary>Every key the address shows: its page, then its table or document when it names one.</summary>
    public static IReadOnlyList<string> Of(string relativePath)
    {
        var kind = KindOf(relativePath);
        List<string> keys = [$"{Page}:{kind}"];
        var query = HttpUtility.ParseQueryString(relativePath.Split('#')[0].Split('?', 2).ElementAtOrDefault(1) ?? string.Empty);
        if (kind == Tables && query["grid"] is { Length: > 0 } grid)
        {
            keys.Add(TableKey(grid));
        }
        if (kind is "notebooks" or "scripts" && query["path"] is { Length: > 0 } path)
        {
            keys.Add(DocumentKey(path));
        }
        return keys;
    }
}
