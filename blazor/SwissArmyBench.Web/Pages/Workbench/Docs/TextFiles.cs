namespace SwissArmyBench.Web.Pages.Workbench.Docs;

/// <summary>Which files open as a text document's tab, and what each one's Preview draws: the server's table
/// (domain/text_documents.py KINDS; GET /app/rules says it as data, and tests/test_named_files.py holds this copy
/// to it), the first ending that matches a file's lower-cased name. Markdown opens in its Read view; a .vl.json or
/// .vg.json chart spec is a text document, never a structure's tab.</summary>
public static class TextFiles
{
    public const string Preview = "preview";
    public const string Split = "split";
    public const string Source = "source";

    private static readonly TextFileKind[] _kinds =
    [
        new(".md", "markdown", "markdown", Preview, "markdown"),
        new(".html", "html", "html", Source, "code"),
        new(".htm", "html", "html", Source, "code"),
        new(".svg", "xml", "svg", Source, "chart"),
        new(".mmd", "plaintext", "mermaid", Source, "chart"),
        new(".mermaid", "plaintext", "mermaid", Source, "chart"),
        new(".vl.json", "json", "vega", Source, "chart"),
        new(".vg.json", "json", "vega", Source, "chart"),
        new(".txt", "plaintext", "", Source, "note"),
    ];

    public static IReadOnlyList<string> Views { get; } = [Preview, Split, Source];

    public static IReadOnlyList<TextFileKind> Kinds => _kinds;

    public static TextFileKind? KindOf(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return null;
        }
        var name = path.Replace('\\', '/').Split('/')[^1].ToLowerInvariant();
        return name.StartsWith('.') ? null : _kinds.FirstOrDefault(k => name.EndsWith(k.Ending, StringComparison.Ordinal));
    }

    public static bool IsText(string? path) => KindOf(path) is not null;
}
