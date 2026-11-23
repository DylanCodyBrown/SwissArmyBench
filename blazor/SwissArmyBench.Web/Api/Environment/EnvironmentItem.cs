using System.Text.Json;

namespace SwissArmyBench.Web.Api.Environment;

/// <summary>One row of the Environment: a table, a variable, a structure, a setting or a library, its words for each column, where it is used and its parts (a table's columns, a structure's paths) as [name, type, words].</summary>
public sealed record EnvironmentItem(
    string Id,
    string Kind,
    string Name,
    string Type = "",
    string Size = "",
    string Value = "",
    string From = "",
    string? Sub = null,
    IReadOnlyList<string>? Tags = null,
    IReadOnlyList<EnvironmentGrid>? Grids = null,
    IReadOnlyList<EnvironmentUse>? Used = null,
    IReadOnlyList<IReadOnlyList<string>>? Kids = null,
    int MoreKids = 0,
    EnvironmentMatch? Match = null,
    JsonElement? Open = null,
    bool InPython = false,
    string? Path = null,
    bool Saved = false,
    bool Secret = false,
    bool Editable = false,
    bool Renamable = false,
    bool Showable = false,
    string? Version = null,
    bool Installed = false,
    bool Pinned = false,
    string? Latest = null);
