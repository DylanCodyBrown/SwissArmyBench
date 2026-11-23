using System.Text.Json;

namespace SwissArmyBench.Web.Api.Environment;

/// <summary>One row of the Environment: a table, a variable, a structure, a setting or a library, and where it is used.
/// Open is true or false for a table (open in Grids) and a structure's own word for one (open, saved...).</summary>
public sealed record EnvironmentItem(
    string Id,
    string Kind,
    string Name,
    string Type = "",
    string Size = "",
    string Value = "",
    string From = "",
    IReadOnlyList<EnvironmentUse>? Used = null,
    JsonElement? Open = null,
    bool? Pinned = null,
    string? Version = null,
    string? Latest = null);
