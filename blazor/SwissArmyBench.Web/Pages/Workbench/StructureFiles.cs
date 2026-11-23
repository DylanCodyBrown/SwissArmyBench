namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>Which files open as a structure's tab beside the code (domain/workbench_pages.py is_structure_path): a
/// .json, .yaml, .yml, .xml or .toml file, but not an app's canvas, a workbook design, an old app canvas, a hidden
/// file, nor anything in a project's .sab/ folder. It opens on the page it was opened from.</summary>
public static class StructureFiles
{
    private static readonly string[] _suffixes = [".json", ".yaml", ".yml", ".xml", ".toml"];
    private static readonly string[] _notStructures = [".canvas.json", ".design.json", ".stapp.json"];

    public static bool IsStructure(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return false;
        }
        var parts = path.Replace('\\', '/').Split('/');
        var name = parts[^1].ToLowerInvariant();
        return !parts[..^1].Contains(".sab")
            && _suffixes.Any(s => name.EndsWith(s, StringComparison.Ordinal))
            && !_notStructures.Any(s => name.EndsWith(s, StringComparison.Ordinal))
            && !name.StartsWith('.');
    }
}
