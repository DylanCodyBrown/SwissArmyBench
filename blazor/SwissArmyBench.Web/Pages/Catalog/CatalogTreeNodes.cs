using System.Globalization;

using SwissArmyBench.Web.Api.Catalog;

namespace SwissArmyBench.Web.Pages.Catalog;

/// <summary>The browse answer as the tree's nodes (the classic dataBrowse.ts showBrowse): each connection with its
/// groups (one unnamed group's tables straight under it), then the sections, each table with its columns.</summary>
public static class CatalogTreeNodes
{
    private static readonly Dictionary<string, string> _sectionIcons = new()
    {
        ["open"] = "grids",
        ["structures"] = "structures",
        ["apis"] = "apis",
        ["blades"] = "blade",
        ["variables"] = "variables",
        ["connections"] = "plug",
        ["shared"] = "folder",
    };

    public static List<TreeNode> Of(BrowseAnswer answer) =>
    [
        .. answer.Connections.Select(c => Connection(c, answer.Connections.Count == 1)),
        .. answer.Sections.Select(s => new TreeNode
        {
            Key = $"section/{s.Kind}",
            Label = s.Label,
            Icon = _sectionIcons.GetValueOrDefault(s.Kind, "rows"),
            Kind = "section",
            Note = s.Items.Count.ToString(CultureInfo.InvariantCulture),
            Children = [.. s.Items.Select(Table)],
            OpenAtFirst = true,
        }),
    ];

    /// <summary>A connection's state in words: Needs a password, Loading its tables…, its count, Not loaded.</summary>
    public static string StateWords(BrowseConnection c) => c.NeedsPassword
        ? "Needs a password"
        : c.State.State switch
        {
            "loading" or "waiting" => "Loading its tables…",
            "failed" => "Its tables did not load",
            _ => c.Loaded ? $"{c.Count.ToString("N0", CultureInfo.InvariantCulture)} table{(c.Count == 1 ? string.Empty : "s")}" : "Not loaded",
        };

    private static TreeNode Connection(BrowseConnection c, bool open)
    {
        List<TreeNode> groups = c.Groups is [{ Schema: "", Database: "" } only]
            ? [.. only.Tables.Select(Table)]
            : [.. c.Groups.Select(g => new TreeNode
            {
                Key = $"group/{c.Name}/{g.Database}/{g.Schema}",
                Label = g.Schema is { Length: > 0 } ? g.Schema : g.Database is { Length: > 0 } ? g.Database : c.Name,
                Icon = c.TablesKind == "powerbi" ? "diagram" : "folder",
                Kind = "group",
                Connection = c,
                Group = g,
                Note = g.Count.ToString(CultureInfo.InvariantCulture),
                Children = [.. g.Tables.Select(Table)],
                OpenAtFirst = c.Groups.Count == 1,
            })];
        return new TreeNode
        {
            Key = $"connection/{c.Name}",
            Label = c.Name,
            Icon = "plug",
            Kind = "connection",
            Connection = c,
            Note = c.Type,
            Status = StateWords(c),
            Children = groups,
            OpenAtFirst = open,
        };
    }

    private static TreeNode Table(SearchResult r)
    {
        var catalog = r.Source == "catalog";
        var kids = r.Children ?? [];
        return new TreeNode
        {
            Key = r.Key,
            Label = r.Name,
            Icon = r.Source == "grid" ? "grids" : r.Kind switch { "structures" => "json", "apis" => "link", "blades" => "blade", _ => "rows" },
            Kind = r.Kind is "tables" or "apis" ? "table" : "item",
            Result = r,
            Note = r.Kind == "structures" && r.Pointer is { } pointer && pointer != "$" ? pointer : r.Detail,
            Children = kids.Count > 0 ? [.. kids.Select(k => k.Kind == "columns" ? Column(r.Key, k) : Table(k))] : catalog ? [] : null,
            Lazy = catalog,
        };
    }

    public static TreeNode Column(string parent, SearchResult r) => new()
    {
        Key = $"{parent}/{r.Name}",
        Label = r.Name,
        Icon = "columns",
        Kind = "column",
        Type = r.Type,
        Result = r,
    };

    /// <summary>A connection's table's columns, read for the tree (no result of their own: Copy name).</summary>
    public static TreeNode Column(string parent, DetailColumn c) => Column(parent, new SearchResult($"{parent}/{c.Name}", "columns", c.Name, []) { Type = c.Type });
}
