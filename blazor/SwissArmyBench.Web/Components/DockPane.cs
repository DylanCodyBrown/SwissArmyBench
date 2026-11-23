using Microsoft.AspNetCore.Components;

namespace SwissArmyBench.Web.Components;

/// <summary>One pane a PaneDock holds: its name, its words, what it shows, and any buttons of its own beside
/// its header's.</summary>
/// <param name="Id">Its name in the layout ("properties").</param>
/// <param name="Label">Its heading and accessible name ("Properties").</param>
/// <param name="Content">What it shows.</param>
/// <param name="ClassName">Its element's own class (the page's styles and tests find it by it).</param>
/// <param name="Actions">Buttons of its own in its header, before Hide.</param>
public sealed record DockPane(
    string Id,
    string Label,
    RenderFragment Content,
    string? ClassName = null,
    RenderFragment? Actions = null);
