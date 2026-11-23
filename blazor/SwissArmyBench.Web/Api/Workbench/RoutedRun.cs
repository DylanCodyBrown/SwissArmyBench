namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A routed cell's run: the notebook's file, the cell's kind as the route reads it (typescript or sql), its
/// code and its number.</summary>
public sealed record RoutedRun(string? Path, string Kind, string Code, int Cell);
