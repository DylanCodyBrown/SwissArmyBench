using System.Text.Json;

namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A connection kind's Add connection form (GET /connections/types), or a saved connection as its form (GET /connections/{name}): the code, its fields by part, its passwords.</summary>
public sealed record ConnectionForm(
    string Id,
    string Label,
    string Group,
    string Connection,
    string Kind,
    string? Dialect,
    string Variable,
    string Code,
    IReadOnlyList<FormField> Fields,
    IReadOnlyDictionary<string, IReadOnlyList<string>> FieldOrder,
    IReadOnlyList<string> Secrets,
    IReadOnlyList<PackageNeed> Packages,
    IReadOnlyList<LocalNote> Local,
    JsonElement Catalog,
    string Note = "",
    WritesInfo? Writes = null,
    string? Name = null,
    string? Description = null);
