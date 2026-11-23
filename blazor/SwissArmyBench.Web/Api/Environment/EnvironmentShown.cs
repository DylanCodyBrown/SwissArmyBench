using System.Text.Json;

namespace SwissArmyBench.Web.Api.Environment;

/// <summary>GET /environment/show: one row whole for the viewer beside the list: what it is, where it is used, and
/// its parts (a table's columns: name, type in words, range), each part a list of words.</summary>
public sealed record EnvironmentShown(
    string Kind,
    string Name,
    string Type = "",
    string Size = "",
    string Value = "",
    string From = "",
    IReadOnlyList<EnvironmentUse>? Used = null,
    JsonElement? Kids = null,
    int MoreKids = 0);
