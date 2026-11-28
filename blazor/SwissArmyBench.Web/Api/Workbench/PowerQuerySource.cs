namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A source a query's composed SQL names: what the SQL calls it, the M function, and it in words.</summary>
public sealed record PowerQuerySource(string Name, string Function, string Kind, string Words);
