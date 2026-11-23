namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>One button of the ribbon: what the page runs (its id), its words, its icon, its tooltip, the reason it
/// does not apply now (greyed out, said as its tooltip, as the classic ribbon does), and whether it is pressed (the
/// compare mode in use).</summary>
public sealed record RibbonTool(
    string Id,
    string Label,
    string Icon,
    string? Title = null,
    string? Disabled = null,
    bool Pressed = false);
