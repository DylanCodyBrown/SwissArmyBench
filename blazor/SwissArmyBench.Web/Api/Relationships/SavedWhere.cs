namespace SwissArmyBench.Web.Api.Relationships;

/// <summary>The answer when a set kept: where (mine or shared) and its file.</summary>
public sealed record SavedWhere(string? Where = null, string? File = null);
