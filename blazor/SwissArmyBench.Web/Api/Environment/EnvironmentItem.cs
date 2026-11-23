namespace SwissArmyBench.Web.Api.Environment;

/// <summary>One row of the Environment: a table, a variable, a structure, a setting or a library, and where it is used.</summary>
public sealed record EnvironmentItem(
    string Id,
    string Kind,
    string Name,
    string Type = "",
    string Size = "",
    string Value = "",
    string From = "",
    IReadOnlyList<EnvironmentUse>? Used = null,
    bool Open = false,
    bool? Pinned = null,
    string? Version = null,
    string? Latest = null);
