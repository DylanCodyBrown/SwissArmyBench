using System.Text.Json;

namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A blade as its IDE reads it (GET /blades/{name}): its kind, code and file's stamp, whether it is a
/// starter's (read-only) or removable, its file, and what its code asks for (secrets, variables).</summary>
public sealed record BladeDetail(
    string Name,
    string Kind,
    string Code,
    string Stamp,
    bool ReadOnly = false,
    bool Removable = true,
    string? Pack = null,
    string? File = null,
    IReadOnlyList<string>? EnvNames = null,
    IReadOnlyDictionary<string, bool>? Secrets = null,
    JsonElement? Inspect = null,
    string? Language = null);
