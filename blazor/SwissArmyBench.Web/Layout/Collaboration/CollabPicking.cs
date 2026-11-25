using SwissArmyBench.Web.Api.Collaboration;

namespace SwissArmyBench.Web.Layout.Collaboration;

/// <summary>
/// The composer's `@` list in the owner's order (2026-11-25): the objects on the page you are looking at first (the
/// page's own list, then what the server knows of it), then people (teammates seen in the notes, and you), then the
/// rest of the project; each part filtered by what is typed, each object once.
/// </summary>
public static class CollabPicking
{
    public const string OnThisPage = "On this page";
    public const string People = "People";
    public const string InTheProject = "In the project";
    public const int MostPicks = 14;
    private const int MostOnPage = 8;

    public static IReadOnlyList<CollabPick> Of(IReadOnlyList<CollabReference> page, CollabPicks found, string typed)
    {
        var words = typed.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        bool Fits(CollabReference r) => words.All(w => $"{r.Text} {r.Path} {r.Kind}".Contains(w, StringComparison.OrdinalIgnoreCase));
        var here = page.Where(Fits)
            .Concat(found.Page ?? [])
            .DistinctBy(Key)
            .Take(MostOnPage)
            .ToList();
        var seen = here.Select(Key).ToHashSet(StringComparer.Ordinal);
        var people = found.People.Select(p => new CollabPick(p.Name, $"@{p.Login}", $"@{p.Login} ", "user", People));
        var rest = found.Objects.Where(o => !seen.Contains(Key(o)) && !here.Any(h => Same(h, o)))
            .Select(o => Pick(o, InTheProject));
        return here.Select(o => Pick(o, OnThisPage)).Concat(people).Concat(rest).Take(MostPicks).ToList();
    }

    /// <summary>A reference as a message writes it: [@data.ipynb cell 7](sab:cell/data.ipynb#7).</summary>
    public static string LinkOf(CollabReference reference)
    {
        var place = Uri.EscapeDataString(reference.Path).Replace("%2F", "/", StringComparison.Ordinal);
        var anchor = string.IsNullOrEmpty(reference.Id) ? string.Empty : $"#{Uri.EscapeDataString(reference.Id)}";
        var shown = reference.Text.Replace(']', ')').Replace('\n', ' ');
        return $"[@{shown}](sab:{reference.Kind}/{place}{anchor})";
    }

    public static string IconOf(string kind) => kind switch
    {
        "cell" or "notebook" => "notebook",
        "script" or "function" => "code",
        "sql" => "sql",
        "table" => "table",
        "column" => "columns",
        "connection" => "plug",
        "endpoint" => "apis",
        "widget" => "page",
        "analysis" => "chart",
        _ => "link",
    };

    private static CollabPick Pick(CollabReference o, string section) =>
        new(o.Text, o.Kind, $"{o.Link ?? LinkOf(o)} ", IconOf(o.Kind), section);

    private static string Key(CollabReference r) => $"{r.Kind}:{r.Path}#{r.Id}";

    // The page names a file by its whole path, the server by its place in the project: one object either way.
    private static bool Same(CollabReference page, CollabReference other) =>
        page.Kind == other.Kind && page.Id == other.Id
        && (page.Path == other.Path || page.Path.Replace('\\', '/').EndsWith($"/{other.Path}", StringComparison.Ordinal));
}
