using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A script's numbered cells (`# %% [7]` markers, the classic script outline): which cell a line is in, and
/// the line a cell starts on.</summary>
public static partial class ScriptCells
{
    [GeneratedRegex(@"^#\s*%%\s*\[(\d+)\]")]
    private static partial Regex Marker();

    /// <summary>The number of the cell the 1-based line is in: the nearest marker at or above it.</summary>
    public static int? CellAt(string text, int line) =>
        text.Split('\n')
            .Take(line)
            .Select(l => Marker().Match(l.TrimStart()))
            .LastOrDefault(m => m.Success) is { } found && int.TryParse(found.Groups[1].Value, out var number)
            ? number
            : null;

    /// <summary>The 1-based line cell `number`'s marker is on.</summary>
    public static int? LineOf(string text, int number) =>
        text.Split('\n')
            .Select((l, i) => (Match: Marker().Match(l.TrimStart()), Line: i + 1))
            .FirstOrDefault(m => m.Match.Success && m.Match.Groups[1].Value == number.ToString(System.Globalization.CultureInfo.InvariantCulture))
            .Line is var at and > 0 ? at : null;
}
