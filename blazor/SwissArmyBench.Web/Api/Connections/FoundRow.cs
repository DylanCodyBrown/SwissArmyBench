namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One connection found on this computer (never its password): its kind, where it points, whether it is already added, what only this computer has.</summary>
public sealed record FoundRow(
    string Id,
    string Name,
    string Kind,
    string KindLabel,
    string Server = "",
    int? Port = null,
    string Database = "",
    string User = "",
    string Path = "",
    IReadOnlyList<FoundSource>? From = null,
    string? Already = null,
    bool Supported = true,
    string? Why = null,
    string DataSource = "",
    string SignIn = "",
    bool Searched = false,
    IReadOnlyList<LocalNote>? Local = null);
