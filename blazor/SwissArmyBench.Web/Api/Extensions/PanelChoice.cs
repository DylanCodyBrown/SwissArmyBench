namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>A picker of an extension's panel.</summary>
public sealed record PanelChoice(string Id, string Label, string Value, IReadOnlyList<PanelOption> Options);
