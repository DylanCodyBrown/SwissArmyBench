namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>One line an extension's panel says, and its tone (ok, warn, error).</summary>
public sealed record PanelLine(string Text, string? Tone = null);
