namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A variable of the failing function, what it held, and whether it is a table (Open as a grid).</summary>
public sealed record RunErrorLocal(string Name, string Repr, string Type, bool Table);
