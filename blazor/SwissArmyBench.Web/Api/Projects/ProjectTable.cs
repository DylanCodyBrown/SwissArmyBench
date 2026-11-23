namespace SwissArmyBench.Web.Api.Projects;

/// <summary>One of the open project's tables: its name, where it comes from, whether it has no source to read again
/// (a paste, a push: its rows are kept only on a tick) and whether they are kept.</summary>
public sealed record ProjectTable(string Name, string Kind = "", string From = "", bool NeedsRows = false, bool KeepRows = false);
