namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /connections/found: what the known tools and the settings folders hold.</summary>
public sealed record FoundList(
    IReadOnlyList<FoundRow> Connections,
    IReadOnlyList<string> Notes,
    int Files = 0,
    string? Stopped = null);
