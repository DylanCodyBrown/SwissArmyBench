using SwissArmyBench.Web.Api.Catalog;

namespace SwissArmyBench.Web.Pages.Catalog;

/// <summary>
/// A typed search as the same tree, narrowed to what matches (the classic dataBrowse.ts showSearch): a connection's
/// matched tables under it by database and schema, a matched column under its table; a connection matched by its
/// name with all of its tables; the other kinds as their own sections (Open tables, Sandbox, Structures, APIs,
/// Variables, Blades, From the shared catalog).
/// </summary>
public static class CatalogSearchTree
{
    private sealed record Found(SearchResult Table, List<SearchResult> Columns);

    private static readonly (string Kind, string Label)[] _sections =
    [
        ("open", "Open tables"),
        ("sandbox", "Sandbox"),
        ("structures", "Structures"),
        ("apis", "APIs"),
        ("variables", "Variables"),
        ("blades", "Blades"),
        ("shared", "From the shared catalog"),
    ];

    public static BrowseAnswer Of(SearchAnswer answer, BrowseAnswer? browsed)
    {
        IReadOnlyList<SearchResult> OfKind(string kind) => answer.Groups.FirstOrDefault(g => g.Kind == kind)?.Results ?? [];
        var tables = OfKind("tables");
        var columns = OfKind("columns");
        var placed = tables.Concat(columns).Where(InCatalog).ToList();

        // Each connection's tables by their place; a matched column joins its table (made when only a column matched).
        var byConnection = placed
            .GroupBy(r => r.Connection!, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(g => g.Key, g => g
                .GroupBy(r => (r.Place!.Database ?? string.Empty, r.Place.Schema ?? string.Empty, r.Place.Table))
                .Select(t => new Found(
                    t.FirstOrDefault(r => r.Kind == "tables") ?? TableOf(t.First()),
                    [.. t.Where(r => r.Kind == "columns")]))
                .ToList(), StringComparer.OrdinalIgnoreCase);
        var known = (browsed?.Connections ?? []).ToDictionary(c => c.Name, StringComparer.OrdinalIgnoreCase);
        var names = byConnection.Keys.Concat(OfKind("connections").Select(r => r.Name)).Distinct(StringComparer.OrdinalIgnoreCase);
        var connections = names.Select(name =>
        {
            var c = known.GetValueOrDefault(name) ?? new BrowseConnection(name, string.Empty, string.Empty, new BrowseState("loaded"), true, 0, false, false, []);
            // Matched by its name only: all of its tables, as the browse has them.
            return byConnection.TryGetValue(name, out var found)
                ? c with { Groups = GroupsOf(found) }
                : c;
        }).ToList();

        var others = tables.Where(r => !InCatalog(r)).Select(r => (Home: HomeOf(r, "open"), Result: r))
            .Concat(columns.Where(r => !InCatalog(r)).Select(r => (Home: r.Source == "api" ? "apis" : HomeOf(r, "open"), Result: r)))
            .Concat(OfKind("structures").Select(r => (Home: "structures", Result: r)))
            .Concat(OfKind("apis").Select(r => (Home: "apis", Result: r)))
            .Concat(OfKind("variables").Select(r => (Home: "variables", Result: r)))
            .Concat(OfKind("blades").Select(r => (Home: "blades", Result: r)))
            .ToLookup(x => x.Home, x => x.Result);
        var sections = _sections
            .Where(s => others[s.Kind].Any())
            .Select(s => new BrowseSection(s.Kind, s.Label, others[s.Kind].Count(), [.. others[s.Kind]]))
            .ToList();
        return new BrowseAnswer(connections, sections);
    }

    private static bool InCatalog(SearchResult r) => r.Source == "catalog" && r.Connection is not null && r.Place is not null;

    private static string HomeOf(SearchResult r, string other) => r.Source switch
    {
        "shared" => "shared",
        "sandbox" => "sandbox",
        _ => other,
    };

    private static List<BrowseGroup> GroupsOf(List<Found> found) =>
    [
        .. found
            .GroupBy(f => (f.Table.Place?.Database ?? string.Empty, f.Table.Place?.Schema ?? string.Empty))
            .Select(g => new BrowseGroup(g.Key.Item1, g.Key.Item2, g.Count(), [.. g.Select(f => f.Table with { Children = f.Columns })])),
    ];

    // A table known only by a column that matched: made from the column's place, as the classic does.
    private static SearchResult TableOf(SearchResult column)
    {
        var place = column.Place!;
        var sql = column.Sql ?? place.Table;
        return new SearchResult(
            $"tables/{column.Connection}/{string.Join('/', column.Path.SkipLast(1))}/{place.Table}",
            "tables",
            place.Table,
            [.. column.Path.SkipLast(1)],
            column.Connection,
            Icon: "rows",
            Insert: new InsertText($"SELECT * FROM {sql}", $"sab.sql(\"SELECT * FROM {sql}\")"),
            Place: place)
        {
            Source = "catalog",
            Sql = sql,
        };
    }
}
