namespace SwissArmyBench.Web.Api.Projects;

/// <summary>A document copied into the open project: where from, its path in the project and its whole path.</summary>
public sealed record ImportedDocument(string From, string Path, string Full);
