namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>Every widget the lists show (GET /streamlit/widgets): the project's, the library's and the prebuilt ones.</summary>
public sealed record WidgetListing
{
    public IReadOnlyList<WidgetEntry> Widgets { get; init; } = [];

    public string? ProjectFolder { get; init; }
}
