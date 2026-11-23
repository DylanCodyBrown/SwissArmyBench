namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>A row to work through on an extension's panel, with its one fix.</summary>
public sealed record PanelRow(string Id, string Text, string? Tone = null, PanelAction? Action = null);
