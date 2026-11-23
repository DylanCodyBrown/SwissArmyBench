namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A document imported: where from, its path in the project and its whole path.</summary>
public sealed record ImportedDocument(string From, string Path, string Full);
