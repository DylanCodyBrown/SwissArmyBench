namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A lineage node's value: what it holds now, or where the flow broke.</summary>
public sealed record LineageValue(IReadOnlyList<LineageItem> Items, string? Error, bool Busy);
