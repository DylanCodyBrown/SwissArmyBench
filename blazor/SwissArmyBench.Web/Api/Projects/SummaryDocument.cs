namespace SwissArmyBench.Web.Api.Projects;

/// <summary>One of the project's documents on Home's summary: its kind (notebook, script, app, structure), the page
/// it opens on, its whole path (<see cref="Full"/>), and whether it is API.py.</summary>
public sealed record SummaryDocument(
    string Name,
    string Path,
    string Full,
    string Kind,
    string Page,
    bool Api = false);
