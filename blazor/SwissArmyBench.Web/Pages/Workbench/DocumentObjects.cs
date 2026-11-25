using System.Text.RegularExpressions;

using SwissArmyBench.Web.Api.Collaboration;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>An open document as the objects a note can name (State/PageObjects): a notebook and its cells by number
/// and name (else its first line), a script or .sql file and its top-level functions and classes.</summary>
public static partial class DocumentObjects
{
    private const int MostCells = 200;
    private const int ShortLine = 32;

    public static IReadOnlyList<CollabReference> Of(OpenDocument? doc)
    {
        if (doc?.Path is not { } path)
        {
            return [];
        }
        var name = FilePaths.Name(path);
        if (doc.IsNotebook)
        {
            var cells = (doc.Notebook?.Cells ?? [])
                .Where(c => c.Number is not null)
                .Take(MostCells)
                .Select(c => new CollabReference("cell", path, $"{c.Number}", $"{name} cell {c.Number}{Label(c.Name, c.Source)}"));
            return [new CollabReference("notebook", path, string.Empty, name), .. cells];
        }
        var sql = path.EndsWith(".sql", StringComparison.OrdinalIgnoreCase);
        var functions = sql
            ? []
            : Definition().Matches(doc.ScriptText).Select(m => m.Groups[1].Value).Distinct()
                .Select(f => new CollabReference("function", path, f, $"{name} {f}()"));
        return [new CollabReference(sql ? "sql" : "script", path, string.Empty, name), .. functions];
    }

    private static string Label(string? named, string source)
    {
        var first = named is { Length: > 0 } ? named : source.Split('\n').Select(l => l.Trim()).FirstOrDefault(l => l.Length > 0) ?? string.Empty;
        return first.Length == 0 ? string.Empty : $" · {(first.Length > ShortLine ? first[..ShortLine] + "…" : first)}";
    }

    [GeneratedRegex(@"^(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)", RegexOptions.Multiline)]
    private static partial Regex Definition();
}
