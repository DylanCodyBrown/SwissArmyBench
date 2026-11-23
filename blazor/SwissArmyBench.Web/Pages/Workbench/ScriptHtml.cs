using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A script's HTML cells (domain/html_cells.py): `# %% [7] [html] height=320` and the HTML as one string
/// that does nothing; each read into a cell kept by its number, so its design's state stays as the text changes.</summary>
public static partial class ScriptHtml
{
    [GeneratedRegex(@"^#\s*%%\s*\[(\d+)\]\s*\[html\](?:\s+height=(\d+))?", RegexOptions.Multiline)]
    private static partial Regex Marker();

    [GeneratedRegex("^#\\s*%%", RegexOptions.Multiline)]
    private static partial Regex AnyMarker();

    [GeneratedRegex("^\\s*[rRbBuU]?(\"\"\"|''')(?<html>.*?)\\1", RegexOptions.Singleline)]
    private static partial Regex Body();

    public static IReadOnlyList<CellModel> Cells(string text, IReadOnlyDictionary<int, CellModel> kept) =>
        Marker().Matches(text)
            .Select(m =>
            {
                var start = m.Index + m.Length;
                var next = AnyMarker().Match(text, start);
                var body = text[start..(next.Success ? next.Index : text.Length)];
                var html = Body().Match(body) is { Success: true } found ? found.Groups["html"].Value.Trim() : body.Trim();
                var number = int.Parse(m.Groups[1].Value, System.Globalization.CultureInfo.InvariantCulture);
                var cell = kept.GetValueOrDefault(number) ?? new CellModel { Kind = "html", Number = number };
                cell.Source = html;
                cell.Height = m.Groups[2].Success ? int.Parse(m.Groups[2].Value, System.Globalization.CultureInfo.InvariantCulture) : cell.Height;
                return cell;
            })
            .ToList();
}
