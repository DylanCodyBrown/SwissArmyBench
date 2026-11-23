namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>A button of an extension's panel (a sentence under it, its note).</summary>
public sealed record PanelAction(
    string Id,
    string Label,
    bool Primary = false,
    bool Disabled = false,
    string? Note = null);
