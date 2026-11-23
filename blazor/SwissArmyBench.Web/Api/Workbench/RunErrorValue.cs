namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A part of the failing line and what it held (its text and type).</summary>
public sealed record RunErrorValue(string Expr, string Repr, string Type);
