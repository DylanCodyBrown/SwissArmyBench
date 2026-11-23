namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A module's outline line: a class, a function, a method or a constant, its line, and what it holds.</summary>
public sealed record TreeSymbol(string Name, string Kind, int Line, IReadOnlyList<TreeSymbol> Children);
