namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A document renamed in its folder (POST /workbench/rename, a tab's Rename…): where it was and where it is.</summary>
public sealed record RenamedDocument(string From, string To);
