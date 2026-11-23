using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids.Tabs;

/// <summary>
/// The tab row's rules (the classic panes.ts): the order the user dragged the tabs into (remembered), each table's
/// tabs together under its connection once any connection's table is open, a tab's words ("orders · 2" for a second
/// grid on one table), and moving a tab or a whole group. Pure: the page keeps the order and remembers it.
/// </summary>
public static class TabOrder
{
    private static readonly IReadOnlyDictionary<string, string> _kindWords = new Dictionary<string, string>
    {
        ["file"] = "Files",
        ["python"] = "Python",
        ["paste"] = "Pasted",
        ["query"] = "Queries",
        ["unknown"] = "Other",
    };

    public static string GroupKey(GridListItem tab)
    {
        if (tab.Origin?.Connection is { Length: > 0 } connection)
        {
            return $"c:{connection.ToLowerInvariant()}";
        }
        var kind = tab.Origin?.Kind ?? "unknown";
        return $"k:{(kind == "dropped" ? "file" : kind)}";
    }

    /// <summary>The open grids in the remembered order (new ones at the end), each group's tabs together.</summary>
    public static IReadOnlyList<string> Normalize(IReadOnlyList<GridListItem> open, IReadOnlyList<string> remembered)
    {
        var ids = open.Select(t => t.Grid).ToHashSet();
        var ordered = remembered
            .Where(ids.Contains)
            .Concat(open.Select(t => t.Grid).Where(id => !remembered.Contains(id)))
            .ToList();
        var byId = open.ToDictionary(t => t.Grid);
        if (!ordered.Any(id => GroupKey(byId[id]).StartsWith("c:", StringComparison.Ordinal)))
        {
            return ordered;
        }
        // GroupBy keeps the groups in the order of their first tab, and each group's tabs in order.
        return ordered
            .GroupBy(id => GroupKey(byId[id]))
            .SelectMany(g => g)
            .ToList();
    }

    /// <summary>The row's groups, in order. With no connection's table open, one group with no head.</summary>
    public static IReadOnlyList<TabGroup> Groups(IReadOnlyList<GridListItem> open, IReadOnlyList<string> order)
    {
        var byId = open.ToDictionary(t => t.Grid);
        var tabs = order
            .Where(byId.ContainsKey)
            .Select(id => byId[id])
            .ToList();
        if (!tabs.Any(t => GroupKey(t).StartsWith("c:", StringComparison.Ordinal)))
        {
            return [new TabGroup(string.Empty, null, null, tabs)];
        }
        return tabs
            .GroupBy(GroupKey)
            .Select(g => new TabGroup(g.Key, GroupName(g.Key, g.First()), g.First().Origin?.Connection, g.ToList()))
            .ToList();
    }

    /// <summary>A tab's words: its table, "· 2" for the second grid on one table (in tab order).</summary>
    public static string Label(GridListItem tab, IReadOnlyList<GridListItem> open, IReadOnlyList<string> order)
    {
        var same = order
            .Select(id => open.FirstOrDefault(t => t.Grid == id))
            .Where(t => t is not null && t.Dataset == tab.Dataset)
            .Select(t => t!.Grid)
            .ToList();
        return same.Count > 1 ? $"{tab.Dataset} · {same.IndexOf(tab.Grid) + 1}" : tab.Dataset;
    }

    /// <summary>`moved` put before `before` (null: at the end).</summary>
    public static IReadOnlyList<string> Move(IReadOnlyList<string> order, string moved, string? before)
    {
        if (moved == before)
        {
            return order;
        }
        var rest = order.Where(id => id != moved).ToList();
        var at = before is null ? -1 : rest.IndexOf(before);
        rest.Insert(at < 0 ? rest.Count : at, moved);
        return rest;
    }

    /// <summary>A whole group's tabs put before `before` (a tab of another group; null: at the end).</summary>
    public static IReadOnlyList<string> MoveGroup(IReadOnlyList<string> order, IReadOnlyList<GridListItem> open, string key, string? before)
    {
        var byId = open.ToDictionary(t => t.Grid);
        var mine = order.Where(id => byId.ContainsKey(id) && GroupKey(byId[id]) == key).ToList();
        if (before is not null && mine.Contains(before))
        {
            return order;
        }
        var rest = order.Where(id => !mine.Contains(id)).ToList();
        var at = before is null ? -1 : rest.IndexOf(before);
        rest.InsertRange(at < 0 ? rest.Count : at, mine);
        return rest;
    }

    private static string GroupName(string key, GridListItem first) =>
        key.StartsWith("c:", StringComparison.Ordinal)
            ? first.Origin?.Connection ?? key[2..]
            : _kindWords.GetValueOrDefault(key[2..], "Other");
}
