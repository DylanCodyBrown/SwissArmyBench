namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>One line a rename or a replace changes: its number, before and after.</summary>
public sealed record IdeLineChange(int Line, string Before, string After);
