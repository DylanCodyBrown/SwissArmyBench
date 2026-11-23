namespace SwissArmyBench.Web.Api.Apis;

/// <summary>One field of an endpoint's shape: its path, type, format, whether it can be empty, its drift
/// mark.</summary>
public sealed record ActionField(
    string Path,
    string Type,
    string Format = "",
    bool Empty = false,
    string Mark = "");
