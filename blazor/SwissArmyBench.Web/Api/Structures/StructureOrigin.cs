namespace SwissArmyBench.Web.Api.Structures;

/// <summary>Where a structure came from: a file, a paste, New, an API's answer (its call, status, time, headers, what it said).</summary>
public sealed record StructureOrigin(
    string Kind,
    string? Api = null,
    string? Operation = null,
    string? Method = null,
    string? Path = null,
    int? Status = null,
    double? Ms = null,
    IReadOnlyDictionary<string, string>? Headers = null,
    string? Said = null);
