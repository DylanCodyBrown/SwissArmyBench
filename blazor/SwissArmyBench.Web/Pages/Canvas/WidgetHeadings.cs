using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>Widget starter packs in the lists (the classic widgetPacks.ts): a prebuilt widget that names a pack shows
/// under that pack's heading, the rest under their group; the open project's own under "This project", then the
/// library's under "Library".</summary>
public static class WidgetHeadings
{
    public static string Of(WidgetEntry widget) =>
        widget.Prebuilt ? (string.IsNullOrEmpty(widget.Pack) ? widget.Group : widget.Pack) : widget.Where == "project" ? "This project" : "Library";

    /// <summary>A pack's description (a line under its heading), else empty.</summary>
    public static string Description(WidgetEntry widget) =>
        widget.Prebuilt && !string.IsNullOrEmpty(widget.Pack) ? widget.PackDescription : string.Empty;

    /// <summary>Whether a widget's words hold every word of the search (in any case).</summary>
    public static bool Matches(WidgetEntry widget, string query, bool withTags = true)
    {
        var words = query.ToLowerInvariant().Split(' ', StringSplitOptions.RemoveEmptyEntries);
        var text = $"{widget.Name} {widget.Description} {widget.Group} {widget.Pack} {(withTags ? string.Join(' ', widget.Tags) : string.Empty)}".ToLowerInvariant();
        return words.All(text.Contains);
    }

    /// <summary>Yours first, then the prebuilt ones in the server's order (the starter packs, then by group).</summary>
    public static IEnumerable<WidgetEntry> Ordered(IEnumerable<WidgetEntry> widgets) => widgets.OrderBy(w => w.Prebuilt);
}
